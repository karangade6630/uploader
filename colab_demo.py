"""
colab_demo.py
-------------
Orchestrator that:
  1. Converts notebook.ipynb -> script.py
  2. Runs script.py on a Google Colab cloud VM via `colab run`
  3. Streams all stdout/stderr live to the terminal AND to the dashboard
  4. Checks MongoDB before each cycle so we don't spin the VM needlessly
  5. Respects Pause / Stop commands from the live web dashboard
"""

import json
import os
import re
import subprocess
import sys
import time
import shutil
import threading
import psutil
import random
import datetime
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------------------------
# PYMONGO IMPORT
# ---------------------------------------------------------------------------
try:
    from pymongo import MongoClient
except ImportError:
    sys.exit("FATAL: pymongo is not installed. Run: pip install pymongo dnspython")

# ---------------------------------------------------------------------------
# WINDOWS UTF-8 ENCODING FIX
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.system("")

SUBPROCESS_ENV = os.environ.copy()
SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
SUBPROCESS_ENV["PYTHONUTF8"] = "1"

# ---------------------------------------------------------------------------
# GOOGLE ADC CHECK (runs at import time for visibility in logs)
# ---------------------------------------------------------------------------
print("========== GOOGLE ADC CHECK ==========")
_credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
print("GOOGLE_APPLICATION_CREDENTIALS =", _credentials_path)
if _credentials_path:
    print("Credential file exists =", os.path.isfile(_credentials_path))
else:
    print("GOOGLE_APPLICATION_CREDENTIALS is not set")
print("Render secret directory exists =", os.path.isdir("/etc/secrets"))
if os.path.isdir("/etc/secrets"):
    print("Render secret files =", os.listdir("/etc/secrets"))
print("======================================")

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
NOTEBOOK_FILE = "notebook.ipynb"
TARGET_FILE   = "script.py"
SESSION_ID_FILE = "active_colab_session.lock"

TIMEOUT_SECONDS         = 10 * 60   # hard cap per `colab run` call (seconds)
WATCHDOG_GRACE_SECONDS  = 20
COOLDOWN_ON_412         = 10

# Scheduling
MAX_DAILY_RUNS              = 10
MIN_SLEEP_AFTER_RUN_MINUTES = 45
MAX_SLEEP_AFTER_RUN_MINUTES = 120
NO_MOVIE_WAIT_MINUTES       = 20

# MongoDB  (hardcoded fallback; prefer env var MONGO_URI in production)
_MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://karangade6630_db_user:PH3mTb73zv9yUZrw@movie-scraper-data.j3z6hjh.mongodb.net/"
)
MONGO_DB = "movie_scraper"

# ---------------------------------------------------------------------------
# LIVE DASHBOARD INTEGRATION
# ---------------------------------------------------------------------------
try:
    import dashboard_server as _ds
    _DASHBOARD_AVAILABLE = True
except ImportError:
    _DASHBOARD_AVAILABLE = False


def _emit(event_type: str, **kwargs):
    """Push a structured event to the live dashboard (no-op if not available)."""
    if _DASHBOARD_AVAILABLE:
        try:
            _ds.emit(event_type, **kwargs)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MONGODB HELPERS
# ---------------------------------------------------------------------------

def _get_mongo_client() -> MongoClient:
    return MongoClient(_MONGO_URI, serverSelectionTimeoutMS=7000)


def _extract_all_urls(movie_doc: dict) -> set:
    """Extract every download URL from a movie document's `links` field."""
    urls: set = set()

    # Direct top-level url field
    if isinstance(movie_doc.get("url"), str) and movie_doc["url"].strip():
        urls.add(movie_doc["url"].strip())

    raw = movie_doc.get("links")
    if not raw:
        return urls

    try:
        groups = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict):
                    for link_obj in group.get("links", []):
                        if isinstance(link_obj, dict) and link_obj.get("url"):
                            urls.add(link_obj["url"].strip())
                        elif isinstance(link_obj, str) and link_obj.strip():
                            urls.add(link_obj.strip())
                elif isinstance(group, str) and group.strip():
                    urls.add(group.strip())
    except Exception:
        pass

    return urls


def _check_batch_unseen(seen_col, batch_urls: set) -> bool:
    """Returns True if at least one URL in batch_urls is NOT in seen_links."""
    if not batch_urls:
        return False
    seen_docs = seen_col.find(
        {"url": {"$in": list(batch_urls)}}, {"url": 1, "_id": 0}
    )
    seen_in_db = set(d["url"] for d in seen_docs if "url" in d)
    return bool(batch_urls - seen_in_db)


def has_unprocessed_movies(batch_size: int = 1000) -> bool:
    """
    Fast streaming check: returns True as soon as a single unseen URL is found.
    Uses batched $in queries against seen_links (which has a unique index on url).
    """
    client = None
    try:
        client = _get_mongo_client()
        db         = client[MONGO_DB]
        seen_col   = db["seen_links"]
        movies_col = db["movies"]

        cursor = movies_col.find({}, {"url": 1, "links": 1}).batch_size(batch_size)
        pending_urls: set = set()

        for movie in cursor:
            pending_urls.update(_extract_all_urls(movie))
            if len(pending_urls) >= batch_size:
                if _check_batch_unseen(seen_col, pending_urls):
                    print("DB Check: Unprocessed movies detected! (Early exit)")
                    return True
                pending_urls.clear()

        if pending_urls and _check_batch_unseen(seen_col, pending_urls):
            print("DB Check: Unprocessed movies detected in final batch!")
            return True

        print("DB Check: No new movies found. All caught up.")
        return False

    except Exception as e:
        print(f"MongoDB Check Error: {e}")
        return True   # fail-open so the VM still runs
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def get_mongo_overview() -> dict:
    """
    Returns a full summary of DB state and broadcasts it to the dashboard.
    Runs in a background thread to avoid blocking the scheduling loop.
    """
    result = {
        "connected": False,
        "total_movies": 0,
        "seen_links": 0,
        "unprocessed_count": 0,
        "next_movie_title": None,
        "next_movie_page": None,
        "error": None,
    }
    client = None
    try:
        client = _get_mongo_client()
        db         = client[MONGO_DB]
        movies_col = db["movies"]
        seen_col   = db["seen_links"]

        total_movies = movies_col.count_documents({})
        total_seen   = seen_col.count_documents({})

        # Load all seen URLs into a set (4,632 docs ~ 2-3 MB, fast)
        seen_urls: set = set(
            d["url"] for d in seen_col.find({}, {"url": 1, "_id": 0}) if "url" in d
        )

        unprocessed_count   = 0
        first_movie_title   = None
        first_movie_page    = None

        cursor = movies_col.find(
            {}, {"title": 1, "links": 1, "url": 1, "page_num": 1}
        ).sort([("page_num", 1), ("id", 1)]).batch_size(2000)

        for m in cursor:
            urls   = _extract_all_urls(m)
            unseen = [u for u in urls if u not in seen_urls]
            if unseen:
                unprocessed_count += 1
                if first_movie_title is None:
                    first_movie_title = m.get("title")
                    first_movie_page  = m.get("page_num")

        result.update({
            "connected":         True,
            "total_movies":      total_movies,
            "seen_links":        total_seen,
            "unprocessed_count": unprocessed_count,
            "next_movie_title":  first_movie_title,
            "next_movie_page":   first_movie_page,
        })

        print(
            f"DB Overview: {total_movies} movies | "
            f"{total_seen} seen | "
            f"{unprocessed_count} unprocessed | "
            f"Next: {first_movie_title} (Page {first_movie_page})"
        )

    except Exception as e:
        result["error"] = str(e)
        print(f"MongoDB overview error: {e}")
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass

    # Broadcast to dashboard
    _emit("db_status", **result)
    if _DASHBOARD_AVAILABLE:
        try:
            _ds.update_db_state(result)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# CONTROL STATE & PROCESS MANAGEMENT
# ---------------------------------------------------------------------------
_runner_thread: threading.Thread | None = None
_runner_lock   = threading.Lock()
_active_process: subprocess.Popen | None = None
_active_process_lock = threading.Lock()


def _set_active_process(p):
    global _active_process
    with _active_process_lock:
        _active_process = p


def _kill_active_process():
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
            try:
                _kill_process_tree(_active_process.pid)
            except Exception:
                try:
                    _active_process.kill()
                except Exception:
                    pass


def _suspend_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.suspend()
            except Exception:
                pass
        parent.suspend()
    except Exception as e:
        print(f"Failed to suspend process tree: {e}")


def _resume_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        parent.resume()
        for child in parent.children(recursive=True):
            try:
                child.resume()
            except Exception:
                pass
    except Exception as e:
        print(f"Failed to resume process tree: {e}")


def _kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        procs  = parent.children(recursive=True)
        procs.append(parent)
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs(procs, timeout=5)
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        print(f"Failed to kill process tree for PID {pid}: {e}")


def _on_pause():
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
            _suspend_process_tree(_active_process.pid)
            _emit("warn", msg="Active process suspended (paused).")


def _on_resume():
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
            _resume_process_tree(_active_process.pid)
            _emit("log", msg="Active process resumed.")


def _on_stop():
    print("\nStop requested from dashboard - killing active process...")
    _kill_active_process()
    threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()
    _emit("warn", msg="Run stopped by user. Clearing active sessions...")


# ---------------------------------------------------------------------------
# CLI STDOUT STREAM PARSER
# ---------------------------------------------------------------------------
_DL_RE = re.compile(
    r"(?:Downloading|Downloading).+?(\d+\.\d+)%\s*\|"
    r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
    r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
    re.IGNORECASE,
)
_UL_RE = re.compile(
    r"(?:Uploading).+?(\d+\.\d+)%\s*\|"
    r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
    r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
    re.IGNORECASE,
)
_DL_FILE_RE   = re.compile(r"Downloading:\s*(.+?)(?:\.{3}|$)", re.IGNORECASE)
_SAVED_RE     = re.compile(r"Saved to\s+(.+)", re.IGNORECASE)
_UPLOAD_RE    = re.compile(r"(?:Updated|Created).+?'(.+?)'\s+on\s+Google\s+Drive", re.IGNORECASE)
_AUTH_CRED_RE = re.compile(r"Downloading service account", re.IGNORECASE)
_AUTH_OK_RE   = re.compile(r"Successfully authenticated", re.IGNORECASE)
_SESSION_RE   = re.compile(
    r"(?:Creating session '|Session READY \(|run-|session id[:\s]+)(?:run-)?([a-zA-Z0-9]{4,12})",
    re.IGNORECASE,
)

_current_dl_file = None
_current_ul_file = None


def _parse_and_emit_line(line: str):
    """Parse one stdout line and emit the matching dashboard event."""
    global _current_dl_file, _current_ul_file

    if _AUTH_CRED_RE.search(line):
        _emit("auth_start", msg="Downloading service account credentials...")
        return
    if _AUTH_OK_RE.search(line):
        _emit("auth_ok", msg="Authenticated with Google Drive API")
        return

    m = _DL_FILE_RE.search(line)
    if m:
        _current_dl_file = m.group(1).strip()
        _emit("download", msg=f"Downloading: {_current_dl_file}",
              filename=_current_dl_file, pct=0)
        return

    m = _DL_RE.search(line)
    if m:
        pct   = float(m.group(1))
        done  = m.group(2)
        total = m.group(3)
        speed = m.group(4) or ""
        eta   = m.group(5) or ""
        fname = _current_dl_file or "file"
        _emit("download", msg=f"{fname} - {pct:.1f}%",
              filename=fname, pct=round(pct, 1),
              done=done, total=total, speed=speed, eta=eta)
        return

    m = _SAVED_RE.search(line)
    if m:
        _current_dl_file = None
        _emit("file_saved", msg=f"Saved: {m.group(1).strip()}", detail=m.group(1).strip())
        return

    m = _UPLOAD_RE.search(line)
    if m:
        fname = m.group(1)
        _emit("upload", msg=f"Uploaded to Drive: {fname}", filename=fname, pct=100)
        return

    m = _UL_RE.search(line)
    if m:
        pct   = float(m.group(1))
        done  = m.group(2)
        total = m.group(3)
        speed = m.group(4) or ""
        eta   = m.group(5) or ""
        fname = _current_ul_file or "file"
        _emit("upload", msg=f"{fname} - {pct:.1f}%",
              filename=fname, pct=round(pct, 1),
              done=done, total=total, speed=speed, eta=eta)
        return

    if re.search(r"ERROR|FATAL", line):
        _emit("error", msg=line.strip())
        return
    if re.search(r"WARN|warning", line, re.IGNORECASE):
        _emit("warn", msg=line.strip())
        return

    _emit("log", msg=line.rstrip())


def stream_subprocess_output(process, on_line=None):
    """
    Reads stdout from `process` in 4 KB chunks.
    - Handles \\r (in-place progress bars) and \\n (newlines).
    - Parses each completed line and emits dashboard events.
    - Calls optional on_line(line) callback (e.g. to capture session ID).
    """
    buf = ""
    while True:
        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            break
        chunk = process.stdout.read(4096)
        if not chunk:
            break
        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            break
        buf += chunk.replace("\r\n", "\n")

        while True:
            idx_r = buf.find("\r")
            idx_n = buf.find("\n")
            if idx_r == -1 and idx_n == -1:
                break

            if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
                # Full newline-terminated line
                line, buf = buf[:idx_n], buf[idx_n + 1:]
                sys.stdout.write(f"\r{line}\n")
                _parse_and_emit_line(line)
                if on_line:
                    on_line(line)
            else:
                # Carriage-return (in-place overwrite progress line)
                line, buf = buf[:idx_r], buf[idx_r + 1:]
                sys.stdout.write(f"\r{line.ljust(80)}")
                _parse_and_emit_line(line)

        sys.stdout.flush()


# ---------------------------------------------------------------------------
# CORE RUNNER FUNCTIONS
# ---------------------------------------------------------------------------

def check_dependencies():
    if not shutil.which("colab"):
        sys.exit("FATAL: 'colab' CLI is not installed or not in PATH.")


def convert_ipynb_to_py(ipynb_path: str, py_path: str):
    if not os.path.exists(ipynb_path):
        raise FileNotFoundError(f"Source file '{ipynb_path}' not found.")
    _emit("convert", msg=f"Converting {ipynb_path} to {py_path}...")
    with open(ipynb_path, "r", encoding="utf-8", errors="replace") as f:
        nb_data = json.load(f)
    code_lines = [
        "".join(cell.get("source", [])) + "\n\n"
        for cell in nb_data.get("cells", [])
        if cell.get("cell_type") == "code"
    ]
    with open(py_path, "w", encoding="utf-8", errors="replace") as f:
        f.writelines(code_lines)
    print(f"Converted '{ipynb_path}' to '{py_path}'.")
    _emit("convert", msg=f"Converted {ipynb_path} to {py_path}")


def manage_session_lock(session_id=None, action="get"):
    try:
        if action == "save" and session_id:
            with open(SESSION_ID_FILE, "w", encoding="utf-8") as f:
                f.write(session_id.strip())
        elif action == "get" and os.path.exists(SESSION_ID_FILE):
            with open(SESSION_ID_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        elif action == "clear" and os.path.exists(SESSION_ID_FILE):
            os.remove(SESSION_ID_FILE)
    except Exception:
        pass
    return None


def stop_session(session_id: str) -> bool:
    if not session_id:
        return False
    session_name = session_id if session_id.startswith("run-") else f"run-{session_id}"
    try:
        result = subprocess.run(
            ["colab", "--auth=adc", "stop", "-s", session_name],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30, env=SUBPROCESS_ENV,
        )
        return result.returncode == 0
    except Exception:
        return False


def cleanup_and_verify_sessions():
    stored_id = manage_session_lock(action="get")
    if stored_id:
        stop_session(stored_id)
        manage_session_lock(action="clear")
    try:
        list_check = subprocess.run(
            ["colab", "sessions"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=15, env=SUBPROCESS_ENV,
        )
        if list_check.returncode == 0 and list_check.stdout.strip():
            found_ids = set()
            for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
                found_ids.add(m.group(1))
            if found_ids:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(stop_session, filter(None, found_ids))
    except Exception:
        pass


def run_remote_colab_cycle(cycle_num: int, runs_today: int) -> bool:
    """Runs one full Colab cycle. Returns True on success / expected completion."""
    print(f"\n{'='*40}\nCYCLE START (Run {runs_today}/{MAX_DAILY_RUNS} for Today)\n{'='*40}")
    _emit("cycle_start",
          msg=f"Cycle #{cycle_num} starting (Run {runs_today}/{MAX_DAILY_RUNS} today)",
          cycle=cycle_num, total=MAX_DAILY_RUNS)

    cleanup_and_verify_sessions()
    if _DASHBOARD_AVAILABLE and _ds.should_stop():
        return False

    exec_command = [
        "colab", "--auth=adc", "run",
        "--timeout", str(TIMEOUT_SECONDS),
        TARGET_FILE,
    ]

    session_id     = None
    process        = None
    timer          = None
    watchdog_fired = threading.Event()

    try:
        process = subprocess.Popen(
            exec_command,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, env=SUBPROCESS_ENV,
        )
        _set_active_process(process)
        _emit("session_start", msg="Provisioning new Colab session...")

        def _watchdog_fire():
            watchdog_fired.set()
            _kill_process_tree(process.pid)

        timer = threading.Timer(
            TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS, _watchdog_fire
        )
        timer.daemon = True
        timer.start()

        def _handle_line(line: str):
            nonlocal session_id
            if not session_id:
                m = _SESSION_RE.search(line)
                if m:
                    session_id = m.group(1).strip()
                    print(f"\nSession ID captured: {session_id}")
                    manage_session_lock(session_id, action="save")
                    _emit("session_ready",
                          msg=f"Session ready: {session_id}",
                          session_id=session_id)

        stream_subprocess_output(process, on_line=_handle_line)
        process.wait()

        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            return False

        if watchdog_fired.is_set():
            print(f"\nCycle force-terminated by watchdog.")
            _emit("warn", msg="Cycle force-terminated by watchdog.")
        elif process.returncode == 0:
            print("\nCloud execution completed successfully!")
            _emit("cycle_end",
                  msg=f"Cycle #{cycle_num} completed successfully",
                  cycle=cycle_num, total=MAX_DAILY_RUNS)
            return True
        else:
            print(f"\nExecution finished with exit code: {process.returncode}")
            _emit("warn", msg=f"Cycle #{cycle_num} exit code {process.returncode}")

    except Exception as e:
        err = str(e)
        print(f"\nError during execution: {err}")
        _emit("error", msg=f"Execution error: {err}")
        if any(x in err for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
            print(f"Rate limit (HTTP 412). Cooling down {COOLDOWN_ON_412}s...")
            _emit("warn", msg=f"Rate limit - cooling down {COOLDOWN_ON_412}s")
            time.sleep(COOLDOWN_ON_412)
    finally:
        if timer:
            timer.cancel()
        _set_active_process(None)
        if session_id:
            stop_session(session_id)
        manage_session_lock(action="clear")
        cleanup_and_verify_sessions()

    return True


# ---------------------------------------------------------------------------
# SCHEDULING RUNNER
# ---------------------------------------------------------------------------

def _interruptible_sleep(total_seconds: float):
    """Sleeps in 0.25s intervals so dashboard stop/pause is immediately responsive."""
    steps = int(total_seconds * 4)
    for _ in range(steps):
        if _DASHBOARD_AVAILABLE:
            if _ds.should_stop():
                return
            if not _ds.wait_if_paused():
                return
        time.sleep(0.25)


def _run_all_cycles():
    global _runner_thread

    try:
        convert_ipynb_to_py(NOTEBOOK_FILE, TARGET_FILE)
        cleanup_and_verify_sessions()
    except Exception as e:
        print(f"Startup error: {e}")
        _emit("error", msg=f"Startup error: {e}")
        if _DASHBOARD_AVAILABLE:
            _ds.mark_idle()
        with _runner_lock:
            _runner_thread = None
        return

    runs_today      = 0
    current_day     = datetime.date.today()
    cycle_num_total = 0

    while True:
        # 1. Day flip
        today = datetime.date.today()
        if today != current_day:
            current_day = today
            runs_today  = 0
            print(f"\nNew day! Resetting run counter to 0/{MAX_DAILY_RUNS}.")

        # 2. Daily cap — sleep until midnight
        if runs_today >= MAX_DAILY_RUNS:
            now      = datetime.datetime.now()
            tomorrow = now + datetime.timedelta(days=1)
            midnight = datetime.datetime(
                year=tomorrow.year, month=tomorrow.month,
                day=tomorrow.day, hour=0, minute=5
            )
            sleep_s = (midnight - now).total_seconds()
            print(f"\nReached {MAX_DAILY_RUNS} runs today.")
            print(f"Sleeping until {midnight.strftime('%Y-%m-%d %H:%M')}...")
            _emit("intermission",
                  msg=f"Daily limit reached. Sleeping until {midnight.strftime('%H:%M')}",
                  delay=int(sleep_s))
            _interruptible_sleep(sleep_s)
            continue

        # 3. Stop / Pause check
        if _DASHBOARD_AVAILABLE:
            if _ds.should_stop():
                break
            if not _ds.wait_if_paused():
                break

        # 4. MongoDB quick-check before burning a VM slot
        print("\nChecking MongoDB for unprocessed movies...")
        _emit("log", msg="Checking MongoDB for unprocessed movies...")

        if has_unprocessed_movies():
            # Full DB overview in background (non-blocking)
            threading.Thread(target=get_mongo_overview, daemon=True).start()

            cycle_num_total += 1
            completed = run_remote_colab_cycle(cycle_num_total, runs_today + 1)

            if not completed and _DASHBOARD_AVAILABLE and _ds.should_stop():
                break

            runs_today += 1
            sleep_mins = random.randint(
                MIN_SLEEP_AFTER_RUN_MINUTES, MAX_SLEEP_AFTER_RUN_MINUTES
            )
            print(f"\nFinished Run {runs_today}/{MAX_DAILY_RUNS} for today.")
            print(f"Anti-ban delay: {sleep_mins} minutes before next cycle...")
            _emit("intermission",
                  msg=f"Anti-ban delay: {sleep_mins} min before next cycle",
                  delay=sleep_mins * 60)
            _interruptible_sleep(sleep_mins * 60)
        else:
            threading.Thread(target=get_mongo_overview, daemon=True).start()
            print(f"\nNo movies to process. Waiting {NO_MOVIE_WAIT_MINUTES} min...")
            _emit("intermission",
                  msg=f"No new movies. Checking again in {NO_MOVIE_WAIT_MINUTES} min",
                  delay=NO_MOVIE_WAIT_MINUTES * 60)
            _interruptible_sleep(NO_MOVIE_WAIT_MINUTES * 60)

    if _DASHBOARD_AVAILABLE:
        _ds.mark_idle()
    with _runner_lock:
        _runner_thread = None


def _start_fresh_run():
    global _runner_thread
    with _runner_lock:
        if _runner_thread and _runner_thread.is_alive():
            return
        _kill_active_process()
        _runner_thread = threading.Thread(
            target=_run_all_cycles, daemon=True, name="colab-runner"
        )
        _runner_thread.start()


# ---------------------------------------------------------------------------
# GOOGLE ADC SETUP
# ---------------------------------------------------------------------------

def setup_google_adc():
    if os.environ.get("RENDER") == "true":
        cred = "/etc/secrets/application_default_credentials.json"
        if not os.path.isfile(cred):
            raise FileNotFoundError(f"Google credentials not found: {cred}")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred
    else:
        local = os.path.join(
            os.environ.get("APPDATA", ""), "gcloud",
            "application_default_credentials.json"
        )
        if os.path.isfile(local):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    setup_google_adc()
    check_dependencies()

    if not os.environ.get("MONGO_URI"):
        print("\nNOTE: MONGO_URI env var not set - using hardcoded URI in colab_demo.py\n")

    # Broadcast initial DB overview in background so it shows on dashboard immediately
    threading.Thread(target=get_mongo_overview, daemon=True).start()

    if _DASHBOARD_AVAILABLE:
        _ds.register_start_callback(_start_fresh_run)
        _ds.register_pause_callback(_on_pause)
        _ds.register_resume_callback(_on_resume)
        _ds.register_stop_callback(_on_stop)
        _ds.start_server(open_browser=(os.environ.get("RENDER") != "true"))
    else:
        try:
            _run_all_cycles()
        except KeyboardInterrupt:
            _kill_active_process()
            cleanup_and_verify_sessions()
            sys.exit(0)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _kill_active_process()
        cleanup_and_verify_sessions()
        sys.exit(0)
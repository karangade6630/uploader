# # gdown "https://drive.google.com/uc?id=19KSP1KUPAXCMBMazKUhk6fJF1uEkFSAg" -O notebook.ipynb


import json
import os
import re
import subprocess
import sys
import time
import shutil
import threading
import psutil
from concurrent.futures import ThreadPoolExecutor


print("========== GOOGLE ADC CHECK ==========")

credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

print("GOOGLE_APPLICATION_CREDENTIALS =", credentials_path)

if credentials_path:
    print("Credential file exists =", os.path.isfile(credentials_path))
else:
    print("❌ GOOGLE_APPLICATION_CREDENTIALS is not set")

print("Render secret directory exists =", os.path.isdir("/etc/secrets"))

if os.path.isdir("/etc/secrets"):
    print("Render secret files =", os.listdir("/etc/secrets"))

print("======================================")

# --- WINDOWS UTF-8 ENCODING FIX ---
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.system("")

SUBPROCESS_ENV = os.environ.copy()
SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
SUBPROCESS_ENV["PYTHONUTF8"] = "1"

# --- CONFIGURATION ---
NOTEBOOK_FILE = "notebook.ipynb"
TARGET_FILE = "script.py"
SESSION_ID_FILE = "active_colab_session.lock"

TIMEOUT_SECONDS = 10 * 60  # 10-minute limit
TOTAL_CYCLES = 99999999999
INTERMISSION_DELAY = 10     # seconds between cycles
COOLDOWN_ON_412 = 10       # cooldown when rate-limited

# ---------------------------------------------------------------------------
# ── LIVE DASHBOARD INTEGRATION ─────────────────────────────────────────────
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
# ── CONTROL STATE ──────────────────────────────────────────────────────────
# The runner thread is kept as a module-level reference so we never spawn
# two runners at the same time.
# ---------------------------------------------------------------------------
_runner_thread: threading.Thread | None = None
_runner_lock = threading.Lock()

# Reference to the currently running subprocess so stop() can kill it
_active_process: subprocess.Popen | None = None
_active_process_lock = threading.Lock()


def _set_active_process(p):
    global _active_process
    with _active_process_lock:
        _active_process = p


def _kill_active_process():
    """Kill the currently running colab subprocess if one exists."""
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
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
        print(f"⏸ Suspended process tree for PID {pid}")
    except Exception as e:
        print(f"⚠️ Failed to suspend process tree: {e}")


def _resume_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        parent.resume()
        for child in parent.children(recursive=True):
            try:
                child.resume()
            except Exception:
                pass
        print(f"▶ Resumed process tree for PID {pid}")
    except Exception as e:
        print(f"⚠️ Failed to resume process tree: {e}")


def _on_pause():
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
            _suspend_process_tree(_active_process.pid)
            _emit("warn", msg="⏸ Active process suspended (paused).")


def _on_resume():
    with _active_process_lock:
        if _active_process and _active_process.poll() is None:
            _resume_process_tree(_active_process.pid)
            _emit("log", msg="▶ Active process resumed.")


# def _on_stop():
#     print("\n🛑 Stop requested from dashboard — killing active process…")
#     _kill_active_process()
    
#     # Run session cleanup in a background thread to keep UI responsive
#     threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()
    
#     _emit("warn", msg="🛑 Run stopped by user. Clearing active sessions…")

def _on_stop():
    print("\n🛑 Stop requested from dashboard.")

    # 1. Stop the local colab CLI subprocess
    _kill_active_process()

    # 2. Get the exact remote session name immediately
    session_name = manage_session_lock(action="get")

    if session_name:
        print(f"🛑 Remote session found: {session_name}")

        # Stop the remote VM explicitly
        threading.Thread(
            target=stop_session,
            args=(session_name,),
            daemon=True,
            name="remote-colab-stop",
        ).start()

        # Remove the lock
        manage_session_lock(action="clear")

    else:
        print("⚠️ No stored remote session found.")

        # Fallback: scan all active sessions
        threading.Thread(
            target=cleanup_and_verify_sessions,
            daemon=True,
            name="colab-cleanup",
        ).start()

    _emit(
        "warn",
        msg="🛑 Stop requested — terminating remote Colab session…"
    )
# ---------------------------------------------------------------------------
# ── STDOUT LINE PARSER / DASHBOARD EMITTER ─────────────────────────────────
# ---------------------------------------------------------------------------
_DL_RE = re.compile(
    r"(?:Downloading|📥).+?(\d+\.\d+)%\s*\|"
    r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
    r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
    re.IGNORECASE,
)
_UL_RE = re.compile(
    r"(?:Uploading|📤).+?(\d+\.\d+)%\s*\|"
    r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
    r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
    re.IGNORECASE,
)
_DL_FILE_RE   = re.compile(r"📥\s*Downloading:\s*(.+?)(?:\.{3}|$)", re.IGNORECASE)
_SAVED_RE     = re.compile(r"✅\s*Saved to\s+(.+)", re.IGNORECASE)
_UPLOAD_RE    = re.compile(r"(?:Updated|Created).+?'(.+?)'\s+on\s+Google\s+Drive", re.IGNORECASE)
_AUTH_CRED_RE = re.compile(r"Downloading service account", re.IGNORECASE)
_AUTH_OK_RE   = re.compile(r"Successfully authenticated", re.IGNORECASE)

_current_dl_file = None
_current_ul_file = None


def _parse_and_emit_line(line: str):
    """Parse a raw stdout line and emit the appropriate dashboard event."""
    global _current_dl_file, _current_ul_file

    if _AUTH_CRED_RE.search(line):
        _emit("auth_start", msg="Downloading service account credentials…")
        return
    if _AUTH_OK_RE.search(line):
        _emit("auth_ok", msg="✅ Authenticated with Google Drive API")
        return

    m = _DL_FILE_RE.search(line)
    if m:
        _current_dl_file = m.group(1).strip()
        _emit("download", msg=f"📥 Downloading: {_current_dl_file}", filename=_current_dl_file, pct=0)
        return

    m = _DL_RE.search(line)
    if m:
        pct   = float(m.group(1))
        done  = m.group(2)
        total = m.group(3)
        speed = m.group(4) or ""
        eta   = m.group(5) or ""
        fname = _current_dl_file or "file"
        _emit("download", msg=f"📥 {fname} — {pct:.1f}%",
              filename=fname, pct=round(pct, 1),
              done=done, total=total, speed=speed, eta=eta)
        return

    m = _SAVED_RE.search(line)
    if m:
        _current_dl_file = None
        _emit("file_saved", msg=f"💾 Saved: {m.group(1).strip()}", detail=m.group(1).strip())
        return

    m = _UPLOAD_RE.search(line)
    if m:
        fname = m.group(1)
        _emit("upload", msg=f"📤 Uploaded to Drive: {fname}", filename=fname, pct=100)
        return

    m = _UL_RE.search(line)
    if m:
        pct   = float(m.group(1))
        done  = m.group(2)
        total = m.group(3)
        speed = m.group(4) or ""
        eta   = m.group(5) or ""
        fname = _current_ul_file or "file"
        _emit("upload", msg=f"📤 {fname} — {pct:.1f}%",
              filename=fname, pct=round(pct, 1),
              done=done, total=total, speed=speed, eta=eta)
        return

    if re.search(r"❌|ERROR|FATAL", line):
        _emit("error", msg=line.strip())
        return
    if re.search(r"⚠️|WARN|warning", line, re.IGNORECASE):
        _emit("warn", msg=line.strip())
        return

    _emit("log", msg=line.rstrip())


# ---------------------------------------------------------------------------
# ── CORE RUNNER FUNCTIONS ──────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def check_dependencies():
    """Ensures the colab CLI is installed before starting."""
    if not shutil.which("colab"):
        sys.exit("❌ FATAL: 'colab' CLI is not installed or not in PATH. Please install it first.")


def convert_ipynb_to_py(ipynb_path, py_path):
    """Converts local source Jupyter notebook into a clean runnable Python script."""
    if not os.path.exists(ipynb_path):
        raise FileNotFoundError(f"Source file '{ipynb_path}' not found.")

    _emit("convert", msg=f"🔄 Converting {ipynb_path} → {py_path}…")

    with open(ipynb_path, "r", encoding="utf-8", errors="replace") as f:
        nb_data = json.load(f)

    code_lines = [
        "".join(cell.get("source", [])) + "\n\n"
        for cell in nb_data.get("cells", [])
        if cell.get("cell_type") == "code"
    ]

    with open(py_path, "w", encoding="utf-8", errors="replace") as f:
        f.writelines(code_lines)

    print(f"📄 Converted '{ipynb_path}' to '{py_path}'.")
    _emit("convert", msg=f"📄 Converted {ipynb_path} → {py_path}")


def manage_session_lock(session_id=None, action="get"):
    """Handles all lock file operations (get, save, clear) safely."""
    try:
        if action == "save" and session_id:
            with open(SESSION_ID_FILE, "w", encoding="utf-8") as f:
                f.write(session_id.strip())
        elif action == "get" and os.path.exists(SESSION_ID_FILE):
            with open(SESSION_ID_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        elif action == "clear" and os.path.exists(SESSION_ID_FILE):
            os.remove(SESSION_ID_FILE)
    except Exception as e:
        print(f"⚠️ Lock file warning: {e}")
    return None


# def stop_session(session_id):
#     """Terminates a specific Colab session."""
#     if not session_id:
#         print("returning because no session_id!")
#         return
#     try:
#         print("stopping session", session_id)
#         subprocess.run(
#             ["colab", "stop"],
#              capture_output=True, text=True, encoding="utf-8", errors="replace",
#             timeout=15, env=SUBPROCESS_ENV
#         )
#         print(f"✅ Terminated session: {session_id}")
#         _emit("session_stop", msg=f"🛑 Session terminated: {session_id}", session_id=session_id)
#     except Exception as e:
#         print(f"❌ Error terminating {session_id}: {e}")
#         _emit("error", msg=f"❌ Error terminating session {session_id}: {e}")

def stop_session(session_name):
    """Terminate the specific remote Colab session."""
    if not session_name:
        print("⚠️ No Colab session name to stop.")
        return False

    # Ensure the CLI receives the full session name.
    # Example: run-f5abb3
    if not session_name.startswith("run-"):
        session_name = session_name

    try:
        print(f"🛑 Stopping remote Colab session: {session_name}")

        result = subprocess.run(
            [
                "colab",
                "--auth=adc",
                "stop",
                "-s",
                session_name,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=SUBPROCESS_ENV,
        )

        output = (result.stdout or "") + (result.stderr or "")

        if output.strip():
            print(output.rstrip())

        if result.returncode == 0:
            print(f"✅ Remote Colab session stopped: {session_name}")

            _emit(
                "session_stop",
                msg=f"🛑 Remote Colab session stopped: {session_name}",
                session_id=session_name,
            )

            return True

        print(
            f"⚠️ Failed to stop session {session_name} "
            f"(exit code {result.returncode})"
        )

        _emit(
            "error",
            msg=f"❌ Failed to stop Colab session: {session_name}",
            session_id=session_name,
        )

        return False

    except subprocess.TimeoutExpired:
        print(f"⏰ Timeout while stopping session: {session_name}")

        _emit(
            "error",
            msg=f"⏰ Timeout while stopping session: {session_name}",
            session_id=session_name,
        )

        return False

    except Exception as e:
        print(f"❌ Error stopping {session_name}: {e}")

        _emit(
            "error",
            msg=f"❌ Error stopping session {session_name}: {e}",
        )

        return False
    
def cleanup_and_verify_sessions():
    """Aggressively finds and kills active sessions concurrently."""
    print("🧹 Clearing active Google Colab cloud sessions...")
    _emit("cleanup", msg="🧹 Clearing all active Colab sessions…")

    stored_id = manage_session_lock(action="get")
    print("seesion id", stored_id)
    if stored_id:
        stop_session(stored_id)
        manage_session_lock(action="clear")

    try:
        list_check = subprocess.run(
    [
        "colab",
        "--auth=adc",
        "sessions",
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=10,
    env=SUBPROCESS_ENV,
)
        if list_check.returncode == 0 and list_check.stdout.strip():
            # Extract session IDs (6-character hex strings)
            found_ids = set()
            for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
                found_ids.add(m.group(1))
            session_ids = list(found_ids)
            if session_ids:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(stop_session, filter(None, session_ids))
    except Exception:
        pass


def stream_subprocess_output(process, on_line=None):
    """Highly optimized stream reader for parsing CLI output and progress bars."""
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
                line, buf = buf[:idx_n], buf[idx_n + 1:]
                sys.stdout.write(f"\r{line}\n")
                _parse_and_emit_line(line)
                if on_line:
                    on_line(line)
            else:
                line, buf = buf[:idx_r], buf[idx_r + 1:]
                sys.stdout.write(f"\r{line.ljust(80)}")
                _parse_and_emit_line(line)
        sys.stdout.flush()


def run_remote_colab_cycle(cycle_num):
    """Run one full Colab cycle. Returns True if completed, False if stopped."""
    print(f"\n{'='*40}\n☁️  CYCLE #{cycle_num}: PROVISIONING & RUNNING\n{'='*40}")
    _emit("cycle_start",
          msg=f"🚀 Cycle #{cycle_num} starting — provisioning Colab session",
          cycle=cycle_num, total=TOTAL_CYCLES)

    cleanup_and_verify_sessions()

    # Check stop flag after cleanup
    if _DASHBOARD_AVAILABLE and _ds.should_stop():
        return False

    # exec_command = ["colab", "run", "--timeout", str(TIMEOUT_SECONDS), TARGET_FILE]
    exec_command = [
    "colab",
    "--auth=adc",
    "run",
    "--timeout",
    str(TIMEOUT_SECONDS),
    TARGET_FILE
]
    session_id = None
    process = None

    _emit("session_start", msg="☁️ Provisioning new Colab session…")

    try:
        process = subprocess.Popen(
            exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
        )
        _set_active_process(process)

        def _handle_line(line):
            nonlocal session_id
            if not session_id:
                match = re.search(r"(?:Creating session '|READY \()(?:run-)?([a-zA-Z0-9]+)", line)
                if match:
                    session_id = match.group(1).strip()
                    print(f"\n📌 Isolated Session ID: {session_id}")
                    manage_session_lock(session_id, action="save")
                    _emit("session_ready",
                          msg=f"📌 Session ready: {session_id}",
                          session_id=session_id)




        stream_subprocess_output(process, on_line=_handle_line)
        process.wait()

        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            print("\n🛑 Stop requested — aborting cycle.")
            return False

        if process.returncode == 0:
            print("\n🎉 Cloud execution completed successfully!")
            _emit("cycle_end",
                  msg=f"✅ Cycle #{cycle_num} completed successfully",
                  cycle=cycle_num, total=TOTAL_CYCLES)
        else:
            print(f"\n⚠️ Execution finished with exit code: {process.returncode}")
            _emit("warn",
                  msg=f"⚠️ Cycle #{cycle_num} finished with exit code {process.returncode}",
                  cycle=cycle_num)

    except subprocess.TimeoutExpired:
        print(f"\n⏰ TIMEOUT REACHED for session '{session_id}'! Force-killing...")
        _emit("error", msg=f"⏰ Timeout reached for session {session_id}! Force-killing.")
        if process:
            process.kill()

    except Exception as e:
        err_str = str(e)
        print(f"\n❌ Error during execution: {err_str}")
        _emit("error", msg=f"❌ Execution error: {err_str}")
        if any(x in err_str for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
            print(f"🛑 Rate limit hit (HTTP 412). Cool-down enforced ({COOLDOWN_ON_412}s)...")
            _emit("warn", msg=f"🛑 Rate limit (HTTP 412) — cooling down for {COOLDOWN_ON_412}s")
            time.sleep(COOLDOWN_ON_412)

    finally:
        _set_active_process(None)
        if session_id:
            stop_session(session_id)
        manage_session_lock(action="clear")

    return True


# ---------------------------------------------------------------------------
# ── MAIN RUNNER — runs in a background thread ──────────────────────────────
# ---------------------------------------------------------------------------

def _run_all_cycles():
    """
    The main cycle loop, always runs from cycle 1 when started.
    Runs in a daemon thread so it doesn't block Flask or the main thread.
    Checks stop/pause flags between every cycle.
    """
    global _runner_thread

    print("\n🏁 Runner starting — converting notebook…")
    _emit("log", msg="🏁 Runner starting fresh from Cycle 1…")

    try:
        convert_ipynb_to_py(NOTEBOOK_FILE, TARGET_FILE)
        cleanup_and_verify_sessions()
    except Exception as e:
        print(f"❌ Startup error: {e}")
        _emit("error", msg=f"❌ Startup error: {e}")
        if _DASHBOARD_AVAILABLE:
            _ds.mark_idle()
        with _runner_lock:
            _runner_thread = None
        return

    for i in range(1, TOTAL_CYCLES + 1):
        # ── Check stop before each cycle ──────────────────────────────────
        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            print("\n🛑 Stop requested — exiting cycle loop.")
            _emit("warn", msg="🛑 Run stopped by user.")
            break

        # ── Check pause before each cycle (blocks until resumed or stopped) ──
        if _DASHBOARD_AVAILABLE:
            _emit("log", msg=f"⏸ Checking pause before cycle #{i}…") if not _ds._pause_event.is_set() else None
            if not _ds.wait_if_paused():
                # stop was requested while we were paused
                print("\n🛑 Stopped while paused.")
                _emit("warn", msg="🛑 Run stopped by user while paused.")
                break

        completed = run_remote_colab_cycle(i)
        if not completed:
            break

        if i < TOTAL_CYCLES:
            # ── Interruptible intermission sleep ──────────────────────────
            print(f"\n⏳ Intermission: Waiting {INTERMISSION_DELAY}s...")
            _emit("intermission",
                  msg=f"⏳ Intermission — waiting {INTERMISSION_DELAY}s before next cycle",
                  delay=INTERMISSION_DELAY)

            for _ in range(INTERMISSION_DELAY * 4):   # check every 0.25s
                if _DASHBOARD_AVAILABLE:
                    if _ds.should_stop():
                        break
                    if not _ds.wait_if_paused():
                        break
                time.sleep(0.25)

            if _DASHBOARD_AVAILABLE and _ds.should_stop():
                _emit("warn", msg="🛑 Run stopped during intermission.")
                break

    else:
        # Loop finished without break → all cycles done
        print("\n🏆 All remote cloud cycles completed!")
        _emit("cycle_end",
              msg="🏆 All remote cloud cycles completed!",
              cycle=TOTAL_CYCLES, total=TOTAL_CYCLES)

    # ── Cleanup and reset state ────────────────────────────────────────────
    cleanup_and_verify_sessions()
    if _DASHBOARD_AVAILABLE:
        _ds.mark_idle()
    with _runner_lock:
        _runner_thread = None


def _start_fresh_run():
    """
    Callback registered with dashboard_server.
    Called when the browser presses START.
    Kills any leftover subprocess, then spawns a fresh runner thread.
    Always resets to cycle 1.
    """
    global _runner_thread

    with _runner_lock:
        if _runner_thread and _runner_thread.is_alive():
            # Shouldn't happen (server only calls this from idle), but be safe
            print("⚠️ Runner already active — ignoring start.")
            return

        # Kill any lingering subprocess
        _kill_active_process()

        # Spawn fresh runner starting from cycle 1
        _runner_thread = threading.Thread(
            target=_run_all_cycles, daemon=True, name="colab-runner"
        )
        _runner_thread.start()

def setup_google_adc():
    """
    Configure Google Application Default Credentials.

    Local:
        Uses the normal gcloud ADC location.

    Render:
        Uses the Render Secret File.
    """

    if os.environ.get("RENDER") == "true":
        credentials_path = "/etc/secrets/application_default_credentials.json"

        if not os.path.isfile(credentials_path):
            raise FileNotFoundError(
                f"❌ Google credentials not found: {credentials_path}"
            )

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        print("✅ Render Google ADC credentials detected.")
        print(f"🔐 Credentials: {credentials_path}")

    else:
        local_credentials = os.path.join(
            os.environ.get("APPDATA", ""),
            "gcloud",
            "application_default_credentials.json"
        )

        if os.path.isfile(local_credentials):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_credentials
            print("✅ Local Google ADC credentials detected.")
        else:
            print("⚠️ Local Google ADC credentials not found.")

# ---------------------------------------------------------------------------
# ── ENTRY POINT ────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

if __name__ == "__main__":
     # Configure Google authentication first
    setup_google_adc()
    # ── Start live dashboard server ────────────────────────────────────────
    if _DASHBOARD_AVAILABLE:
        # Register our callbacks so the browser control buttons work
        _ds.register_start_callback(_start_fresh_run)
        _ds.register_pause_callback(_on_pause)
        _ds.register_resume_callback(_on_resume)
        _ds.register_stop_callback(_on_stop)

        # Start dashboard server
        _ds.start_server(
            open_browser=(os.environ.get("RENDER") != "true")
        )

        _emit(
            "log",
            msg="🌐 Live dashboard started — press ▶ START to begin running cycles"
        )

        print("✅ Dashboard ready. Press ▶ START in the browser.")
    else:
        print("⚠️ dashboard_server.py not found or flask not installed.")
        print("    Install with: pip install flask")
        print("    Falling back to direct run…\n")

        check_dependencies()

        try:
            _run_all_cycles()
        except KeyboardInterrupt:
            print("\n\n🛑 Interrupt received!")
            _kill_active_process()
            cleanup_and_verify_sessions()
            sys.exit(0)

    # Keep the main thread alive so daemon threads keep running
    check_dependencies()

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
        _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
        _kill_active_process()
        cleanup_and_verify_sessions()
        sys.exit(0)
    # ── Start live dashboard server ────────────────────────────────────────
    if _DASHBOARD_AVAILABLE:
        # Register our callbacks so the browser control buttons work
        _ds.register_start_callback(_start_fresh_run)
        _ds.register_pause_callback(_on_pause)
        _ds.register_resume_callback(_on_resume)
        _ds.register_stop_callback(_on_stop)
        _ds.start_server(open_browser=True)
        _emit("log", msg="🌐 Live dashboard started — press ▶ START to begin running cycles")
        print("✅ Dashboard ready. Press ▶ START in the browser to begin.")
    else:
        print("⚠️  dashboard_server.py not found or flask not installed.")
        print("    Install with: pip install flask")
        print("    Falling back to direct run…\n")
        # No dashboard: run directly (original behaviour)
        check_dependencies()
        try:
            _run_all_cycles()
        except KeyboardInterrupt:
            print("\n\n🛑 Interrupt received!")
            _kill_active_process()
            cleanup_and_verify_sessions()
            sys.exit(0)

    # Keep the main thread alive so daemon threads keep running
    check_dependencies()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
        _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
        _kill_active_process()
        cleanup_and_verify_sessions()
        sys.exit(0)
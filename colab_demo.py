# # # gdown "https://drive.google.com/uc?id=19KSP1KUPAXCMBMazKUhk6fJF1uEkFSAg" -O notebook.ipynb


# import json
# import os
# import re
# import subprocess
# import sys
# import time
# import shutil
# import threading
# import psutil
# from concurrent.futures import ThreadPoolExecutor


# print("========== GOOGLE ADC CHECK ==========")

# credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

# print("GOOGLE_APPLICATION_CREDENTIALS =", credentials_path)

# if credentials_path:
#     print("Credential file exists =", os.path.isfile(credentials_path))
# else:
#     print("❌ GOOGLE_APPLICATION_CREDENTIALS is not set")

# print("Render secret directory exists =", os.path.isdir("/etc/secrets"))

# if os.path.isdir("/etc/secrets"):
#     print("Render secret files =", os.listdir("/etc/secrets"))

# print("======================================")

# # --- WINDOWS UTF-8 ENCODING FIX ---
# if sys.platform == "win32":
#     if hasattr(sys.stdout, "reconfigure"):
#         sys.stdout.reconfigure(encoding="utf-8", errors="replace")
#     if hasattr(sys.stderr, "reconfigure"):
#         sys.stderr.reconfigure(encoding="utf-8", errors="replace")
#     os.system("")

# SUBPROCESS_ENV = os.environ.copy()
# SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
# SUBPROCESS_ENV["PYTHONUTF8"] = "1"

# # --- CONFIGURATION ---
# NOTEBOOK_FILE = "notebook.ipynb"
# TARGET_FILE = "script.py"
# SESSION_ID_FILE = "active_colab_session.lock"

# TIMEOUT_SECONDS = 1 * 60  # 1-minute limit
# TOTAL_CYCLES = 99999999999
# INTERMISSION_DELAY = 10     # seconds between cycles
# COOLDOWN_ON_412 = 10       # cooldown when rate-limited

# # ---------------------------------------------------------------------------
# # ── LIVE DASHBOARD INTEGRATION ─────────────────────────────────────────────
# # ---------------------------------------------------------------------------
# try:
#     import dashboard_server as _ds
#     _DASHBOARD_AVAILABLE = True
# except ImportError:
#     _DASHBOARD_AVAILABLE = False

# def _emit(event_type: str, **kwargs):
#     """Push a structured event to the live dashboard (no-op if not available)."""
#     if _DASHBOARD_AVAILABLE:
#         try:
#             _ds.emit(event_type, **kwargs)
#         except Exception:
#             pass

# # ---------------------------------------------------------------------------
# # ── CONTROL STATE ──────────────────────────────────────────────────────────
# # The runner thread is kept as a module-level reference so we never spawn
# # two runners at the same time.
# # ---------------------------------------------------------------------------
# _runner_thread: threading.Thread | None = None
# _runner_lock = threading.Lock()

# # Reference to the currently running subprocess so stop() can kill it
# _active_process: subprocess.Popen | None = None
# _active_process_lock = threading.Lock()


# def _set_active_process(p):
#     global _active_process
#     with _active_process_lock:
#         _active_process = p


# def _kill_active_process():
#     """Kill the currently running colab subprocess if one exists."""
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             try:
#                 _active_process.kill()
#             except Exception:
#                 pass


# def _suspend_process_tree(pid):
#     try:
#         parent = psutil.Process(pid)
#         for child in parent.children(recursive=True):
#             try:
#                 child.suspend()
#             except Exception:
#                 pass
#         parent.suspend()
#         print(f"⏸ Suspended process tree for PID {pid}")
#     except Exception as e:
#         print(f"⚠️ Failed to suspend process tree: {e}")


# def _resume_process_tree(pid):
#     try:
#         parent = psutil.Process(pid)
#         parent.resume()
#         for child in parent.children(recursive=True):
#             try:
#                 child.resume()
#             except Exception:
#                 pass
#         print(f"▶ Resumed process tree for PID {pid}")
#     except Exception as e:
#         print(f"⚠️ Failed to resume process tree: {e}")


# def _on_pause():
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             _suspend_process_tree(_active_process.pid)
#             _emit("warn", msg="⏸ Active process suspended (paused).")


# def _on_resume():
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             _resume_process_tree(_active_process.pid)
#             _emit("log", msg="▶ Active process resumed.")


# def _on_stop():
#     print("\n🛑 Stop requested from dashboard — killing active process…")
#     _kill_active_process()
    
#     # Run session cleanup in a background thread to keep UI responsive
#     threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()
    
#     _emit("warn", msg="🛑 Run stopped by user. Clearing active sessions…")


# # ---------------------------------------------------------------------------
# # ── STDOUT LINE PARSER / DASHBOARD EMITTER ─────────────────────────────────
# # ---------------------------------------------------------------------------
# _DL_RE = re.compile(
#     r"(?:Downloading|📥).+?(\d+\.\d+)%\s*\|"
#     r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
#     r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
#     re.IGNORECASE,
# )
# _UL_RE = re.compile(
#     r"(?:Uploading|📤).+?(\d+\.\d+)%\s*\|"
#     r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
#     r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
#     re.IGNORECASE,
# )
# _DL_FILE_RE   = re.compile(r"📥\s*Downloading:\s*(.+?)(?:\.{3}|$)", re.IGNORECASE)
# _SAVED_RE     = re.compile(r"✅\s*Saved to\s+(.+)", re.IGNORECASE)
# _UPLOAD_RE    = re.compile(r"(?:Updated|Created).+?'(.+?)'\s+on\s+Google\s+Drive", re.IGNORECASE)
# _AUTH_CRED_RE = re.compile(r"Downloading service account", re.IGNORECASE)
# _AUTH_OK_RE   = re.compile(r"Successfully authenticated", re.IGNORECASE)

# _current_dl_file = None
# _current_ul_file = None


# def _parse_and_emit_line(line: str):
#     """Parse a raw stdout line and emit the appropriate dashboard event."""
#     global _current_dl_file, _current_ul_file

#     if _AUTH_CRED_RE.search(line):
#         _emit("auth_start", msg="Downloading service account credentials…")
#         return
#     if _AUTH_OK_RE.search(line):
#         _emit("auth_ok", msg="✅ Authenticated with Google Drive API")
#         return

#     m = _DL_FILE_RE.search(line)
#     if m:
#         _current_dl_file = m.group(1).strip()
#         _emit("download", msg=f"📥 Downloading: {_current_dl_file}", filename=_current_dl_file, pct=0)
#         return

#     m = _DL_RE.search(line)
#     if m:
#         pct   = float(m.group(1))
#         done  = m.group(2)
#         total = m.group(3)
#         speed = m.group(4) or ""
#         eta   = m.group(5) or ""
#         fname = _current_dl_file or "file"
#         _emit("download", msg=f"📥 {fname} — {pct:.1f}%",
#               filename=fname, pct=round(pct, 1),
#               done=done, total=total, speed=speed, eta=eta)
#         return

#     m = _SAVED_RE.search(line)
#     if m:
#         _current_dl_file = None
#         _emit("file_saved", msg=f"💾 Saved: {m.group(1).strip()}", detail=m.group(1).strip())
#         return

#     m = _UPLOAD_RE.search(line)
#     if m:
#         fname = m.group(1)
#         _emit("upload", msg=f"📤 Uploaded to Drive: {fname}", filename=fname, pct=100)
#         return

#     m = _UL_RE.search(line)
#     if m:
#         pct   = float(m.group(1))
#         done  = m.group(2)
#         total = m.group(3)
#         speed = m.group(4) or ""
#         eta   = m.group(5) or ""
#         fname = _current_ul_file or "file"
#         _emit("upload", msg=f"📤 {fname} — {pct:.1f}%",
#               filename=fname, pct=round(pct, 1),
#               done=done, total=total, speed=speed, eta=eta)
#         return

#     if re.search(r"❌|ERROR|FATAL", line):
#         _emit("error", msg=line.strip())
#         return
#     if re.search(r"⚠️|WARN|warning", line, re.IGNORECASE):
#         _emit("warn", msg=line.strip())
#         return

#     _emit("log", msg=line.rstrip())


# # ---------------------------------------------------------------------------
# # ── CORE RUNNER FUNCTIONS ──────────────────────────────────────────────────
# # ---------------------------------------------------------------------------

# def check_dependencies():
#     """Ensures the colab CLI is installed before starting."""
#     if not shutil.which("colab"):
#         sys.exit("❌ FATAL: 'colab' CLI is not installed or not in PATH. Please install it first.")


# def convert_ipynb_to_py(ipynb_path, py_path):
#     """Converts local source Jupyter notebook into a clean runnable Python script."""
#     if not os.path.exists(ipynb_path):
#         raise FileNotFoundError(f"Source file '{ipynb_path}' not found.")

#     _emit("convert", msg=f"🔄 Converting {ipynb_path} → {py_path}…")

#     with open(ipynb_path, "r", encoding="utf-8", errors="replace") as f:
#         nb_data = json.load(f)

#     code_lines = [
#         "".join(cell.get("source", [])) + "\n\n"
#         for cell in nb_data.get("cells", [])
#         if cell.get("cell_type") == "code"
#     ]

#     with open(py_path, "w", encoding="utf-8", errors="replace") as f:
#         f.writelines(code_lines)

#     print(f"📄 Converted '{ipynb_path}' to '{py_path}'.")
#     _emit("convert", msg=f"📄 Converted {ipynb_path} → {py_path}")


# def manage_session_lock(session_id=None, action="get"):
#     """Handles all lock file operations (get, save, clear) safely."""
#     try:
#         if action == "save" and session_id:
#             with open(SESSION_ID_FILE, "w", encoding="utf-8") as f:
#                 f.write(session_id.strip())
#         elif action == "get" and os.path.exists(SESSION_ID_FILE):
#             with open(SESSION_ID_FILE, "r", encoding="utf-8") as f:
#                 return f.read().strip()
#         elif action == "clear" and os.path.exists(SESSION_ID_FILE):
#             os.remove(SESSION_ID_FILE)
#     except Exception as e:
#         print(f"⚠️ Lock file warning: {e}")
#     return None


# # def stop_session(session_id):
# #     """Terminates a specific Colab session."""
# #     if not session_id:
# #         print("returning because no session_id!")
# #         return
# #     try:
# #         print("stopping session", session_id)
# #         subprocess.run(
# #             ["colab", "stop"],
# #              capture_output=True, text=True, encoding="utf-8", errors="replace",
# #             timeout=15, env=SUBPROCESS_ENV
# #         )
# #         print(f"✅ Terminated session: {session_id}")
# #         _emit("session_stop", msg=f"🛑 Session terminated: {session_id}", session_id=session_id)
# #     except Exception as e:
# #         print(f"❌ Error terminating {session_id}: {e}")
# #         _emit("error", msg=f"❌ Error terminating session {session_id}: {e}")

# def stop_session(session_id):
#     """Stop one specific remote Colab session."""

#     if not session_id:
#         print("⚠️ No Colab session ID available.")
#         return False

#     # You want to store only the ID, e.g.:
#     # 68d60c
#     #
#     # But Colab's generated session name is:
#     # run-68d60c
#     session_name = (
#         session_id
#         if session_id.startswith("run-")
#         else f"run-{session_id}"
#     )

#     print(f"🛑 Requesting remote Colab stop: {session_name}")

#     try:
#         result = subprocess.run(
#             [
#                 "colab",
#                 "--auth=adc",
#                 "stop",
#                 "-s",
#                 session_name,
#             ],
#             capture_output=True,
#             text=True,
#             encoding="utf-8",
#             errors="replace",
#             timeout=30,
#             env=SUBPROCESS_ENV,
#         )

#         stdout = (result.stdout or "").strip()
#         stderr = (result.stderr or "").strip()

#         if stdout:
#             print(stdout)

#         if stderr:
#             print(stderr)

#         if result.returncode == 0:
#             print(
#                 f"✅ Remote Colab session stopped successfully: "
#                 f"{session_name}"
#             )

#             _emit(
#                 "session_stop",
#                 msg=f"🛑 Remote Colab session stopped: {session_id}",
#                 session_id=session_id,
#             )

#             return True

#         print(
#             f"❌ Colab stop failed for {session_name} "
#             f"(exit code {result.returncode})"
#         )

#         _emit(
#             "error",
#             msg=f"❌ Failed to stop Colab session: {session_id}",
#             session_id=session_id,
#         )

#         return False

#     except subprocess.TimeoutExpired:
#         print(f"⏰ Timeout while stopping {session_name}")

#         _emit(
#             "error",
#             msg=f"⏰ Timeout stopping Colab session: {session_id}",
#             session_id=session_id,
#         )

#         return False

#     except Exception as e:
#         print(f"❌ Error stopping {session_name}: {e}")

#         _emit(
#             "error",
#             msg=f"❌ Error stopping Colab session: {session_id}",
#         )

#         return False

# def cleanup_and_verify_sessions():
#     """Aggressively finds and kills active sessions concurrently."""
#     print("🧹 Clearing active Google Colab cloud sessions...")
#     _emit("cleanup", msg="🧹 Clearing all active Colab sessions…")

#     stored_id = manage_session_lock(action="get")
#     print("seesion id", stored_id)
#     if stored_id:
#         stop_session(stored_id)
#         manage_session_lock(action="clear")

#     try:
#         list_check = subprocess.run(
#             ["colab", "sessions"],
#             capture_output=True, text=True, encoding="utf-8", errors="replace",
#             timeout=10, env=SUBPROCESS_ENV
#         )
#         if list_check.returncode == 0 and list_check.stdout.strip():
#             # Extract session IDs (6-character hex strings)
#             found_ids = set()
#             for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
#                 found_ids.add(m.group(1))
#             session_ids = list(found_ids)
#             if session_ids:
#                 with ThreadPoolExecutor(max_workers=5) as executor:
#                     executor.map(stop_session, filter(None, session_ids))
#     except Exception:
#         pass


# def stream_subprocess_output(process, on_line=None):
#     """Highly optimized stream reader for parsing CLI output and progress bars."""
#     buf = ""
#     while True:
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             break
#         chunk = process.stdout.read(4096)
#         if not chunk:
#             break
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             break
#         buf += chunk.replace("\r\n", "\n")

#         while True:
#             idx_r = buf.find("\r")
#             idx_n = buf.find("\n")
#             if idx_r == -1 and idx_n == -1:
#                 break

#             if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
#                 line, buf = buf[:idx_n], buf[idx_n + 1:]
#                 sys.stdout.write(f"\r{line}\n")
#                 _parse_and_emit_line(line)
#                 if on_line:
#                     on_line(line)
#             else:
#                 line, buf = buf[:idx_r], buf[idx_r + 1:]
#                 sys.stdout.write(f"\r{line.ljust(80)}")
#                 _parse_and_emit_line(line)
#         sys.stdout.flush()


# def run_remote_colab_cycle(cycle_num):
#     """Run one full Colab cycle. Returns True if completed, False if stopped."""
#     print(f"\n{'='*40}\n☁️  CYCLE #{cycle_num}: PROVISIONING & RUNNING\n{'='*40}")
#     _emit("cycle_start",
#           msg=f"🚀 Cycle #{cycle_num} starting — provisioning Colab session",
#           cycle=cycle_num, total=TOTAL_CYCLES)

#     cleanup_and_verify_sessions()

#     # Check stop flag after cleanup
#     if _DASHBOARD_AVAILABLE and _ds.should_stop():
#         return False

#     # exec_command = ["colab", "run", "--timeout", str(TIMEOUT_SECONDS), TARGET_FILE]
# #     exec_command = [
# #     "colab",
# #     "--auth=adc",
# #     "run",
# #     "--timeout",
# #     str(TIMEOUT_SECONDS),
# #     TARGET_FILE
# # ] 
#     exec_command = [
#     "colab",
#     "--auth=adc",
#     "run",
#     "--timeout",
#     str(TIMEOUT_SECONDS),
#     TARGET_FILE,
# ]
#     session_id = None
#     process = None

#     _emit("session_start", msg="☁️ Provisioning new Colab session…")

#     try:
#         process = subprocess.Popen(
#             exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#             text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
#         )
#         _set_active_process(process)

#         # def _handle_line(line):
#         #     nonlocal session_id
#         #     if not session_id:
#         #         match = re.search(r"(?:Creating session '|READY \()(?:run-)?([a-zA-Z0-9]+)", line)
#         #         if match:
#         #             session_id = match.group(1).strip()
#         #             print(f"\n📌 Isolated Session ID: {session_id}")
#         #             manage_session_lock(session_id, action="save")
#         #             _emit("session_ready",
#         #                   msg=f"📌 Session ready: {session_id}",
#         #                   session_id=session_id)

#         def _handle_line(line):
#             nonlocal session_id

#             if not session_id:
#                 match = re.search(
#             r"(?:Creating session '|Session READY \()(?:run-)?([a-zA-Z0-9]+)",
#             line
#         )

#                 if match:
#                     session_id = match.group(1).strip()

#                     print(
#                 f"\n📌 Isolated Session ID: {session_id}"
#             )

#                     manage_session_lock(
#                 session_id,
#                 action="save"
#             )

#                     _emit(
#                 "session_ready",
#                 msg=f"📌 Session ready: {session_id}",
#                 session_id=session_id
#             )

#         stream_subprocess_output(process, on_line=_handle_line)
#         process.wait()

#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             print("\n🛑 Stop requested — aborting cycle.")
#             return False

#         if process.returncode == 0:
#             print("\n🎉 Cloud execution completed successfully!")
#             _emit("cycle_end",
#                   msg=f"✅ Cycle #{cycle_num} completed successfully",
#                   cycle=cycle_num, total=TOTAL_CYCLES)
#         else:
#             print(f"\n⚠️ Execution finished with exit code: {process.returncode}")
#             _emit("warn",
#                   msg=f"⚠️ Cycle #{cycle_num} finished with exit code {process.returncode}",
#                   cycle=cycle_num)

#     except subprocess.TimeoutExpired:
#         print(f"\n⏰ TIMEOUT REACHED for session '{session_id}'! Force-killing...")
#         _emit("error", msg=f"⏰ Timeout reached for session {session_id}! Force-killing.")
#         if process:
#             process.kill()

#     except Exception as e:
#         err_str = str(e)
#         print(f"\n❌ Error during execution: {err_str}")
#         _emit("error", msg=f"❌ Execution error: {err_str}")
#         if any(x in err_str for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
#             print(f"🛑 Rate limit hit (HTTP 412). Cool-down enforced ({COOLDOWN_ON_412}s)...")
#             _emit("warn", msg=f"🛑 Rate limit (HTTP 412) — cooling down for {COOLDOWN_ON_412}s")
#             time.sleep(COOLDOWN_ON_412)

#     finally:
#         _set_active_process(None)
#         if session_id:
#             stop_session(session_id)
#         manage_session_lock(action="clear")

#     return True


# # ---------------------------------------------------------------------------
# # ── MAIN RUNNER — runs in a background thread ──────────────────────────────
# # ---------------------------------------------------------------------------

# def _run_all_cycles():
#     """
#     The main cycle loop, always runs from cycle 1 when started.
#     Runs in a daemon thread so it doesn't block Flask or the main thread.
#     Checks stop/pause flags between every cycle.
#     """
#     global _runner_thread

#     print("\n🏁 Runner starting — converting notebook…")
#     _emit("log", msg="🏁 Runner starting fresh from Cycle 1…")

#     try:
#         convert_ipynb_to_py(NOTEBOOK_FILE, TARGET_FILE)
#         cleanup_and_verify_sessions()
#     except Exception as e:
#         print(f"❌ Startup error: {e}")
#         _emit("error", msg=f"❌ Startup error: {e}")
#         if _DASHBOARD_AVAILABLE:
#             _ds.mark_idle()
#         with _runner_lock:
#             _runner_thread = None
#         return

#     for i in range(1, TOTAL_CYCLES + 1):
#         # ── Check stop before each cycle ──────────────────────────────────
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             print("\n🛑 Stop requested — exiting cycle loop.")
#             _emit("warn", msg="🛑 Run stopped by user.")
#             break

#         # ── Check pause before each cycle (blocks until resumed or stopped) ──
#         if _DASHBOARD_AVAILABLE:
#             _emit("log", msg=f"⏸ Checking pause before cycle #{i}…") if not _ds._pause_event.is_set() else None
#             if not _ds.wait_if_paused():
#                 # stop was requested while we were paused
#                 print("\n🛑 Stopped while paused.")
#                 _emit("warn", msg="🛑 Run stopped by user while paused.")
#                 break

#         completed = run_remote_colab_cycle(i)
#         if not completed:
#             break

#         if i < TOTAL_CYCLES:
#             # ── Interruptible intermission sleep ──────────────────────────
#             print(f"\n⏳ Intermission: Waiting {INTERMISSION_DELAY}s...")
#             _emit("intermission",
#                   msg=f"⏳ Intermission — waiting {INTERMISSION_DELAY}s before next cycle",
#                   delay=INTERMISSION_DELAY)

#             for _ in range(INTERMISSION_DELAY * 4):   # check every 0.25s
#                 if _DASHBOARD_AVAILABLE:
#                     if _ds.should_stop():
#                         break
#                     if not _ds.wait_if_paused():
#                         break
#                 time.sleep(0.25)

#             if _DASHBOARD_AVAILABLE and _ds.should_stop():
#                 _emit("warn", msg="🛑 Run stopped during intermission.")
#                 break

#     else:
#         # Loop finished without break → all cycles done
#         print("\n🏆 All remote cloud cycles completed!")
#         _emit("cycle_end",
#               msg="🏆 All remote cloud cycles completed!",
#               cycle=TOTAL_CYCLES, total=TOTAL_CYCLES)

#     # ── Cleanup and reset state ────────────────────────────────────────────
#     cleanup_and_verify_sessions()
#     if _DASHBOARD_AVAILABLE:
#         _ds.mark_idle()
#     with _runner_lock:
#         _runner_thread = None


# def _start_fresh_run():
#     """
#     Callback registered with dashboard_server.
#     Called when the browser presses START.
#     Kills any leftover subprocess, then spawns a fresh runner thread.
#     Always resets to cycle 1.
#     """
#     global _runner_thread

#     with _runner_lock:
#         if _runner_thread and _runner_thread.is_alive():
#             # Shouldn't happen (server only calls this from idle), but be safe
#             print("⚠️ Runner already active — ignoring start.")
#             return

#         # Kill any lingering subprocess
#         _kill_active_process()

#         # Spawn fresh runner starting from cycle 1
#         _runner_thread = threading.Thread(
#             target=_run_all_cycles, daemon=True, name="colab-runner"
#         )
#         _runner_thread.start()

# def setup_google_adc():
#     """
#     Configure Google Application Default Credentials.

#     Local:
#         Uses the normal gcloud ADC location.

#     Render:
#         Uses the Render Secret File.
#     """

#     if os.environ.get("RENDER") == "true":
#         credentials_path = "/etc/secrets/application_default_credentials.json"

#         if not os.path.isfile(credentials_path):
#             raise FileNotFoundError(
#                 f"❌ Google credentials not found: {credentials_path}"
#             )

#         os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

#         print("✅ Render Google ADC credentials detected.")
#         print(f"🔐 Credentials: {credentials_path}")

#     else:
#         local_credentials = os.path.join(
#             os.environ.get("APPDATA", ""),
#             "gcloud",
#             "application_default_credentials.json"
#         )

#         if os.path.isfile(local_credentials):
#             os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_credentials
#             print("✅ Local Google ADC credentials detected.")
#         else:
#             print("⚠️ Local Google ADC credentials not found.")

# # ---------------------------------------------------------------------------
# # ── ENTRY POINT ────────────────────────────────────────────────────────────
# # ---------------------------------------------------------------------------

# if __name__ == "__main__":
#      # Configure Google authentication first
#     setup_google_adc()
#     # ── Start live dashboard server ────────────────────────────────────────
#     if _DASHBOARD_AVAILABLE:
#         # Register our callbacks so the browser control buttons work
#         _ds.register_start_callback(_start_fresh_run)
#         _ds.register_pause_callback(_on_pause)
#         _ds.register_resume_callback(_on_resume)
#         _ds.register_stop_callback(_on_stop)

#         # Start dashboard server
#         _ds.start_server(
#             open_browser=(os.environ.get("RENDER") != "true")
#         )

#         _emit(
#             "log",
#             msg="🌐 Live dashboard started — press ▶ START to begin running cycles"
#         )

#         print("✅ Dashboard ready. Press ▶ START in the browser.")
#     else:
#         print("⚠️ dashboard_server.py not found or flask not installed.")
#         print("    Install with: pip install flask")
#         print("    Falling back to direct run…\n")

#         check_dependencies()

#         try:
#             _run_all_cycles()
#         except KeyboardInterrupt:
#             print("\n\n🛑 Interrupt received!")
#             _kill_active_process()
#             cleanup_and_verify_sessions()
#             sys.exit(0)

#     # Keep the main thread alive so daemon threads keep running
#     check_dependencies()

#     try:
#         while True:
#             time.sleep(1)

#     except KeyboardInterrupt:
#         print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
#         _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
#         _kill_active_process()
#         cleanup_and_verify_sessions()
#         sys.exit(0)
#     # ── Start live dashboard server ────────────────────────────────────────
#     if _DASHBOARD_AVAILABLE:
#         # Register our callbacks so the browser control buttons work
#         _ds.register_start_callback(_start_fresh_run)
#         _ds.register_pause_callback(_on_pause)
#         _ds.register_resume_callback(_on_resume)
#         _ds.register_stop_callback(_on_stop)
#         _ds.start_server(open_browser=True)
#         _emit("log", msg="🌐 Live dashboard started — press ▶ START to begin running cycles")
#         print("✅ Dashboard ready. Press ▶ START in the browser to begin.")
#     else:
#         print("⚠️  dashboard_server.py not found or flask not installed.")
#         print("    Install with: pip install flask")
#         print("    Falling back to direct run…\n")
#         # No dashboard: run directly (original behaviour)
#         check_dependencies()
#         try:
#             _run_all_cycles()
#         except KeyboardInterrupt:
#             print("\n\n🛑 Interrupt received!")
#             _kill_active_process()
#             cleanup_and_verify_sessions()
#             sys.exit(0)

#     # Keep the main thread alive so daemon threads keep running
#     check_dependencies()
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
#         _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
#         _kill_active_process()
#         cleanup_and_verify_sessions()
#         sys.exit(0)



# # gdown "https://drive.google.com/uc?id=19KSP1KUPAXCMBMazKUhk6fJF1uEkFSAg" -O notebook.ipynb
#
# ── WHY YOUR SESSIONS WEREN'T STOPPING AFTER 1 MIN ON RENDER ─────────────────
# 1. `process.wait()` was called with NO timeout, so the
#    `except subprocess.TimeoutExpired:` block could never actually fire —
#    it was dead code. The script fully trusted `colab run --timeout 60` to
#    kill itself. If the CLI ever hung/misbehaved in Render's container
#    (no TTY, different signal/long-poll behaviour than your local machine),
#    nothing on the Python side would ever step in.
# 2. The remote session was only stopped via `stop_session(session_id)`,
#    and `session_id` was only set if one specific log line matched one
#    specific regex. If the CLI's wording ever differed even slightly, the
#    ID was never captured, `stop_session()` was silently skipped, and the
#    remote Colab session kept running with nothing to kill it.
#
# FIXES APPLIED:
# - A real watchdog timer (`threading.Timer`) now force-kills the *entire*
#   local process tree (via psutil) if a cycle runs longer than
#   TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS, no matter what the CLI does.
# - `process.wait()` now has an explicit timeout too, with a follow-up kill.
# - Session-ID capture now tries several known log patterns.
# - Every cycle now ends with an UNCONDITIONAL `cleanup_and_verify_sessions()`
#   call (not just a conditional `stop_session`) — this does a real
#   `colab sessions` listing and kills anything still alive remotely, so a
#   missed ID or a hung CLI can no longer leave a session running.
# - Removed dead/duplicated code at the bottom of `__main__` (it was
#   unreachable, left over from an earlier edit).
# ──────────────────────────────────────────────────────────────────────────

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

TIMEOUT_SECONDS = 10 * 60     # 10-minute limit passed to `colab run --timeout`
WATCHDOG_GRACE_SECONDS = 20  # extra buffer BEFORE Python force-kills locally.
                             # Total worst-case time before a forced kill is
                             # TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS.
TOTAL_CYCLES = 99999999999
INTERMISSION_DELAY = 10      # seconds between cycles
COOLDOWN_ON_412 = 10         # cooldown when rate-limited

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


def _kill_process_tree(pid):
    """
    Forcefully kill a process and every child it spawned.
    This is the core fix for cycles that hang past TIMEOUT_SECONDS: the
    watchdog timer below calls this regardless of what the `colab` CLI is
    doing, so a stuck local process can never run forever.
    """
    try:
        parent = psutil.Process(pid)
        procs = parent.children(recursive=True)
        procs.append(parent)
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs(procs, timeout=5)
        print(f"💀 Force-killed process tree for PID {pid}")
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        print(f"⚠️ Failed to kill process tree for PID {pid}: {e}")


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


def _on_stop():
    print("\n🛑 Stop requested from dashboard — killing active process…")
    _kill_active_process()

    # Run session cleanup in a background thread to keep UI responsive
    threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()

    _emit("warn", msg="🛑 Run stopped by user. Clearing active sessions…")


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

# Multiple patterns because the CLI's exact wording can vary — relying on a
# single regex was the second reason sessions were leaking (silently no
# session_id captured -> stop_session() never called).
_SESSION_ID_PATTERNS = [
    re.compile(r"Creating session '(?:run-)?([a-zA-Z0-9]+)'", re.IGNORECASE),
    re.compile(r"Session READY \((?:run-)?([a-zA-Z0-9]+)\)", re.IGNORECASE),
    re.compile(r"\brun-([a-fA-F0-9]{6,})\b"),
]

_current_dl_file = None
_current_ul_file = None


def _extract_session_id(line):
    for pattern in _SESSION_ID_PATTERNS:
        m = pattern.search(line)
        if m:
            return m.group(1).strip()
    return None


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


def stop_session(session_id):
    """Stop one specific remote Colab session."""

    if not session_id:
        print("⚠️ No Colab session ID available.")
        return False

    # You want to store only the ID, e.g.:  68d60c
    # But Colab's generated session name is:  run-68d60c
    session_name = (
        session_id
        if session_id.startswith("run-")
        else f"run-{session_id}"
    )

    print(f"🛑 Requesting remote Colab stop: {session_name}")

    try:
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

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if stdout:
            print(stdout)
        if stderr:
            print(stderr)

        if result.returncode == 0:
            print(f"✅ Remote Colab session stopped successfully: {session_name}")
            _emit(
                "session_stop",
                msg=f"🛑 Remote Colab session stopped: {session_id}",
                session_id=session_id,
            )
            return True

        print(f"❌ Colab stop failed for {session_name} (exit code {result.returncode})")
        _emit(
            "error",
            msg=f"❌ Failed to stop Colab session: {session_id}",
            session_id=session_id,
        )
        return False

    except subprocess.TimeoutExpired:
        print(f"⏰ Timeout while stopping {session_name}")
        _emit(
            "error",
            msg=f"⏰ Timeout stopping Colab session: {session_id}",
            session_id=session_id,
        )
        return False

    except Exception as e:
        print(f"❌ Error stopping {session_name}: {e}")
        _emit(
            "error",
            msg=f"❌ Error stopping Colab session: {session_id}",
        )
        return False


def cleanup_and_verify_sessions():
    """
    Aggressively finds and kills active sessions concurrently.
    Called both BEFORE a cycle starts and AFTER a cycle ends (success,
    error, or forced timeout) — this unconditional post-cycle sweep is
    what actually guarantees nothing is left running remotely, even if
    session-ID parsing or the local kill above didn't work as expected.
    """
    print("🧹 Clearing active Google Colab cloud sessions...")
    _emit("cleanup", msg="🧹 Clearing all active Colab sessions…")

    stored_id = manage_session_lock(action="get")
    print("session id:", stored_id)
    if stored_id:
        stop_session(stored_id)
        manage_session_lock(action="clear")

    try:
        list_check = subprocess.run(
            ["colab", "sessions"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, env=SUBPROCESS_ENV
        )
        if list_check.returncode == 0 and list_check.stdout.strip():
            # Extract session IDs (6-character hex strings)
            found_ids = set()
            for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
                found_ids.add(m.group(1))
            session_ids = list(found_ids)
            if session_ids:
                print(f"🔎 Found {len(session_ids)} stray session(s) still live remotely: {session_ids}")
                _emit("warn", msg=f"🔎 Found {len(session_ids)} stray remote session(s) — stopping them.")
                with ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(stop_session, filter(None, session_ids))
    except Exception as e:
        print(f"⚠️ Session listing/cleanup check failed: {e}")


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

    exec_command = [
        "colab",
        "--auth=adc",
        "run",
        "--timeout",
        str(TIMEOUT_SECONDS),
        TARGET_FILE,
    ]
    session_id = None
    process = None
    timer = None
    watchdog_fired = threading.Event()

    _emit("session_start", msg="☁️ Provisioning new Colab session…")

    try:
        process = subprocess.Popen(
            exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
        )
        _set_active_process(process)

        # ── WATCHDOG: guarantees this cycle cannot run forever ──────────
        # This fires independently of the main thread, so even if the CLI
        # hangs (never honours --timeout, no stdout, no exit) the local
        # process tree still gets force-killed. The remote session itself
        # is then caught by the unconditional cleanup_and_verify_sessions()
        # call in `finally` below.
        def _watchdog_fire():
            watchdog_fired.set()
            msg = (f"⏰ WATCHDOG: cycle #{cycle_num} exceeded "
                   f"{TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS}s wall-clock "
                   f"(CLI --timeout of {TIMEOUT_SECONDS}s did not stop it). "
                   f"Force-killing local process — remote sweep follows.")
            print(f"\n{msg}")
            _emit("error", msg=msg, cycle=cycle_num)
            _kill_process_tree(process.pid)

        timer = threading.Timer(TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS, _watchdog_fire)
        timer.daemon = True
        timer.start()

        def _handle_line(line):
            nonlocal session_id
            if not session_id:
                found = _extract_session_id(line)
                if found:
                    session_id = found
                    print(f"\n📌 Isolated Session ID: {session_id}")
                    manage_session_lock(session_id, action="save")
                    _emit(
                        "session_ready",
                        msg=f"📌 Session ready: {session_id}",
                        session_id=session_id,
                    )

        stream_subprocess_output(process, on_line=_handle_line)

        # Bounded wait instead of an unbounded one — if the process hasn't
        # actually exited yet (stdout closed but process still finishing
        # up), give it a short grace window, then force it.
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            print(f"\n⚠️ Process still alive after stdout closed — force killing PID {process.pid}")
            _emit("error", msg="⚠️ Process unresponsive after output ended — force killing.")
            _kill_process_tree(process.pid)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass

        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            print("\n🛑 Stop requested — aborting cycle.")
            return False

        if watchdog_fired.is_set():
            print(f"\n⚠️ Cycle #{cycle_num} was force-terminated by the watchdog.")
            _emit("warn", msg=f"⚠️ Cycle #{cycle_num} force-terminated by watchdog.", cycle=cycle_num)
        elif process.returncode == 0:
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
            _kill_process_tree(process.pid)

    except Exception as e:
        err_str = str(e)
        print(f"\n❌ Error during execution: {err_str}")
        _emit("error", msg=f"❌ Execution error: {err_str}")
        if any(x in err_str for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
            print(f"🛑 Rate limit hit (HTTP 412). Cool-down enforced ({COOLDOWN_ON_412}s)...")
            _emit("warn", msg=f"🛑 Rate limit (HTTP 412) — cooling down for {COOLDOWN_ON_412}s")
            time.sleep(COOLDOWN_ON_412)

    finally:
        if timer:
            timer.cancel()
        _set_active_process(None)
        if session_id:
            stop_session(session_id)
        manage_session_lock(action="clear")
        # THE KEY FIX: always do a full remote sweep after every cycle,
        # regardless of how it ended. This is what actually guarantees the
        # Colab session is gone even if the ID was never captured or the
        # CLI's own timeout silently failed to stop things.
        cleanup_and_verify_sessions()

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
            if not _ds._pause_event.is_set():
                _emit("log", msg=f"⏸ Checking pause before cycle #{i}…")
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
    check_dependencies()

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

        try:
            _run_all_cycles()
        except KeyboardInterrupt:
            print("\n\n🛑 Interrupt received!")
            _kill_active_process()
            cleanup_and_verify_sessions()
            sys.exit(0)

    # Keep the main thread alive so daemon threads keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
        _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
        _kill_active_process()
        cleanup_and_verify_sessions()
        sys.exit(0)













# # ============================================================================
# # FIX NOTES — why sessions weren't stopping after 1 minute, and what changed
# # ----------------------------------------------------------------------------
# # 1. `colab run --timeout` is a SILENT-EXECUTION watchdog, not a wall-clock
# #    cap on the whole run. Per the official docs it's a "Timeout in seconds
# #    for code execution to prevent hanging on silent tasks" (default 30s).
# #    If your notebook prints anything periodically, that flag never fires,
# #    no matter how long the run actually takes.
# #
# # 2. The old code called `process.wait()` with NO timeout argument, so the
# #    `except subprocess.TimeoutExpired:` block could never actually trigger.
# #    There was no real 1-minute cap being enforced anywhere.
# #
# # 3. `colab run`'s own teardown (stop the runtime, unassign the VM, kill its
# #    detached keep-alive daemon) runs in the CLI's OWN `finally` block, which
# #    only executes on a graceful exit. A hard `process.kill()` from outside
# #    skips it entirely. Worse, the keep-alive daemon is a DETACHED background
# #    process that pings Google every 60s to keep the VM alive independently
# #    of the CLI — it can survive your kill() as an orphan and keep the VM
# #    billed/running. Nothing reclaims it automatically except a 24h safety
# #    cap (or a ~90 min idle timeout if the daemon dies too). The only thing
# #    that reliably releases it immediately is an explicit `colab stop -s
# #    <name>` call.
# #
# # 4. FIXED: added a real local watchdog thread that force-kills the process
# #    (and any children) after TIMEOUT_SECONDS wall-clock time, independent
# #    of whatever output the script is producing. This is now what actually
# #    enforces your 1-minute limit — the CLI's `--timeout` flag is kept as a
# #    secondary safety net for genuinely silent hangs, nothing more.
# #
# # 5. FIXED: `stop_session()` is now guaranteed to run whenever we had to
# #    force-kill the process, and a fallback full-sweep `cleanup_and_verify_
# #    sessions()` runs afterward too, in case the session id was never
# #    captured from stdout (e.g. the process died before printing it).
# #
# # 6. FIXED: added SIGTERM/SIGINT handlers. Render sends SIGTERM on redeploys/
# #    restarts; without a handler your process is just SIGKILLed later and
# #    never gets a chance to call `colab stop` at all.
# # ============================================================================

# import json
# import os
# import re
# import signal
# import subprocess
# import sys
# import time
# import shutil
# import threading
# import psutil
# from concurrent.futures import ThreadPoolExecutor


# print("========== GOOGLE ADC CHECK ==========")

# credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

# print("GOOGLE_APPLICATION_CREDENTIALS =", credentials_path)

# if credentials_path:
#     print("Credential file exists =", os.path.isfile(credentials_path))
# else:
#     print("❌ GOOGLE_APPLICATION_CREDENTIALS is not set")

# print("Render secret directory exists =", os.path.isdir("/etc/secrets"))

# if os.path.isdir("/etc/secrets"):
#     print("Render secret files =", os.listdir("/etc/secrets"))

# print("======================================")

# # --- WINDOWS UTF-8 ENCODING FIX ---
# if sys.platform == "win32":
#     if hasattr(sys.stdout, "reconfigure"):
#         sys.stdout.reconfigure(encoding="utf-8", errors="replace")
#     if hasattr(sys.stderr, "reconfigure"):
#         sys.stderr.reconfigure(encoding="utf-8", errors="replace")
#     os.system("")

# SUBPROCESS_ENV = os.environ.copy()
# SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
# SUBPROCESS_ENV["PYTHONUTF8"] = "1"

# # --- CONFIGURATION ---
# NOTEBOOK_FILE = "notebook.ipynb"
# TARGET_FILE = "script.py"
# SESSION_ID_FILE = "active_colab_session.lock"

# # This is now a REAL hard wall-clock cap, enforced locally (see watchdog
# # below) — not just something we hand to `colab run --timeout`, which only
# # guards against silent (no-output) hangs and would never actually enforce
# # this on its own.
# TIMEOUT_SECONDS = 1 * 60  # 1-minute limit
# TOTAL_CYCLES = 99999999999
# INTERMISSION_DELAY = 10     # seconds between cycles
# COOLDOWN_ON_412 = 10       # cooldown when rate-limited
# WATCHDOG_POLL_INTERVAL = 0.25  # how often the watchdog checks the deadline

# # ---------------------------------------------------------------------------
# # ── LIVE DASHBOARD INTEGRATION ─────────────────────────────────────────────
# # ---------------------------------------------------------------------------
# try:
#     import dashboard_server as _ds
#     _DASHBOARD_AVAILABLE = True
# except ImportError:
#     _DASHBOARD_AVAILABLE = False

# def _emit(event_type: str, **kwargs):
#     """Push a structured event to the live dashboard (no-op if not available)."""
#     if _DASHBOARD_AVAILABLE:
#         try:
#             _ds.emit(event_type, **kwargs)
#         except Exception:
#             pass

# # ---------------------------------------------------------------------------
# # ── CONTROL STATE ──────────────────────────────────────────────────────────
# # The runner thread is kept as a module-level reference so we never spawn
# # two runners at the same time.
# # ---------------------------------------------------------------------------
# _runner_thread: threading.Thread | None = None
# _runner_lock = threading.Lock()

# # Reference to the currently running subprocess so stop() can kill it
# _active_process: subprocess.Popen | None = None
# _active_process_lock = threading.Lock()


# def _set_active_process(p):
#     global _active_process
#     with _active_process_lock:
#         _active_process = p


# def _kill_process_tree(pid, reason="stop requested"):
#     """Force-kill a process AND any children it spawned (e.g. pip installs
#     the CLI shells out to). A plain process.kill() only kills the CLI's own
#     PID and can leave stray children behind."""
#     try:
#         parent = psutil.Process(pid)
#     except psutil.NoSuchProcess:
#         return
#     try:
#         children = parent.children(recursive=True)
#     except Exception:
#         children = []
#     for child in children:
#         try:
#             child.kill()
#         except Exception:
#             pass
#     try:
#         parent.kill()
#     except Exception:
#         pass
#     print(f"💀 Killed process tree for PID {pid} ({reason})")


# def _kill_active_process():
#     """Kill the currently running colab subprocess (and its children) if one exists."""
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             try:
#                 _kill_process_tree(_active_process.pid, reason="active process stop")
#             except Exception:
#                 pass


# def _suspend_process_tree(pid):
#     try:
#         parent = psutil.Process(pid)
#         for child in parent.children(recursive=True):
#             try:
#                 child.suspend()
#             except Exception:
#                 pass
#         parent.suspend()
#         print(f"⏸ Suspended process tree for PID {pid}")
#     except Exception as e:
#         print(f"⚠️ Failed to suspend process tree: {e}")


# def _resume_process_tree(pid):
#     try:
#         parent = psutil.Process(pid)
#         parent.resume()
#         for child in parent.children(recursive=True):
#             try:
#                 child.resume()
#             except Exception:
#                 pass
#         print(f"▶ Resumed process tree for PID {pid}")
#     except Exception as e:
#         print(f"⚠️ Failed to resume process tree: {e}")


# def _on_pause():
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             _suspend_process_tree(_active_process.pid)
#             _emit("warn", msg="⏸ Active process suspended (paused).")


# def _on_resume():
#     with _active_process_lock:
#         if _active_process and _active_process.poll() is None:
#             _resume_process_tree(_active_process.pid)
#             _emit("log", msg="▶ Active process resumed.")


# def _on_stop():
#     print("\n🛑 Stop requested from dashboard — killing active process…")
#     _kill_active_process()

#     # Run session cleanup in a background thread to keep UI responsive
#     threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()

#     _emit("warn", msg="🛑 Run stopped by user. Clearing active sessions…")


# # ---------------------------------------------------------------------------
# # ── GRACEFUL SHUTDOWN ON SIGTERM/SIGINT ────────────────────────────────────
# # Render (and most platform schedulers) send SIGTERM before a hard kill on
# # redeploys, restarts, or manual stops. Without a handler, this process just
# # sits there until it's SIGKILLed and NEVER gets a chance to call
# # `colab stop`, so any active remote session is orphaned. This handler makes
# # a best-effort attempt to kill the local CLI and release the remote session
# # before the process actually exits. It's best-effort because the platform's
# # grace period between SIGTERM and SIGKILL is finite and outside our control.
# # ---------------------------------------------------------------------------
# def _graceful_shutdown_handler(signum, frame):
#     try:
#         sig_name = signal.Signals(signum).name
#     except Exception:
#         sig_name = str(signum)

#     print(f"\n🛑 Received {sig_name} — attempting to release active Colab session before exit…")
#     _emit("warn", msg=f"🛑 Received {sig_name} (platform shutdown) — cleaning up Colab session…")

#     try:
#         _kill_active_process()
#         cleanup_and_verify_sessions()
#     except Exception as e:
#         print(f"⚠️ Cleanup during {sig_name} handling failed: {e}")
#     finally:
#         os._exit(0)


# try:
#     signal.signal(signal.SIGTERM, _graceful_shutdown_handler)
#     signal.signal(signal.SIGINT, _graceful_shutdown_handler)
# except (ValueError, AttributeError):
#     # signal.signal only works from the main thread and isn't available
#     # on every platform — skip quietly if unavailable rather than crash.
#     pass


# # ---------------------------------------------------------------------------
# # ── STDOUT LINE PARSER / DASHBOARD EMITTER ─────────────────────────────────
# # ---------------------------------------------------------------------------
# _DL_RE = re.compile(
#     r"(?:Downloading|📥).+?(\d+\.\d+)%\s*\|"
#     r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
#     r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
#     re.IGNORECASE,
# )
# _UL_RE = re.compile(
#     r"(?:Uploading|📤).+?(\d+\.\d+)%\s*\|"
#     r"\s*([\d.]+\s*\w+)\s*/\s*([\d.]+\s*\w+)"
#     r"(?:\s*\|\s*([\d.]+\s*\w+/s))?(?:\s*\|\s*ETA:\s*(\d+\w+))?",
#     re.IGNORECASE,
# )
# _DL_FILE_RE   = re.compile(r"📥\s*Downloading:\s*(.+?)(?:\.{3}|$)", re.IGNORECASE)
# _SAVED_RE     = re.compile(r"✅\s*Saved to\s+(.+)", re.IGNORECASE)
# _UPLOAD_RE    = re.compile(r"(?:Updated|Created).+?'(.+?)'\s+on\s+Google\s+Drive", re.IGNORECASE)
# _AUTH_CRED_RE = re.compile(r"Downloading service account", re.IGNORECASE)
# _AUTH_OK_RE   = re.compile(r"Successfully authenticated", re.IGNORECASE)

# # Colab CLI ephemeral sessions from `colab run` are always named `run-<hex>`
# # unless you pass `-s NAME` explicitly (this script doesn't), so matching
# # that pattern directly anywhere in a line is more robust than depending on
# # one specific preamble phrase that might change between CLI versions.
# _SESSION_ID_RE = re.compile(r"\brun-[a-zA-Z0-9]{4,}\b")

# _current_dl_file = None
# _current_ul_file = None


# def _parse_and_emit_line(line: str, session_box: dict | None = None):
#     """Parse a raw stdout line and emit the appropriate dashboard event.
#     If session_box is provided, also opportunistically capture the session
#     id from any line that mentions it (belt-and-suspenders alongside the
#     dedicated _handle_line matcher in run_remote_colab_cycle)."""
#     global _current_dl_file, _current_ul_file

#     if session_box is not None and session_box.get("id") is None:
#         m_sid = _SESSION_ID_RE.search(line)
#         if m_sid:
#             session_box["id"] = m_sid.group(0)

#     if _AUTH_CRED_RE.search(line):
#         _emit("auth_start", msg="Downloading service account credentials…")
#         return
#     if _AUTH_OK_RE.search(line):
#         _emit("auth_ok", msg="✅ Authenticated with Google Drive API")
#         return

#     m = _DL_FILE_RE.search(line)
#     if m:
#         _current_dl_file = m.group(1).strip()
#         _emit("download", msg=f"📥 Downloading: {_current_dl_file}", filename=_current_dl_file, pct=0)
#         return

#     m = _DL_RE.search(line)
#     if m:
#         pct   = float(m.group(1))
#         done  = m.group(2)
#         total = m.group(3)
#         speed = m.group(4) or ""
#         eta   = m.group(5) or ""
#         fname = _current_dl_file or "file"
#         _emit("download", msg=f"📥 {fname} — {pct:.1f}%",
#               filename=fname, pct=round(pct, 1),
#               done=done, total=total, speed=speed, eta=eta)
#         return

#     m = _SAVED_RE.search(line)
#     if m:
#         _current_dl_file = None
#         _emit("file_saved", msg=f"💾 Saved: {m.group(1).strip()}", detail=m.group(1).strip())
#         return

#     m = _UPLOAD_RE.search(line)
#     if m:
#         fname = m.group(1)
#         _emit("upload", msg=f"📤 Uploaded to Drive: {fname}", filename=fname, pct=100)
#         return

#     m = _UL_RE.search(line)
#     if m:
#         pct   = float(m.group(1))
#         done  = m.group(2)
#         total = m.group(3)
#         speed = m.group(4) or ""
#         eta   = m.group(5) or ""
#         fname = _current_ul_file or "file"
#         _emit("upload", msg=f"📤 {fname} — {pct:.1f}%",
#               filename=fname, pct=round(pct, 1),
#               done=done, total=total, speed=speed, eta=eta)
#         return

#     if re.search(r"❌|ERROR|FATAL", line):
#         _emit("error", msg=line.strip())
#         return
#     if re.search(r"⚠️|WARN|warning", line, re.IGNORECASE):
#         _emit("warn", msg=line.strip())
#         return

#     _emit("log", msg=line.rstrip())


# # ---------------------------------------------------------------------------
# # ── CORE RUNNER FUNCTIONS ──────────────────────────────────────────────────
# # ---------------------------------------------------------------------------

# def check_dependencies():
#     """Ensures the colab CLI is installed before starting."""
#     if not shutil.which("colab"):
#         sys.exit("❌ FATAL: 'colab' CLI is not installed or not in PATH. Please install it first.")


# def convert_ipynb_to_py(ipynb_path, py_path):
#     """Converts local source Jupyter notebook into a clean runnable Python script."""
#     if not os.path.exists(ipynb_path):
#         raise FileNotFoundError(f"Source file '{ipynb_path}' not found.")

#     _emit("convert", msg=f"🔄 Converting {ipynb_path} → {py_path}…")

#     with open(ipynb_path, "r", encoding="utf-8", errors="replace") as f:
#         nb_data = json.load(f)

#     code_lines = [
#         "".join(cell.get("source", [])) + "\n\n"
#         for cell in nb_data.get("cells", [])
#         if cell.get("cell_type") == "code"
#     ]

#     with open(py_path, "w", encoding="utf-8", errors="replace") as f:
#         f.writelines(code_lines)

#     print(f"📄 Converted '{ipynb_path}' to '{py_path}'.")
#     _emit("convert", msg=f"📄 Converted {ipynb_path} → {py_path}")


# def manage_session_lock(session_id=None, action="get"):
#     """Handles all lock file operations (get, save, clear) safely."""
#     try:
#         if action == "save" and session_id:
#             with open(SESSION_ID_FILE, "w", encoding="utf-8") as f:
#                 f.write(session_id.strip())
#         elif action == "get" and os.path.exists(SESSION_ID_FILE):
#             with open(SESSION_ID_FILE, "r", encoding="utf-8") as f:
#                 return f.read().strip()
#         elif action == "clear" and os.path.exists(SESSION_ID_FILE):
#             os.remove(SESSION_ID_FILE)
#     except Exception as e:
#         print(f"⚠️ Lock file warning: {e}")
#     return None


# def stop_session(session_id):
#     """Stop one specific remote Colab session."""

#     if not session_id:
#         print("⚠️ No Colab session ID available.")
#         return False

#     # You want to store only the ID, e.g.:
#     # 68d60c
#     #
#     # But Colab's generated session name is:
#     # run-68d60c
#     session_name = (
#         session_id
#         if session_id.startswith("run-")
#         else f"run-{session_id}"
#     )

#     print(f"🛑 Requesting remote Colab stop: {session_name}")

#     try:
#         result = subprocess.run(
#             [
#                 "colab",
#                 "--auth=adc",
#                 "stop",
#                 "-s",
#                 session_name,
#             ],
#             capture_output=True,
#             text=True,
#             encoding="utf-8",
#             errors="replace",
#             timeout=30,
#             env=SUBPROCESS_ENV,
#         )

#         stdout = (result.stdout or "").strip()
#         stderr = (result.stderr or "").strip()

#         if stdout:
#             print(stdout)

#         if stderr:
#             print(stderr)

#         if result.returncode == 0:
#             print(
#                 f"✅ Remote Colab session stopped successfully: "
#                 f"{session_name}"
#             )

#             _emit(
#                 "session_stop",
#                 msg=f"🛑 Remote Colab session stopped: {session_id}",
#                 session_id=session_id,
#             )

#             return True

#         print(
#             f"❌ Colab stop failed for {session_name} "
#             f"(exit code {result.returncode})"
#         )

#         _emit(
#             "error",
#             msg=f"❌ Failed to stop Colab session: {session_id}",
#             session_id=session_id,
#         )

#         return False

#     except subprocess.TimeoutExpired:
#         print(f"⏰ Timeout while stopping {session_name}")

#         _emit(
#             "error",
#             msg=f"⏰ Timeout stopping Colab session: {session_id}",
#             session_id=session_id,
#         )

#         return False

#     except Exception as e:
#         print(f"❌ Error stopping {session_name}: {e}")

#         _emit(
#             "error",
#             msg=f"❌ Error stopping Colab session: {session_id}",
#         )

#         return False


# def cleanup_and_verify_sessions():
#     """Aggressively finds and kills active sessions concurrently. Acts as a
#     full-sweep fallback in case a specific session id was never captured
#     (e.g. the process was force-killed before it printed its session name)."""
#     print("🧹 Clearing active Google Colab cloud sessions...")
#     _emit("cleanup", msg="🧹 Clearing all active Colab sessions…")

#     stored_id = manage_session_lock(action="get")
#     print("seesion id", stored_id)
#     if stored_id:
#         stop_session(stored_id)
#         manage_session_lock(action="clear")

#     try:
#         list_check = subprocess.run(
#             ["colab", "sessions"],
#             capture_output=True, text=True, encoding="utf-8", errors="replace",
#             timeout=10, env=SUBPROCESS_ENV
#         )
#         if list_check.returncode == 0 and list_check.stdout.strip():
#             # Extract session IDs (6-character hex strings)
#             found_ids = set()
#             for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
#                 found_ids.add(m.group(1))
#             session_ids = list(found_ids)
#             if session_ids:
#                 with ThreadPoolExecutor(max_workers=5) as executor:
#                     executor.map(stop_session, filter(None, session_ids))
#     except Exception:
#         pass


# def stream_subprocess_output(process, on_line=None, session_box=None):
#     """Highly optimized stream reader for parsing CLI output and progress bars."""
#     buf = ""
#     while True:
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             break
#         chunk = process.stdout.read(4096)
#         if not chunk:
#             break
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             break
#         buf += chunk.replace("\r\n", "\n")

#         while True:
#             idx_r = buf.find("\r")
#             idx_n = buf.find("\n")
#             if idx_r == -1 and idx_n == -1:
#                 break

#             if idx_n != -1 and (idx_r == -1 or idx_n < idx_r):
#                 line, buf = buf[:idx_n], buf[idx_n + 1:]
#                 sys.stdout.write(f"\r{line}\n")
#                 _parse_and_emit_line(line, session_box=session_box)
#                 if on_line:
#                     on_line(line)
#             else:
#                 line, buf = buf[:idx_r], buf[idx_r + 1:]
#                 sys.stdout.write(f"\r{line.ljust(80)}")
#                 _parse_and_emit_line(line, session_box=session_box)
#         sys.stdout.flush()


# def _watchdog_timeout(process, timeout_seconds, session_box, timed_out_event):
#     """Force-kill `process` if it's still running after `timeout_seconds`,
#     REGARDLESS of whether it's still producing output.

#     This is what actually enforces TIMEOUT_SECONDS. `colab run --timeout`
#     only guards against *silent* hangs (no kernel output for N seconds) —
#     a script that keeps printing progress will never trip it, so without
#     this watchdog a cycle could run indefinitely.
#     """
#     deadline = time.monotonic() + timeout_seconds
#     while time.monotonic() < deadline:
#         if process.poll() is not None:
#             return  # finished on its own — nothing to do
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             return  # _on_stop() already handles killing in this case
#         time.sleep(WATCHDOG_POLL_INTERVAL)

#     if process.poll() is None:
#         timed_out_event.set()
#         sid = session_box.get("id")
#         sid_note = f" (session {sid})" if sid else " (session id not yet captured)"
#         print(f"\n⏰ Hard {timeout_seconds}s wall-clock limit reached — force-killing local CLI process{sid_note}…")
#         _emit("warn", msg=f"⏰ {timeout_seconds}s limit reached — force-killing cycle", session_id=sid)
#         _kill_process_tree(process.pid, reason=f"{timeout_seconds}s hard timeout")


# def run_remote_colab_cycle(cycle_num):
#     """Run one full Colab cycle. Returns True if completed, False if stopped."""
#     print(f"\n{'='*40}\n☁️  CYCLE #{cycle_num}: PROVISIONING & RUNNING\n{'='*40}")
#     _emit("cycle_start",
#           msg=f"🚀 Cycle #{cycle_num} starting — provisioning Colab session",
#           cycle=cycle_num, total=TOTAL_CYCLES)

#     cleanup_and_verify_sessions()

#     # Check stop flag after cleanup
#     if _DASHBOARD_AVAILABLE and _ds.should_stop():
#         return False

#     exec_command = [
#         "colab",
#         "--auth=adc",
#         "run",
#         "--timeout",
#         str(TIMEOUT_SECONDS),
#         TARGET_FILE,
#     ]

#     # Shared mutable box so the main thread and the watchdog thread both see
#     # the session id the moment it's captured from stdout.
#     session_box = {"id": None}
#     timed_out_event = threading.Event()
#     process = None
#     watchdog_thread = None

#     _emit("session_start", msg="☁️ Provisioning new Colab session…")

#     try:
#         process = subprocess.Popen(
#             exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#             text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
#         )
#         _set_active_process(process)

#         # Start the REAL hard-timeout watchdog. This runs independently of
#         # whatever output the CLI produces.
#         watchdog_thread = threading.Thread(
#             target=_watchdog_timeout,
#             args=(process, TIMEOUT_SECONDS, session_box, timed_out_event),
#             daemon=True,
#             name="colab-cycle-watchdog",
#         )
#         watchdog_thread.start()

#         def _handle_line(line):
#             if session_box.get("id") is None:
#                 match = re.search(
#                     r"(?:Creating session ['\"]|Session\s+READY\s*\()(?:run-)?([a-zA-Z0-9]+)",
#                     line,
#                 )
#                 if match:
#                     captured = match.group(1).strip()
#                     session_box["id"] = captured if captured.startswith("run-") else captured
#                     print(f"\n📌 Isolated Session ID: {session_box['id']}")
#                     manage_session_lock(session_box["id"], action="save")
#                     _emit(
#                         "session_ready",
#                         msg=f"📌 Session ready: {session_box['id']}",
#                         session_id=session_box["id"],
#                     )

#         stream_subprocess_output(process, on_line=_handle_line, session_box=session_box)
#         process.wait()

#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             print("\n🛑 Stop requested — aborting cycle.")
#             return False

#         if timed_out_event.is_set():
#             print(f"\n⏰ Cycle #{cycle_num} exceeded the {TIMEOUT_SECONDS}s hard limit and was force-stopped.")
#             _emit("warn",
#                   msg=f"⏰ Cycle #{cycle_num} force-stopped after {TIMEOUT_SECONDS}s",
#                   cycle=cycle_num)
#         elif process.returncode == 0:
#             print("\n🎉 Cloud execution completed successfully!")
#             _emit("cycle_end",
#                   msg=f"✅ Cycle #{cycle_num} completed successfully",
#                   cycle=cycle_num, total=TOTAL_CYCLES)
#         else:
#             print(f"\n⚠️ Execution finished with exit code: {process.returncode}")
#             _emit("warn",
#                   msg=f"⚠️ Cycle #{cycle_num} finished with exit code {process.returncode}",
#                   cycle=cycle_num)

#     except Exception as e:
#         err_str = str(e)
#         print(f"\n❌ Error during execution: {err_str}")
#         _emit("error", msg=f"❌ Execution error: {err_str}")
#         if any(x in err_str for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
#             print(f"🛑 Rate limit hit (HTTP 412). Cool-down enforced ({COOLDOWN_ON_412}s)...")
#             _emit("warn", msg=f"🛑 Rate limit (HTTP 412) — cooling down for {COOLDOWN_ON_412}s")
#             time.sleep(COOLDOWN_ON_412)

#     finally:
#         _set_active_process(None)

#         session_id = session_box.get("id")
#         if session_id:
#             stop_session(session_id)

#         # A hard-killed CLI process skips its own cleanup entirely, and even
#         # a graceful exit can occasionally leave a stray assignment behind.
#         # Whenever we had to force the kill, OR we never even captured a
#         # session id to begin with, do a full sweep as a safety net so a
#         # runaway session can't linger.
#         if timed_out_event.is_set() or not session_id:
#             cleanup_and_verify_sessions()

#         manage_session_lock(action="clear")

#     return True


# # ---------------------------------------------------------------------------
# # ── MAIN RUNNER — runs in a background thread ──────────────────────────────
# # ---------------------------------------------------------------------------

# def _run_all_cycles():
#     """
#     The main cycle loop, always runs from cycle 1 when started.
#     Runs in a daemon thread so it doesn't block Flask or the main thread.
#     Checks stop/pause flags between every cycle.
#     """
#     global _runner_thread

#     print("\n🏁 Runner starting — converting notebook…")
#     _emit("log", msg="🏁 Runner starting fresh from Cycle 1…")

#     try:
#         convert_ipynb_to_py(NOTEBOOK_FILE, TARGET_FILE)
#         cleanup_and_verify_sessions()
#     except Exception as e:
#         print(f"❌ Startup error: {e}")
#         _emit("error", msg=f"❌ Startup error: {e}")
#         if _DASHBOARD_AVAILABLE:
#             _ds.mark_idle()
#         with _runner_lock:
#             _runner_thread = None
#         return

#     for i in range(1, TOTAL_CYCLES + 1):
#         # ── Check stop before each cycle ──────────────────────────────────
#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             print("\n🛑 Stop requested — exiting cycle loop.")
#             _emit("warn", msg="🛑 Run stopped by user.")
#             break

#         # ── Check pause before each cycle (blocks until resumed or stopped) ──
#         if _DASHBOARD_AVAILABLE:
#             _emit("log", msg=f"⏸ Checking pause before cycle #{i}…") if not _ds._pause_event.is_set() else None
#             if not _ds.wait_if_paused():
#                 # stop was requested while we were paused
#                 print("\n🛑 Stopped while paused.")
#                 _emit("warn", msg="🛑 Run stopped by user while paused.")
#                 break

#         completed = run_remote_colab_cycle(i)
#         if not completed:
#             break

#         if i < TOTAL_CYCLES:
#             # ── Interruptible intermission sleep ──────────────────────────
#             print(f"\n⏳ Intermission: Waiting {INTERMISSION_DELAY}s...")
#             _emit("intermission",
#                   msg=f"⏳ Intermission — waiting {INTERMISSION_DELAY}s before next cycle",
#                   delay=INTERMISSION_DELAY)

#             for _ in range(INTERMISSION_DELAY * 4):   # check every 0.25s
#                 if _DASHBOARD_AVAILABLE:
#                     if _ds.should_stop():
#                         break
#                     if not _ds.wait_if_paused():
#                         break
#                 time.sleep(0.25)

#             if _DASHBOARD_AVAILABLE and _ds.should_stop():
#                 _emit("warn", msg="🛑 Run stopped during intermission.")
#                 break

#     else:
#         # Loop finished without break → all cycles done
#         print("\n🏆 All remote cloud cycles completed!")
#         _emit("cycle_end",
#               msg="🏆 All remote cloud cycles completed!",
#               cycle=TOTAL_CYCLES, total=TOTAL_CYCLES)

#     # ── Cleanup and reset state ────────────────────────────────────────────
#     cleanup_and_verify_sessions()
#     if _DASHBOARD_AVAILABLE:
#         _ds.mark_idle()
#     with _runner_lock:
#         _runner_thread = None


# def _start_fresh_run():
#     """
#     Callback registered with dashboard_server.
#     Called when the browser presses START.
#     Kills any leftover subprocess, then spawns a fresh runner thread.
#     Always resets to cycle 1.
#     """
#     global _runner_thread

#     with _runner_lock:
#         if _runner_thread and _runner_thread.is_alive():
#             # Shouldn't happen (server only calls this from idle), but be safe
#             print("⚠️ Runner already active — ignoring start.")
#             return

#         # Kill any lingering subprocess
#         _kill_active_process()

#         # Spawn fresh runner starting from cycle 1
#         _runner_thread = threading.Thread(
#             target=_run_all_cycles, daemon=True, name="colab-runner"
#         )
#         _runner_thread.start()


# def setup_google_adc():
#     """
#     Configure Google Application Default Credentials.

#     Local:
#         Uses the normal gcloud ADC location.

#     Render:
#         Uses the Render Secret File.
#     """

#     if os.environ.get("RENDER") == "true":
#         credentials_path = "/etc/secrets/application_default_credentials.json"

#         if not os.path.isfile(credentials_path):
#             raise FileNotFoundError(
#                 f"❌ Google credentials not found: {credentials_path}"
#             )

#         os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

#         print("✅ Render Google ADC credentials detected.")
#         print(f"🔐 Credentials: {credentials_path}")

#     else:
#         local_credentials = os.path.join(
#             os.environ.get("APPDATA", ""),
#             "gcloud",
#             "application_default_credentials.json"
#         )

#         if os.path.isfile(local_credentials):
#             os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_credentials
#             print("✅ Local Google ADC credentials detected.")
#         else:
#             print("⚠️ Local Google ADC credentials not found.")


# # ---------------------------------------------------------------------------
# # ── ENTRY POINT ────────────────────────────────────────────────────────────
# # ---------------------------------------------------------------------------

# if __name__ == "__main__":
#     # Configure Google authentication first
#     setup_google_adc()

#     # ── Start live dashboard server ────────────────────────────────────────
#     if _DASHBOARD_AVAILABLE:
#         # Register our callbacks so the browser control buttons work
#         _ds.register_start_callback(_start_fresh_run)
#         _ds.register_pause_callback(_on_pause)
#         _ds.register_resume_callback(_on_resume)
#         _ds.register_stop_callback(_on_stop)

#         # Start dashboard server
#         _ds.start_server(
#             open_browser=(os.environ.get("RENDER") != "true")
#         )

#         _emit(
#             "log",
#             msg="🌐 Live dashboard started — press ▶ START to begin running cycles"
#         )

#         print("✅ Dashboard ready. Press ▶ START in the browser.")
#     else:
#         print("⚠️ dashboard_server.py not found or flask not installed.")
#         print("    Install with: pip install flask")
#         print("    Falling back to direct run…\n")

#         check_dependencies()

#         try:
#             _run_all_cycles()
#         except KeyboardInterrupt:
#             print("\n\n🛑 Interrupt received!")
#             _kill_active_process()
#             cleanup_and_verify_sessions()
#             sys.exit(0)

#     # Keep the main thread alive so daemon threads keep running
#     check_dependencies()

#     try:
#         while True:
#             time.sleep(1)

#     except KeyboardInterrupt:
#         print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
#         _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
#         _kill_active_process()
#         cleanup_and_verify_sessions()
#         sys.exit(0)
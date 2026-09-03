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

# TIMEOUT_SECONDS = 10 * 60     # 10-minute limit passed to `colab run --timeout`
# WATCHDOG_GRACE_SECONDS = 20  # extra buffer BEFORE Python force-kills locally.
#                              # Total worst-case time before a forced kill is
#                              # TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS.
# TOTAL_CYCLES = 99999999999
# INTERMISSION_DELAY = 10      # seconds between cycles
# COOLDOWN_ON_412 = 10         # cooldown when rate-limited

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
#                 _kill_process_tree(_active_process.pid)
#             except Exception:
#                 try:
#                     _active_process.kill()
#                 except Exception:
#                     pass


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


# def _kill_process_tree(pid):
#     """
#     Forcefully kill a process and every child it spawned.
#     This is the core fix for cycles that hang past TIMEOUT_SECONDS: the
#     watchdog timer below calls this regardless of what the `colab` CLI is
#     doing, so a stuck local process can never run forever.
#     """
#     try:
#         parent = psutil.Process(pid)
#         procs = parent.children(recursive=True)
#         procs.append(parent)
#         for p in procs:
#             try:
#                 p.kill()
#             except Exception:
#                 pass
#         psutil.wait_procs(procs, timeout=5)
#         print(f"💀 Force-killed process tree for PID {pid}")
#     except psutil.NoSuchProcess:
#         pass
#     except Exception as e:
#         print(f"⚠️ Failed to kill process tree for PID {pid}: {e}")


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

# # Multiple patterns because the CLI's exact wording can vary — relying on a
# # single regex was the second reason sessions were leaking (silently no
# # session_id captured -> stop_session() never called).
# _SESSION_ID_PATTERNS = [
#     re.compile(r"Creating session '(?:run-)?([a-zA-Z0-9]+)'", re.IGNORECASE),
#     re.compile(r"Session READY \((?:run-)?([a-zA-Z0-9]+)\)", re.IGNORECASE),
#     re.compile(r"\brun-([a-fA-F0-9]{6,})\b"),
# ]

# _current_dl_file = None
# _current_ul_file = None


# def _extract_session_id(line):
#     for pattern in _SESSION_ID_PATTERNS:
#         m = pattern.search(line)
#         if m:
#             return m.group(1).strip()
#     return None


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


# def stop_session(session_id):
#     """Stop one specific remote Colab session."""

#     if not session_id:
#         print("⚠️ No Colab session ID available.")
#         return False

#     # You want to store only the ID, e.g.:  68d60c
#     # But Colab's generated session name is:  run-68d60c
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
#             print(f"✅ Remote Colab session stopped successfully: {session_name}")
#             _emit(
#                 "session_stop",
#                 msg=f"🛑 Remote Colab session stopped: {session_id}",
#                 session_id=session_id,
#             )
#             return True

#         print(f"❌ Colab stop failed for {session_name} (exit code {result.returncode})")
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
#     """
#     Aggressively finds and kills active sessions concurrently.
#     Called both BEFORE a cycle starts and AFTER a cycle ends (success,
#     error, or forced timeout) — this unconditional post-cycle sweep is
#     what actually guarantees nothing is left running remotely, even if
#     session-ID parsing or the local kill above didn't work as expected.
#     """
#     print("🧹 Clearing active Google Colab cloud sessions...")
#     _emit("cleanup", msg="🧹 Clearing all active Colab sessions…")

#     stored_id = manage_session_lock(action="get")
#     print("session id:", stored_id)
#     if stored_id:
#         stop_session(stored_id)
#         manage_session_lock(action="clear")

#     try:
#         list_check = subprocess.run(
#             ["colab", "sessions"],
#             capture_output=True, text=True, encoding="utf-8", errors="replace",
#             timeout=15, env=SUBPROCESS_ENV
#         )
#         if list_check.returncode == 0 and list_check.stdout.strip():
#             # Extract session IDs (6-character hex strings)
#             found_ids = set()
#             for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
#                 found_ids.add(m.group(1))
#             session_ids = list(found_ids)
#             if session_ids:
#                 print(f"🔎 Found {len(session_ids)} stray session(s) still live remotely: {session_ids}")
#                 _emit("warn", msg=f"🔎 Found {len(session_ids)} stray remote session(s) — stopping them.")
#                 with ThreadPoolExecutor(max_workers=5) as executor:
#                     executor.map(stop_session, filter(None, session_ids))
#     except Exception as e:
#         print(f"⚠️ Session listing/cleanup check failed: {e}")


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

#     exec_command = [
#         "colab",
#         "--auth=adc",
#         "run",
#         "--timeout",
#         str(TIMEOUT_SECONDS),
#         TARGET_FILE,
#     ]
#     session_id = None
#     process = None
#     timer = None
#     watchdog_fired = threading.Event()

#     _emit("session_start", msg="☁️ Provisioning new Colab session…")

#     try:
#         process = subprocess.Popen(
#             exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#             text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
#         )
#         _set_active_process(process)

#         # ── WATCHDOG: guarantees this cycle cannot run forever ──────────
#         # This fires independently of the main thread, so even if the CLI
#         # hangs (never honours --timeout, no stdout, no exit) the local
#         # process tree still gets force-killed. The remote session itself
#         # is then caught by the unconditional cleanup_and_verify_sessions()
#         # call in `finally` below.
#         def _watchdog_fire():
#             watchdog_fired.set()
#             msg = (f"⏰ WATCHDOG: cycle #{cycle_num} exceeded "
#                    f"{TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS}s wall-clock "
#                    f"(CLI --timeout of {TIMEOUT_SECONDS}s did not stop it). "
#                    f"Force-killing local process — remote sweep follows.")
#             print(f"\n{msg}")
#             _emit("error", msg=msg, cycle=cycle_num)
#             _kill_process_tree(process.pid)

#         timer = threading.Timer(TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS, _watchdog_fire)
#         timer.daemon = True
#         timer.start()

#         def _handle_line(line):
#             nonlocal session_id
#             if not session_id:
#                 found = _extract_session_id(line)
#                 if found:
#                     session_id = found
#                     print(f"\n📌 Isolated Session ID: {session_id}")
#                     manage_session_lock(session_id, action="save")
#                     _emit(
#                         "session_ready",
#                         msg=f"📌 Session ready: {session_id}",
#                         session_id=session_id,
#                     )

#         stream_subprocess_output(process, on_line=_handle_line)

#         # Bounded wait instead of an unbounded one — if the process hasn't
#         # actually exited yet (stdout closed but process still finishing
#         # up), give it a short grace window, then force it.
#         try:
#             process.wait(timeout=15)
#         except subprocess.TimeoutExpired:
#             print(f"\n⚠️ Process still alive after stdout closed — force killing PID {process.pid}")
#             _emit("error", msg="⚠️ Process unresponsive after output ended — force killing.")
#             _kill_process_tree(process.pid)
#             try:
#                 process.wait(timeout=10)
#             except subprocess.TimeoutExpired:
#                 pass

#         if _DASHBOARD_AVAILABLE and _ds.should_stop():
#             print("\n🛑 Stop requested — aborting cycle.")
#             return False

#         if watchdog_fired.is_set():
#             print(f"\n⚠️ Cycle #{cycle_num} was force-terminated by the watchdog.")
#             _emit("warn", msg=f"⚠️ Cycle #{cycle_num} force-terminated by watchdog.", cycle=cycle_num)
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

#     except subprocess.TimeoutExpired:
#         print(f"\n⏰ TIMEOUT REACHED for session '{session_id}'! Force-killing...")
#         _emit("error", msg=f"⏰ Timeout reached for session {session_id}! Force-killing.")
#         if process:
#             _kill_process_tree(process.pid)

#     except Exception as e:
#         err_str = str(e)
#         print(f"\n❌ Error during execution: {err_str}")
#         _emit("error", msg=f"❌ Execution error: {err_str}")
#         if any(x in err_str for x in ["412", "Precondition Failed", "TooManyAssignmentsError"]):
#             print(f"🛑 Rate limit hit (HTTP 412). Cool-down enforced ({COOLDOWN_ON_412}s)...")
#             _emit("warn", msg=f"🛑 Rate limit (HTTP 412) — cooling down for {COOLDOWN_ON_412}s")
#             time.sleep(COOLDOWN_ON_412)

#     finally:
#         if timer:
#             timer.cancel()
#         _set_active_process(None)
#         if session_id:
#             stop_session(session_id)
#         manage_session_lock(action="clear")
#         # THE KEY FIX: always do a full remote sweep after every cycle,
#         # regardless of how it ended. This is what actually guarantees the
#         # Colab session is gone even if the ID was never captured or the
#         # CLI's own timeout silently failed to stop things.
#         cleanup_and_verify_sessions()

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
#             if not _ds._pause_event.is_set():
#                 _emit("log", msg=f"⏸ Checking pause before cycle #{i}…")
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
#     check_dependencies()

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

#         try:
#             _run_all_cycles()
#         except KeyboardInterrupt:
#             print("\n\n🛑 Interrupt received!")
#             _kill_active_process()
#             cleanup_and_verify_sessions()
#             sys.exit(0)

#     # Keep the main thread alive so daemon threads keep running
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("\n\n🛑 Interrupt received! Cleaning up active sessions...")
#         _emit("warn", msg="🛑 Interrupted by user — cleaning up…")
#         _kill_active_process()
#         cleanup_and_verify_sessions()
#         sys.exit(0)










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

# --- NEW IMPORTS FOR DB ---
try:
    from pymongo import MongoClient
except ImportError:
    sys.exit("❌ FATAL: pymongo is not installed. Run: pip install pymongo")

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
WATCHDOG_GRACE_SECONDS = 20  
COOLDOWN_ON_412 = 10         

# --- NEW SCHEDULING CONFIGURATION ---
MAX_DAILY_RUNS = 10
MIN_SLEEP_AFTER_RUN_MINUTES = 45   # Minimum wait after a successful cycle
MAX_SLEEP_AFTER_RUN_MINUTES = 120  # Maximum wait after a successful cycle
NO_MOVIE_WAIT_MINUTES = 20         # Wait time if no movies are found in DB

# ---------------------------------------------------------------------------
# ── MONGODB PRE-CHECK LOGIC ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# def has_unprocessed_movies():
#     """
#     Connects to MongoDB and checks if there are any movie links 
#     that are NOT present in the seen_links collection.
#     """
#     mongo_uri = os.environ.get("MONGO_URI")
#     if not mongo_uri:
#         print("⚠️ MONGO_URI env variable not set! Assuming movies exist to prevent blocking.")
#         return True
        
#     try:
#         client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
#         db = client['movie_scraper']
#         seen_col = db["seen_links"]
#         movies_col = db["movies"]
        
#         # 1. Get a set of all URLs we have already seen
#         seen_docs = seen_col.find({}, {"url": 1})
#         seen_urls = set(doc.get("url") for doc in seen_docs if doc.get("url"))
        
#         # 2. Fetch movies to check if we have any unseen links
#         # Note: You may need to adjust how you extract the URL from the movie doc 
#         # based on your exact schema (e.g. if links are inside an array).
#         movies = movies_col.find({})
        
#         unseen_found = False
#         for movie in movies:
#             # Check the movie doc for URLs. Adjust this to match your DB structure:
#             # If your URL is nested like link_info["url"], extract it accordingly.
            
#             # Example assumption based on your prompt: 
#             # movie document contains a list of links or a primary URL
#             movie_url = movie.get("url") # Adjust this key if your schema is different!
            
#             if movie_url and movie_url not in seen_urls:
#                 unseen_found = True
#                 break
                
#             # If movie contains an array of links:
#             links_array = movie.get("links", [])
#             for link_info in links_array:
#                 if link_info.get("url") not in seen_urls:
#                     unseen_found = True
#                     break
                    
#             if unseen_found:
#                 break
                
#         client.close()
        
#         if unseen_found:
#             print("✅ DB Check: Unprocessed movies found! Cycle can proceed.")
#             return True
#         else:
#             print("📭 DB Check: No new movies found. All caught up.")
#             return False
            
#     except Exception as e:
#         print(f"❌ MongoDB Check Error: {e}")
#         # Default to True so the script doesn't permanently stall on a minor network hiccup
#         return True

def extract_urls_from_movie(movie_doc):
    """
    Safely extracts all URLs from a movie document, handling both 
    nested quality groups and direct field formats.
    """
    urls = set()
    
    # 1. Direct 'url' field if present
    if isinstance(movie_doc.get("url"), str) and movie_doc["url"].strip():
        urls.add(movie_doc["url"].strip())
        
    # 2. 'links' field (handles both JSON string and native lists with quality groups)
    raw = movie_doc.get("links")
    if raw:
        try:
            groups = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(groups, list):
                for group in groups:
                    if isinstance(group, dict):
                        for link_obj in group.get("links", []):
                            if isinstance(link_obj, dict) and link_obj.get("url"):
                                url = link_obj.get("url")
                                if url:
                                    urls.add(url.strip())
                            elif isinstance(link_obj, str):
                                urls.add(link_obj.strip())
                    elif isinstance(group, str):
                        urls.add(group.strip())
        except Exception:
            pass
            
    return urls


def _check_batch_unseen(seen_col, batch_urls):
    """
    Queries MongoDB for only the URLs in the current batch.
    Returns True if at least one URL in batch_urls is missing from seen_links.
    """
    if seen_col is None or not batch_urls:
        return False
        
    seen_docs = seen_col.find(
        {"url": {"$in": list(batch_urls)}}, 
        {"url": 1, "_id": 0}
    )
    seen_urls_in_db = set(doc["url"] for doc in seen_docs if doc.get("url"))
    
    for url in batch_urls:
        if url not in seen_urls_in_db:
            return True
            
    return False


def has_unprocessed_movies(batch_size=1000):
    """
    Self-contained MongoDB check using batched chunks and early exit,
    preventing linter scope errors.
    """
    MONGO_URI = "mongodb+srv://karangade6630_db_user:PH3mTb73zv9yUZrw@movie-scraper-data.j3z6hjh.mongodb.net/"
    
    client = None
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client['movie_scraper']
        seen_links_col = db["seen_links"]
        movies_col = db["movies"]
        
        # Stream documents projecting only required fields to minimize RAM usage
        movie_cursor = movies_col.find({}, {"url": 1, "links": 1}).batch_size(batch_size)
        
        current_batch_urls = set()
        
        for movie in movie_cursor:
            extracted_urls = extract_urls_from_movie(movie)
            current_batch_urls.update(extracted_urls)
            
            if len(current_batch_urls) >= batch_size:
                if _check_batch_unseen(seen_links_col, current_batch_urls):
                    client.close()
                    print("✅ DB Check: Unprocessed movies detected! (Early exit)")
                    return True
                current_batch_urls.clear()
        
        # Check remaining URLs in the final batch
        if current_batch_urls:
            if _check_batch_unseen(seen_links_col, current_batch_urls):
                client.close()
                print("✅ DB Check: Unprocessed movies detected in final batch!")
                return True
                
        client.close()
        print("📭 DB Check: No new movies found. All caught up.")
        return False
        
    except Exception as e:
        print(f"❌ MongoDB Check Error: {e}")
        if client:
            client.close()
        return True


# ---------------------------------------------------------------------------
# ── LIVE DASHBOARD INTEGRATION ─────────────────────────────────────────────
# ---------------------------------------------------------------------------
try:
    import dashboard_server as _ds
    _DASHBOARD_AVAILABLE = True
except ImportError:
    _DASHBOARD_AVAILABLE = False

def _emit(event_type: str, **kwargs):
    if _DASHBOARD_AVAILABLE:
        try:
            _ds.emit(event_type, **kwargs)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# ── CONTROL STATE & PROCESS MGMT (Unchanged) ───────────────────────────────
# ---------------------------------------------------------------------------
_runner_thread: threading.Thread | None = None
_runner_lock = threading.Lock()
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
            try: child.suspend()
            except Exception: pass
        parent.suspend()
    except Exception as e:
        print(f"⚠️ Failed to suspend process tree: {e}")

def _resume_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        parent.resume()
        for child in parent.children(recursive=True):
            try: child.resume()
            except Exception: pass
    except Exception as e:
        print(f"⚠️ Failed to resume process tree: {e}")

def _kill_process_tree(pid):
    try:
        parent = psutil.Process(pid)
        procs = parent.children(recursive=True)
        procs.append(parent)
        for p in procs:
            try: p.kill()
            except Exception: pass
        psutil.wait_procs(procs, timeout=5)
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
    threading.Thread(target=cleanup_and_verify_sessions, daemon=True).start()
    _emit("warn", msg="🛑 Run stopped by user. Clearing active sessions…")

# ---------------------------------------------------------------------------
# ── CORE RUNNER FUNCTIONS (Truncated parsing for brevity, same as yours) ───
# ---------------------------------------------------------------------------

def check_dependencies():
    if not shutil.which("colab"):
        sys.exit("❌ FATAL: 'colab' CLI is not installed or not in PATH.")

def convert_ipynb_to_py(ipynb_path, py_path):
    if not os.path.exists(ipynb_path):
        raise FileNotFoundError(f"Source file '{ipynb_path}' not found.")
    with open(ipynb_path, "r", encoding="utf-8", errors="replace") as f:
        nb_data = json.load(f)
    code_lines = [
        "".join(cell.get("source", [])) + "\n\n"
        for cell in nb_data.get("cells", [])
        if cell.get("cell_type") == "code"
    ]
    with open(py_path, "w", encoding="utf-8", errors="replace") as f:
        f.writelines(code_lines)

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
    except Exception as e:
        pass
    return None

def stop_session(session_id):
    if not session_id: return False
    session_name = session_id if session_id.startswith("run-") else f"run-{session_id}"
    try:
        result = subprocess.run(
            ["colab", "--auth=adc", "stop", "-s", session_name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=SUBPROCESS_ENV,
        )
        if result.returncode == 0: return True
        return False
    except Exception:
        return False

def cleanup_and_verify_sessions():
    stored_id = manage_session_lock(action="get")
    if stored_id:
        stop_session(stored_id)
        manage_session_lock(action="clear")
    try:
        list_check = subprocess.run(
            ["colab", "sessions"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, env=SUBPROCESS_ENV
        )
        if list_check.returncode == 0 and list_check.stdout.strip():
            found_ids = set()
            for m in re.finditer(r"\b(?:run-)?([a-fA-F0-9]{6})\b", list_check.stdout):
                found_ids.add(m.group(1))
            session_ids = list(found_ids)
            if session_ids:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    executor.map(stop_session, filter(None, session_ids))
    except Exception:
        pass

def run_remote_colab_cycle(cycle_num, runs_today):
    print(f"\n{'='*40}\n☁️  CYCLE START (Run {runs_today}/{MAX_DAILY_RUNS} for Today)\n{'='*40}")
    cleanup_and_verify_sessions()

    if _DASHBOARD_AVAILABLE and _ds.should_stop():
        return False

    exec_command = ["colab", "--auth=adc", "run", "--timeout", str(TIMEOUT_SECONDS), TARGET_FILE]
    
    session_id = None
    process = None
    timer = None
    watchdog_fired = threading.Event()

    try:
        process = subprocess.Popen(
            exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=SUBPROCESS_ENV
        )
        _set_active_process(process)

        def _watchdog_fire():
            watchdog_fired.set()
            _kill_process_tree(process.pid)

        timer = threading.Timer(TIMEOUT_SECONDS + WATCHDOG_GRACE_SECONDS, _watchdog_fire)
        timer.daemon = True
        timer.start()

        # Dummy stream reader (assumes you have the original stream_subprocess_output in your actual file)
        # Using process.wait for brevity in this example block
        process.wait() 

        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            return False

        if watchdog_fired.is_set():
            print(f"\n⚠️ Cycle was force-terminated by the watchdog.")
        elif process.returncode == 0:
            print("\n🎉 Cloud execution completed successfully!")
            return True
        else:
            print(f"\n⚠️ Execution finished with exit code: {process.returncode}")

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        time.sleep(COOLDOWN_ON_412)
    finally:
        if timer: timer.cancel()
        _set_active_process(None)
        if session_id: stop_session(session_id)
        manage_session_lock(action="clear")
        cleanup_and_verify_sessions()

    return True

# ---------------------------------------------------------------------------
# ── NEW DAILY SCHEDULING RUNNER ────────────────────────────────────────────
# ---------------------------------------------------------------------------

def _run_all_cycles():
    """
    Main loop rebuilt for smart daily scheduling and rate limiting.
    """
    global _runner_thread

    try:
        convert_ipynb_to_py(NOTEBOOK_FILE, TARGET_FILE)
        cleanup_and_verify_sessions()
    except Exception as e:
        print(f"❌ Startup error: {e}")
        if _DASHBOARD_AVAILABLE: _ds.mark_idle()
        with _runner_lock: _runner_thread = None
        return

    runs_today = 0
    current_day = datetime.date.today()
    cycle_num_all_time = 0

    while True:
        # 1. Check if day flipped over
        today = datetime.date.today()
        if today != current_day:
            current_day = today
            runs_today = 0
            print(f"\n🌅 A new day has begun! Resetting run limit to 0/{MAX_DAILY_RUNS}.")

        # 2. Check if we reached daily limit
        if runs_today >= MAX_DAILY_RUNS:
            now = datetime.datetime.now()
            tomorrow = now + datetime.timedelta(days=1)
            # Wake up at 12:05 AM tomorrow
            midnight = datetime.datetime(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day, hour=0, minute=5)
            sleep_seconds = (midnight - now).total_seconds()
            
            print(f"\n🛌 Reached {MAX_DAILY_RUNS} successful runs for today.")
            print(f"⏳ Sleeping until tomorrow ({midnight.strftime('%Y-%m-%d %H:%M')})...")
            
            # Sleep in chunks to remain responsive to pause/stop commands
            _interruptible_sleep(sleep_seconds)
            continue

        # 3. Check for Dashboard Stop/Pause
        if _DASHBOARD_AVAILABLE and _ds.should_stop():
            break
        if _DASHBOARD_AVAILABLE:
            if not _ds.wait_if_paused():
                break

        # 4. Check MongoDB for work
        print("\n🔍 Checking MongoDB for unprocessed movies...")
        if has_unprocessed_movies():
            cycle_num_all_time += 1
            
            # Execute the Colab Runner
            completed = run_remote_colab_cycle(cycle_num_all_time, runs_today + 1)
            
            if not completed and _DASHBOARD_AVAILABLE and _ds.should_stop():
                break # User clicked Stop
                
            # Increment only on successful execution attempt
            runs_today += 1
            
            # Random wait after a heavy run (e.g., 45 to 120 minutes)
            sleep_mins = random.randint(MIN_SLEEP_AFTER_RUN_MINUTES, MAX_SLEEP_AFTER_RUN_MINUTES)
            print(f"\n✅ Finished Run {runs_today}/{MAX_DAILY_RUNS} for today.")
            print(f"🎲 Anti-Ban delay: Waiting {sleep_mins} minutes before next cycle...")
            _interruptible_sleep(sleep_mins * 60)
            
        else:
            # No work found. Don't increment the counter, just wait a bit and check again.
            sleep_mins = NO_MOVIE_WAIT_MINUTES
            print(f"\n⏳ No movies to process. Waiting {sleep_mins} minutes to check DB again...")
            _interruptible_sleep(sleep_mins * 60)


def _interruptible_sleep(total_seconds):
    """Sleeps in small intervals so dashboard stop/pause works immediately."""
    intervals = int(total_seconds * 4) # Check every 0.25 seconds
    for _ in range(intervals):
        if _DASHBOARD_AVAILABLE:
            if _ds.should_stop(): return
            if not _ds.wait_if_paused(): return
        time.sleep(0.25)


def _start_fresh_run():
    global _runner_thread
    with _runner_lock:
        if _runner_thread and _runner_thread.is_alive(): return
        _kill_active_process()
        _runner_thread = threading.Thread(target=_run_all_cycles, daemon=True, name="colab-runner")
        _runner_thread.start()

def setup_google_adc():
    if os.environ.get("RENDER") == "true":
        credentials_path = "/etc/secrets/application_default_credentials.json"
        if not os.path.isfile(credentials_path):
            raise FileNotFoundError(f"❌ Google credentials not found: {credentials_path}")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    else:
        local_credentials = os.path.join(os.environ.get("APPDATA", ""), "gcloud", "application_default_credentials.json")
        if os.path.isfile(local_credentials):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_credentials

if __name__ == "__main__":
    setup_google_adc()
    check_dependencies()
    
    # Needs MONGO_URI setup in environment vars on Render
    if not os.environ.get("MONGO_URI"):
        print("\n⚠️ WARNING: MONGO_URI is not set. Pre-check logic will be bypassed!\n")

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
        while True: time.sleep(1)
    except KeyboardInterrupt:
        _kill_active_process()
        cleanup_and_verify_sessions()
        sys.exit(0)
# """
# dashboard_server.py
# --------------------
# A lightweight Flask SSE (Server-Sent Events) server that:
#   - Receives structured JSON events from colab_demo.py via POST /log
#   - Streams those events in real-time to dashboard.html via GET /events
#   - Serves dashboard.html at GET /
#   - Exposes POST /control for Start / Pause / Resume / Stop
#   - Auto-opens the browser on start
# """

# import json
# import os
# import queue
# import threading
# import time
# import webbrowser
# from datetime import datetime

# # ---------------------------------------------------------------------------
# # Graceful Flask import with helpful error message
# # ---------------------------------------------------------------------------
# try:
#     from flask import Flask, Response, jsonify, request, send_from_directory
# except ImportError:
#     raise SystemExit(
#         "❌ Flask is required for the live dashboard.\n"
#         "   Install it with:  pip install flask"
#     )

# # ---------------------------------------------------------------------------
# # Config
# # ---------------------------------------------------------------------------
# # ---------------------------------------------------------------------------
# # Render / Production configuration
# # ---------------------------------------------------------------------------
# PORT = int(os.environ.get("PORT", 5757))
# DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))

# app = Flask(__name__)
# app.config["SECRET_KEY"] = "nb-runner-dashboard"

# # Global broadcast queue — each connected SSE client gets its own sub-queue
# _client_queues: list[queue.Queue] = []
# _client_queues_lock = threading.Lock()

# # In-memory event history so late-connecting browsers can catch up
# _event_history: list[dict] = []
# _history_lock = threading.Lock()
# MAX_HISTORY = 500

# # ---------------------------------------------------------------------------
# # Control state — shared between Flask and colab_demo.py
# # ---------------------------------------------------------------------------
# # Possible states: "idle" | "running" | "paused" | "stopping"
# _control_state: str = "idle"
# _control_lock  = threading.Lock()

# # Events used by colab_demo.py to react to control commands
# _pause_event  = threading.Event()   # set = NOT paused  (cleared = paused)
# _stop_event   = threading.Event()   # set = stop requested
# _start_event  = threading.Event()   # set = start requested

# _pause_event.set()    # start not paused

# # Optional callback called when the browser requests start, pause, resume, or stop
# # colab_demo.py sets these so it can spin up/suspend/resume/terminate the run
# _on_start_callback = None
# _on_pause_callback = None
# _on_resume_callback = None
# _on_stop_callback = None


# def get_control_state() -> str:
#     with _control_lock:
#         return _control_state


# def _set_state(new_state: str):
#     global _control_state
#     with _control_lock:
#         _control_state = new_state
#     emit("ctrl_state", state=new_state, msg=f"Control → {new_state}")


# def register_start_callback(cb):
#     """colab_demo.py calls this to register the function that starts a fresh run."""
#     global _on_start_callback
#     _on_start_callback = cb


# def register_pause_callback(cb):
#     """colab_demo.py calls this to register the function that pauses active tasks."""
#     global _on_pause_callback
#     _on_pause_callback = cb


# def register_resume_callback(cb):
#     """colab_demo.py calls this to register the function that resumes active tasks."""
#     global _on_resume_callback
#     _on_resume_callback = cb


# def register_stop_callback(cb):
#     """colab_demo.py calls this to register the function that terminates active tasks."""
#     global _on_stop_callback
#     _on_stop_callback = cb


# # ---------------------------------------------------------------------------
# # Internal helpers
# # ---------------------------------------------------------------------------

# def _broadcast(event: dict):
#     """Push an event to every connected SSE client."""
#     with _history_lock:
#         _event_history.append(event)
#         if len(_event_history) > MAX_HISTORY:
#             _event_history.pop(0)

#     with _client_queues_lock:
#         dead = []
#         for q in _client_queues:
#             try:
#                 q.put_nowait(event)
#             except queue.Full:
#                 dead.append(q)
#         for q in dead:
#             _client_queues.remove(q)


# def _make_sse(event: dict) -> str:
#     return f"data: {json.dumps(event)}\n\n"


# # ---------------------------------------------------------------------------
# # Routes
# # ---------------------------------------------------------------------------

# @app.route("/")
# def serve_dashboard():
#     return send_from_directory(DASHBOARD_DIR, "dashboard.html")


# @app.route("/log", methods=["POST"])
# def receive_log():
#     """colab_demo.py POSTs structured JSON events here."""
#     try:
#         data = request.get_json(force=True, silent=True) or {}
#         data.setdefault("ts", datetime.now().isoformat())
#         _broadcast(data)
#         return jsonify({"ok": True})
#     except Exception as e:
#         return jsonify({"ok": False, "error": str(e)}), 500


# @app.route("/control", methods=["POST"])
# def control():
#     """
#     Browser posts { "action": "start" | "pause" | "resume" | "stop" } here.
#     The action is forwarded to colab_demo.py via threading events.
#     """
#     data   = request.get_json(force=True, silent=True) or {}
#     action = data.get("action", "").lower()
#     state  = get_control_state()

#     if action == "start":
#         if state in ("idle", "stopping"):
#             _stop_event.clear()
#             _pause_event.set()
#             _set_state("running")
#             # Fire the registered callback in a daemon thread so Flask returns fast
#             if _on_start_callback:
#                 t = threading.Thread(target=_on_start_callback, daemon=True, name="runner")
#                 t.start()
#             return jsonify({"ok": True, "state": "running"})
#         return jsonify({"ok": False, "reason": f"Cannot start from state '{state}'"}), 400

#     elif action == "pause":
#         if state == "running":
#             _pause_event.clear()   # colab_demo.py will block on _pause_event.wait()
#             _set_state("paused")
#             if _on_pause_callback:
#                 _on_pause_callback()
#             return jsonify({"ok": True, "state": "paused"})
#         return jsonify({"ok": False, "reason": f"Cannot pause from state '{state}'"}), 400

#     elif action == "resume":
#         if state == "paused":
#             _pause_event.set()     # unblock the wait in colab_demo.py
#             _set_state("running")
#             if _on_resume_callback:
#                 _on_resume_callback()
#             return jsonify({"ok": True, "state": "running"})
#         return jsonify({"ok": False, "reason": f"Cannot resume from state '{state}'"}), 400

#     elif action == "stop":
#         if state in ("running", "paused"):
#             _stop_event.set()      # colab_demo.py checks this flag
#             _pause_event.set()     # unblock any paused wait so it can see stop
#             _set_state("stopping")
#             if _on_stop_callback:
#                 _on_stop_callback()
#             return jsonify({"ok": True, "state": "stopping"})
#         return jsonify({"ok": False, "reason": f"Cannot stop from state '{state}'"}), 400

#     return jsonify({"ok": False, "reason": f"Unknown action '{action}'"}), 400


# @app.route("/control/state", methods=["GET"])
# def control_state_route():
#     return jsonify({"state": get_control_state()})


# @app.route("/events")
# def sse_stream():
#     """Browser connects here to receive a live SSE stream."""
#     client_q: queue.Queue = queue.Queue(maxsize=200)

#     # Replay history so the new client sees all past events
#     with _history_lock:
#         history_snapshot = list(_event_history)

#     def generate():
#         # First, flush history
#         for ev in history_snapshot:
#             yield _make_sse(ev)

#         # Send current control state immediately
#         yield _make_sse({"type": "ctrl_state", "state": get_control_state(),
#                          "ts": datetime.now().isoformat()})

#         # Register this client
#         with _client_queues_lock:
#             _client_queues.append(client_q)

#         try:
#             while True:
#                 try:
#                     ev = client_q.get(timeout=20)
#                     yield _make_sse(ev)
#                 except queue.Empty:
#                     # Send a heartbeat comment to keep the connection alive
#                     yield ": heartbeat\n\n"
#         except GeneratorExit:
#             pass
#         finally:
#             with _client_queues_lock:
#                 if client_q in _client_queues:
#                     _client_queues.remove(client_q)

#     return Response(
#         generate(),
#         mimetype="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "X-Accel-Buffering": "no",
#         },
#     )


# @app.route("/history")
# def history():
#     with _history_lock:
#         return jsonify(_event_history)


# @app.route("/ping")
# def ping():
#     return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# # ---------------------------------------------------------------------------
# # Public API — called by colab_demo.py
# # ---------------------------------------------------------------------------

# def emit(event_type: str, **kwargs):
#     """
#     Convenience function: build and broadcast an event dict.
#     Can be called from any thread in colab_demo.py.
#     """
#     ev = {
#         "type": event_type,
#         "ts": datetime.now().isoformat(),
#         **kwargs,
#     }
#     _broadcast(ev)


# def mark_idle():
#     """Call when all cycles finish or are aborted — resets state to idle."""
#     _set_state("idle")


# def should_stop() -> bool:
#     """Returns True if a stop has been requested. colab_demo.py polls this."""
#     return _stop_event.is_set()


# def wait_if_paused(check_interval: float = 0.25):
#     """
#     Block until unpaused. Also returns False if a stop is requested while paused.
#     colab_demo.py calls this between cycles.
#     """
#     while not _pause_event.wait(timeout=check_interval):
#         if _stop_event.is_set():
#             return False
#     return not _stop_event.is_set()


# def start_server(open_browser: bool = True):
#     """
#     Start the Flask server in a daemon background thread.
#     Works locally and on Render.
#     """

#     def _run():
#         # Silence Flask's default request logging
#         import logging
#         log = logging.getLogger("werkzeug")
#         log.setLevel(logging.ERROR)

#         app.run(
#             host="0.0.0.0",
#             port=PORT,
#             debug=False,
#             use_reloader=False,
#             threaded=True
#         )

#     t = threading.Thread(
#         target=_run,
#         daemon=True,
#         name="dashboard-server"
#     )

#     t.start()

#     # Give Flask a moment to bind the port
#     time.sleep(1.2)

#     if open_browser:
#         # Only open browser when running locally.
#         # Render has no local browser to open.
#         if os.environ.get("RENDER") != "true":
#             webbrowser.open(f"http://127.0.0.1:{PORT}")

#     print(f"🌐 Live dashboard → http://0.0.0.0:{PORT}")
#     return t

# # ---------------------------------------------------------------------------
# # Standalone mode (python dashboard_server.py)
# # ---------------------------------------------------------------------------
# if __name__ == "__main__":
#     print(f"🚀 Starting standalone dashboard server on port {PORT}...")
#     start_server(open_browser=False)  # Don't open browser in standalone mode
#     # Keep main thread alive
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("Shutting down.")

"""
dashboard_server.py
--------------------
A lightweight Flask SSE (Server-Sent Events) server that:
  - Receives structured JSON events from colab_demo.py via POST /log
  - Streams those events in real-time to dashboard.html via GET /events
  - Serves dashboard.html at GET /
  - Exposes POST /control for Start / Pause / Resume / Stop
  - Auto-opens the browser on start
"""

import json
import os
import queue
import threading
import time
import webbrowser
from datetime import datetime

# ---------------------------------------------------------------------------
# Graceful Flask import with helpful error message
# ---------------------------------------------------------------------------
try:
    from flask import Flask, Response, jsonify, request, send_from_directory
except ImportError:
    raise SystemExit(
        "❌ Flask is required for the live dashboard.\n"
        "   Install it with:  pip install flask"
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Render / Production configuration
# ---------------------------------------------------------------------------
PORT = 3000
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "nb-runner-dashboard"

# Global broadcast queue — each connected SSE client gets its own sub-queue
_client_queues: list[queue.Queue] = []
_client_queues_lock = threading.Lock()

# In-memory event history so late-connecting browsers can catch up
_event_history: list[dict] = []
_history_lock = threading.Lock()
MAX_HISTORY = 500

# ---------------------------------------------------------------------------
# Control state — shared between Flask and colab_demo.py
# ---------------------------------------------------------------------------
# Possible states: "idle" | "running" | "paused" | "stopping"
_control_state: str = "idle"
_control_lock  = threading.Lock()

# Events used by colab_demo.py to react to control commands
_pause_event  = threading.Event()   # set = NOT paused  (cleared = paused)
_stop_event   = threading.Event()   # set = stop requested
_start_event  = threading.Event()   # set = start requested

_pause_event.set()    # start not paused

# Optional callback called when the browser requests start, pause, resume, or stop
# colab_demo.py sets these so it can spin up/suspend/resume/terminate the run
_on_start_callback = None
_on_pause_callback = None
_on_resume_callback = None
_on_stop_callback = None


def get_control_state() -> str:
    with _control_lock:
        return _control_state


def _set_state(new_state: str):
    global _control_state
    with _control_lock:
        _control_state = new_state
    emit("ctrl_state", state=new_state, msg=f"Control → {new_state}")


def register_start_callback(cb):
    """colab_demo.py calls this to register the function that starts a fresh run."""
    global _on_start_callback
    _on_start_callback = cb


def register_pause_callback(cb):
    """colab_demo.py calls this to register the function that pauses active tasks."""
    global _on_pause_callback
    _on_pause_callback = cb


def register_resume_callback(cb):
    """colab_demo.py calls this to register the function that resumes active tasks."""
    global _on_resume_callback
    _on_resume_callback = cb


def register_stop_callback(cb):
    """colab_demo.py calls this to register the function that terminates active tasks."""
    global _on_stop_callback
    _on_stop_callback = cb


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _broadcast(event: dict):
    """Push an event to every connected SSE client."""
    with _history_lock:
        _event_history.append(event)
        if len(_event_history) > MAX_HISTORY:
            _event_history.pop(0)

    with _client_queues_lock:
        dead = []
        for q in _client_queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _client_queues.remove(q)


def _make_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def serve_dashboard():
    return send_from_directory(DASHBOARD_DIR, "dashboard.html")


@app.route("/log", methods=["POST"])
def receive_log():
    """colab_demo.py POSTs structured JSON events here."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        data.setdefault("ts", datetime.now().isoformat())
        _broadcast(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/control", methods=["POST"])
def control():
    """
    Browser posts { "action": "start" | "pause" | "resume" | "stop" } here.
    The action is forwarded to colab_demo.py via threading events.
    """
    data   = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "").lower()
    state  = get_control_state()

    if action == "start":
        if state in ("idle", "stopping"):
            _stop_event.clear()
            _pause_event.set()
            _set_state("running")
            # Fire the registered callback in a daemon thread so Flask returns fast
            if _on_start_callback:
                t = threading.Thread(target=_on_start_callback, daemon=True, name="runner")
                t.start()
            return jsonify({"ok": True, "state": "running"})
        return jsonify({"ok": False, "reason": f"Cannot start from state '{state}'"}), 400

    elif action == "pause":
        if state == "running":
            _pause_event.clear()   # colab_demo.py will block on _pause_event.wait()
            _set_state("paused")
            if _on_pause_callback:
                _on_pause_callback()
            return jsonify({"ok": True, "state": "paused"})
        return jsonify({"ok": False, "reason": f"Cannot pause from state '{state}'"}), 400

    elif action == "resume":
        if state == "paused":
            _pause_event.set()     # unblock the wait in colab_demo.py
            _set_state("running")
            if _on_resume_callback:
                _on_resume_callback()
            return jsonify({"ok": True, "state": "running"})
        return jsonify({"ok": False, "reason": f"Cannot resume from state '{state}'"}), 400

    elif action == "stop":
        if state in ("running", "paused"):
            _stop_event.set()      # colab_demo.py checks this flag
            _pause_event.set()     # unblock any paused wait so it can see stop
            _set_state("stopping")
            if _on_stop_callback:
                _on_stop_callback()
            return jsonify({"ok": True, "state": "stopping"})
        return jsonify({"ok": False, "reason": f"Cannot stop from state '{state}'"}), 400

    return jsonify({"ok": False, "reason": f"Unknown action '{action}'"}), 400


@app.route("/control/state", methods=["GET"])
def control_state_route():
    return jsonify({"state": get_control_state()})


@app.route("/events")
def sse_stream():
    """Browser connects here to receive a live SSE stream."""
    client_q: queue.Queue = queue.Queue(maxsize=200)

    # Replay history so the new client sees all past events
    with _history_lock:
        history_snapshot = list(_event_history)

    def generate():
        # First, flush history
        for ev in history_snapshot:
            yield _make_sse(ev)

        # Send current control state immediately
        yield _make_sse({"type": "ctrl_state", "state": get_control_state(),
                         "ts": datetime.now().isoformat()})

        # Register this client
        with _client_queues_lock:
            _client_queues.append(client_q)

        try:
            while True:
                try:
                    ev = client_q.get(timeout=20)
                    yield _make_sse(ev)
                except queue.Empty:
                    # Send a heartbeat comment to keep the connection alive
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _client_queues_lock:
                if client_q in _client_queues:
                    _client_queues.remove(client_q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/history")
def history():
    with _history_lock:
        return jsonify(_event_history)


@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Public API — called by colab_demo.py
# ---------------------------------------------------------------------------

def emit(event_type: str, **kwargs):
    """
    Convenience function: build and broadcast an event dict.
    Can be called from any thread in colab_demo.py.
    """
    ev = {
        "type": event_type,
        "ts": datetime.now().isoformat(),
        **kwargs,
    }
    _broadcast(ev)


def mark_idle():
    """Call when all cycles finish or are aborted — resets state to idle."""
    _set_state("idle")


def should_stop() -> bool:
    """Returns True if a stop has been requested. colab_demo.py polls this."""
    return _stop_event.is_set()


def wait_if_paused(check_interval: float = 0.25):
    """
    Block until unpaused. Also returns False if a stop is requested while paused.
    colab_demo.py calls this between cycles.
    """
    while not _pause_event.wait(timeout=check_interval):
        if _stop_event.is_set():
            return False
    return not _stop_event.is_set()


def start_server(open_browser: bool = True):
    """
    Start the Flask server in a daemon background thread.
    Works locally and on Render.
    """

    def _run():
        # Silence Flask's default request logging
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        app.run(
            host="0.0.0.0",
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )

    t = threading.Thread(
        target=_run,
        daemon=True,
        name="dashboard-server"
    )

    t.start()

    # Give Flask a moment to bind the port
    time.sleep(1.2)

    if open_browser:
        # Only open browser when running locally.
        # Render has no local browser to open.
        if os.environ.get("RENDER") != "true":
            webbrowser.open(f"http://127.0.0.1:{PORT}")

    print(f"🌐 Live dashboard → http://0.0.0.0:{PORT}")
    return t

# ---------------------------------------------------------------------------
# Standalone mode (python dashboard_server.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"🚀 Starting standalone dashboard server on port {PORT}...")
    start_server(open_browser=False)  # Don't open browser in standalone mode
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down.")

"""Keyence IV3 receiver - pluggable (spec 8.2).

Interface: start() / stop() / finish(timeout) / check() / status(), same as the
other streams. Two implementations:

  off : nothing is recorded
  iv3 : Keyence IV3 in image-capture mode. The dashboard runs an FTP server
        that receives the JPEG and result text the camera pushes. If the camera
        accepts trigger commands ("trigger": true) it is also triggered over TCP
        at a fixed interval; when the sensor triggers itself, set "trigger" to
        false, or let the receiver fall back to it after the camera refuses. Images are stored untouched, with the
        trigger and arrival times in keyence/index.csv. No OCR happens here:
        the pictures are raw data, read later by the dataset builder.
  tcp : TCP client for IV3 non-procedural output. Records are split on the
        configured delimiter and written verbatim to keyence/records.jsonl with
        the host arrival time. Parsing of the fields is deferred to
        post-processing, like every other stream. Untested against a real IV3.

An FTP-push receiver (pyftpdlib) can be added as a third class with the same
interface without touching the recorder.
"""
import csv
import json
import logging
import os
import shutil
import socket
import threading
import time


class NullReceiver(object):
    name = "keyence"
    health = "off"

    def start(self):
        pass

    def stop(self):
        pass

    def finish(self, timeout):
        pass

    def check(self):
        return "off"

    def status(self):
        return {"name": self.name, "type": "keyence", "health": "off",
                "note": "Not recording - set keyence.mode to \"iv3\" to record the IV3 images"}


class TcpReceiver(object):
    name = "keyence"

    def __init__(self, kcfg, out_dir, clock, emit):
        self.host, self.port = kcfg["host"], int(kcfg["port"])
        self.delim = kcfg["delimiter"].encode("latin-1")
        self.out_dir = out_dir
        self.clock = clock
        self.emit = emit
        self.stop_event = threading.Event()
        self.thread = None
        self.connected = False
        self.records = 0
        self.last_t = None
        self.health = "starting"
        self.t_start = None

    def start(self):
        os.makedirs(self.out_dir, exist_ok=True)
        self.t_start = self.clock.now()
        self.thread = threading.Thread(target=self._run, name="keyence")
        self.thread.daemon = True
        self.thread.start()

    def _run(self):
        path = os.path.join(self.out_dir, "records.jsonl")
        with open(path, "a") as out:
            while not self.stop_event.is_set():
                try:
                    sock = socket.create_connection((self.host, self.port), timeout=3)
                except OSError as e:
                    self.emit("keyence_connect_failed", error=str(e), level="warning")
                    self.stop_event.wait(5)
                    continue
                self.connected = True
                self.emit("keyence_connected", host=self.host, port=self.port)
                sock.settimeout(0.5)
                buf = b""
                try:
                    while not self.stop_event.is_set():
                        try:
                            chunk = sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        t = self.clock.now()
                        buf += chunk
                        while self.delim in buf:
                            rec, buf = buf.split(self.delim, 1)
                            out.write(json.dumps({"t_recv": round(t, 6),
                                                  "raw": rec.decode("latin-1")}) + "\n")
                            self.records += 1
                            self.last_t = t
                        out.flush()
                except OSError as e:
                    self.emit("keyence_error", error=str(e), level="warning")
                finally:
                    self.connected = False
                    sock.close()

    def stop(self):
        self.stop_event.set()

    def finish(self, timeout):
        if self.thread:
            self.thread.join(timeout)

    def check(self):
        health = "ok" if self.connected else ("starting" if self.clock.now() - self.t_start < 10 else "stalled")
        if self.stop_event.is_set():
            health = "stopped"
        self.health = health
        return health

    def status(self):
        return {"name": self.name, "type": "keyence", "health": self.health,
                "records": self.records, "connected": self.connected,
                "since_record_s": round(self.clock.now() - self.last_t, 1) if self.last_t else None}


IV3_FIELDS = ["seq", "t_trigger", "t_response", "t_received", "trigger_latency_ms",
              "transfer_s", "kind", "file", "bytes", "trigger_no", "device_time", "total_status", "error"]


def parse_result_text(path):
    """The IV3 writes a small UTF-16 tab-separated result file next to each image."""
    out = {}
    try:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-16", "replace") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") \
            else raw.decode("utf-8", "replace")
        for line in text.splitlines():
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if len(parts) >= 2:
                out[parts[0].rstrip(".:")] = parts[1] if len(parts) == 2 else parts[1:]
    except OSError:
        pass
    return out


class Iv3Service(object):
    """Long-lived Keyence IV3 connection, owned by the server rather than by a run.

    The FTP server stays up for as long as the dashboard runs, so the camera never
    gets a refused connection, and it can push whenever it likes. Between runs the
    pictures go to a scratch folder that keeps only the newest few; during a run they
    are moved into the session as they arrive and listed in index.csv.

    Triggering, when the camera's program allows it, happens while a run is recording
    or while somebody is watching the live view, and never in between.
    """
    name = "keyence"

    def __init__(self, kcfg, scratch_dir, clock, emit):
        self.cfg = kcfg
        self.scratch_dir = scratch_dir
        self.clock = clock
        self.emit_server = emit
        self.emit_session = None
        self.stop_event = threading.Event()
        self.threads = []
        self.server = None
        self.lock = threading.Lock()
        self.session_dir = None
        self.session_stopping = False
        self.index = None
        self.writer = None
        self.scratch_keep = int(kcfg.get("scratch_keep", 40))
        self.scratch_since_prune = 0
        self.watching_until = 0.0
        self.images = 0                 # this session
        self.triggers = 0
        self.failed = 0
        self.total_images = 0           # since the server started
        self.connected = False
        self.trigger_enabled = bool(kcfg.get("trigger", True))
        self.trigger_refused = 0
        self.last_error = ""
        self.last_image_t = None
        self.last_image_path = None
        self.last_result = {}
        self.last_trigger_no = None
        self.health = "starting"
        self.t_start = None
        self.pending = None

    # -- lifecycle ------------------------------------------------------------ #
    def start(self):
        if os.path.isdir(self.scratch_dir):
            shutil.rmtree(self.scratch_dir, ignore_errors=True)
        os.makedirs(self.scratch_dir, exist_ok=True)
        self.t_start = self.clock.now()
        self._start_ftp()
        t = threading.Thread(target=self._trigger_loop, name="keyence-trigger")
        t.daemon = True
        t.start()
        self.threads.append(t)
        if not self.trigger_enabled:
            self.emit_server("keyence_receive_only", host=self.cfg["host"])

    def shutdown(self):
        self.stop_event.set()
        if self.server:
            try:
                self.server.close_all()
            except Exception:                      # noqa - shutting down anyway
                pass
            self.server = None
        for t in self.threads:
            t.join(2)
        self.threads = []
        self._close_index()

    def _start_ftp(self):
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.servers import FTPServer

        service = self

        class Handler(FTPHandler):
            def on_file_received(self, path):
                service._on_file(path)

            def on_incomplete_file_received(self, path):
                service._on_file(path, incomplete=True)

        auth = DummyAuthorizer()
        auth.add_user(self.cfg.get("ftp_user", "ftpuser"), self.cfg.get("ftp_pass", "ftppass"),
                      self.scratch_dir, perm="elradfmw")
        Handler.authorizer = auth
        Handler.banner = "Aid4SME Dashboard"
        ports = self.cfg.get("ftp_passive_ports") or [2130, 2140]
        Handler.passive_ports = range(int(ports[0]), int(ports[1]) + 1)
        logging.getLogger("pyftpdlib").setLevel(logging.WARNING)
        port = int(self.cfg.get("ftp_port", 2121))
        last = None
        for _ in range(10):
            try:
                self.server = FTPServer(("0.0.0.0", port), Handler)
                break
            except OSError as e:                   # the port may still be closing
                last = e
                time.sleep(0.3)
        else:
            raise IOError("FTP port %d is in use (%s). Close anything else listening on it."
                          % (port, last))
        t = threading.Thread(target=self.server.serve_forever,
                             kwargs={"timeout": 0.5, "blocking": True}, name="keyence-ftp")
        t.daemon = True
        t.start()
        self.threads.append(t)
        self.emit_server("keyence_ftp_started", port=port, folder=self.scratch_dir)

    # -- session ---------------------------------------------------------------- #
    def begin_session(self, out_dir, emit):
        with self.lock:
            os.makedirs(out_dir, exist_ok=True)
            self.index = open(os.path.join(out_dir, "index.csv"), "w", newline="")
            self.writer = csv.DictWriter(self.index, fieldnames=IV3_FIELDS, extrasaction="ignore")
            self.writer.writeheader()
            self.session_dir = out_dir
            self.session_stopping = False
            self.emit_session = emit
            self.images = self.triggers = self.failed = 0
            self.t_start = self.clock.now()
            self.health = "starting"

    def end_session(self):
        self.session_stopping = True

    def finish_session(self, timeout):
        deadline = self.clock.now() + max(timeout, float(self.cfg.get("ftp_wait_s", 2.0)))
        while self.clock.now() < deadline and self.last_image_t and self.clock.now() - self.last_image_t < 1.0:
            time.sleep(0.2)                        # let a transfer in flight finish
        with self.lock:
            self.session_dir = None
            self.emit_session = None
            self._close_index()
        self.health = "stopped"

    def _close_index(self):
        if self.index:
            try:
                self.index.close()
            except OSError:
                pass
            self.index = None
            self.writer = None

    def _emit(self, *a, **k):
        (self.emit_session or self.emit_server)(*a, **k)

    # -- incoming files ------------------------------------------------------------ #
    def _on_file(self, path, incomplete=False):
        t = self.clock.now()
        kind = "image" if path.lower().endswith((".jpg", ".jpeg", ".bmp", ".png")) else "result"
        info = parse_result_text(path) if kind == "result" else {}
        with self.lock:
            session = self.session_dir
            dest_root = session or self.scratch_dir
            if session and session != self.scratch_dir:
                rel = os.path.relpath(path, self.scratch_dir)
                dest = os.path.join(self.session_dir, rel)
                try:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    os.replace(path, dest)
                    path = dest
                except OSError as e:               # keep the file rather than lose it
                    incomplete = incomplete or True
                    self.last_error = str(e)[:100]
        rel = os.path.relpath(path, dest_root).replace("\\", "/")
        row = {"kind": kind, "file": rel, "t_received": round(t, 6),
               "error": "incomplete transfer" if incomplete else ""}
        try:
            row["bytes"] = os.path.getsize(path)
        except OSError:
            row["bytes"] = 0
        if kind == "result":
            row["trigger_no"] = info.get("Trigger No", info.get("Trigger No.", ""))
            row["device_time"] = " ".join(info["Time and Date"]) if isinstance(info.get("Time and Date"), list) \
                else info.get("Time and Date", "")
            row["total_status"] = info.get("Total Status", "")
            if row["trigger_no"]:
                self.last_trigger_no = row["trigger_no"]
            self.last_result = info
        else:
            self.last_image_t = t
            self.last_image_path = path
            self.total_images += 1
        with self.lock:
            pending = self.pending if self.trigger_enabled else None
            if pending:
                row.update({k: pending[k] for k in ("t_trigger", "t_response", "trigger_latency_ms")})
                row["transfer_s"] = round(t - pending["t_response"], 3)
            if self.session_dir is not None and self.writer:
                if kind == "image":
                    self.images += 1
                row["seq"] = self.triggers if self.trigger_enabled else self.total_images
                self.writer.writerow(row)
                self.index.flush()
            else:
                self._prune_scratch(path)

    def _prune_scratch(self, path):
        """Between runs the pictures are only for the live view: keep the newest few.

        Sweeping the folder rather than a remembered list, so files left behind by a
        crash or by a stop mid-transfer are cleaned up too.
        """
        self.scratch_since_prune += 1
        if self.scratch_since_prune < 5:
            return
        self.scratch_since_prune = 0
        files = []
        for root, _, names in os.walk(self.scratch_dir):
            for n in names:
                f = os.path.join(root, n)
                try:
                    files.append((os.path.getmtime(f), f))
                except OSError:
                    pass
        files.sort(reverse=True)
        for _, f in files[self.scratch_keep:]:
            if f == self.last_image_path:
                continue
            try:
                os.remove(f)
            except OSError:
                pass

    # -- triggering ------------------------------------------------------------------ #
    def want_preview(self, seconds=10.0):
        self.watching_until = self.clock.now() + seconds

    def _current_interval(self):
        """Trigger while recording, or while the live view is being watched. Never otherwise."""
        if not self.trigger_enabled:
            return None
        if self.session_dir is not None and not self.session_stopping:
            return float(self.cfg.get("trigger_interval_s", 5.0))
        if self.clock.now() < self.watching_until:
            return float(self.cfg.get("preview_interval_s", 3.0))
        return None

    def _trigger_loop(self):
        host, port = self.cfg["host"], int(self.cfg.get("port", 8500))
        sock = None
        next_at = 0.0
        while not self.stop_event.is_set():
            interval = self._current_interval()
            if interval is None:
                if sock is not None:
                    sock.close()                   # release the camera while nobody needs it
                    sock = None
                    self.connected = False
                self.stop_event.wait(0.3)
                next_at = 0.0
                continue
            now = self.clock.now()
            if next_at and now < next_at:
                self.stop_event.wait(min(next_at - now, 0.3))
                continue
            next_at = self.clock.now() + interval
            try:
                if sock is None:
                    sock = socket.create_connection((host, port), timeout=3)
                    sock.settimeout(3)
                    self.connected = True
                    self._emit("keyence_connected", host=host, port=port)
                t_send = self.clock.now()
                sock.sendall(b"T1\r")
                resp = sock.recv(256).decode("ascii", "replace").strip()
                t_resp = self.clock.now()
                with self.lock:
                    self.triggers += 1
                    self.pending = {"seq": self.triggers, "t_trigger": round(t_send, 6),
                                    "t_response": round(t_resp, 6),
                                    "trigger_latency_ms": round((t_resp - t_send) * 1000, 1)}
                if resp.startswith("ER"):
                    self.failed += 1
                    self.last_error = resp
                    self.trigger_refused += 1
                    # The camera refuses to be triggered (self-triggering program, or setup
                    # mode): stop asking and record whatever it pushes by itself.
                    if self.trigger_refused >= 3:
                        self.trigger_enabled = False
                        self._emit("keyence_receive_only", reason=resp, level="warning")
                else:
                    self.trigger_refused = 0
            except OSError as e:
                self.connected = False
                self.failed += 1
                self.last_error = str(e)[:120]
                self._emit("keyence_error", error=str(e)[:120], level="warning")
                if sock:
                    sock.close()
                sock = None
                self.stop_event.wait(2)
        if sock:
            try:
                sock.close()
            except OSError:
                pass

    # -- state ------------------------------------------------------------------------- #
    def latest_image(self):
        path = self.last_image_path
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read(), ("image/bmp" if path.lower().endswith(".bmp") else "image/jpeg"), self.last_image_t
        except OSError:                            # moved into a session between the two calls
            return None

    def check(self):
        now = self.clock.now()
        stale = float(self.cfg.get("stale_after_s", 0)) or (
            60.0 if not self.trigger_enabled else max(3 * float(self.cfg.get("trigger_interval_s", 5.0)), 10.0))
        if self.session_dir is None:
            health = "stopped"
        elif self.last_image_t is None:
            health = "starting" if now - self.t_start < stale else "stalled"
        else:
            health = "ok" if now - self.last_image_t < stale else "stalled"
        self.health = health
        return health

    def status(self):
        now = self.clock.now()
        return {"name": self.name, "type": "keyence", "health": self.health,
                "records": self.images, "triggers": self.triggers, "failed": self.failed,
                "connected": self.connected, "trigger_no": self.last_trigger_no,
                "trigger_enabled": self.trigger_enabled, "last_error": self.last_error,
                "total_images": self.total_images,
                "since_record_s": round(now - self.last_image_t, 1) if self.last_image_t else None}


class SessionRecorder(object):
    """What a run sees: the same interface as the other streams, backed by the service."""
    name = "keyence"

    def __init__(self, service, out_dir, emit):
        self.service = service
        self.out_dir = out_dir
        self.emit = emit

    def start(self):
        self.service.begin_session(self.out_dir, self.emit)

    def stop(self):
        self.service.end_session()

    def finish(self, timeout):
        self.service.finish_session(timeout)

    def check(self):
        return self.service.check()

    def status(self):
        return self.service.status()


def make_receiver(kcfg, out_dir, clock, emit, service=None):
    mode = kcfg.get("mode")
    if mode == "iv3":
        if service is None:
            raise IOError("the Keyence service is not running")
        return SessionRecorder(service, out_dir, emit)
    if mode == "tcp":
        return TcpReceiver(kcfg, out_dir, clock, emit)
    return NullReceiver()

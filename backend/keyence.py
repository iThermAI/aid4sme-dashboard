"""Keyence IV3 receiver - pluggable (spec 8.2).

Interface: start() / stop() / finish(timeout) / check() / status(), same as the
other streams. Two implementations:

  off : placeholder until the OCR component is delivered
  tcp : TCP client for IV3 non-procedural output. Records are split on the
        configured delimiter and written verbatim to keyence/records.jsonl with
        the host arrival time. Parsing of the fields is deferred to
        post-processing, like every other stream. Untested against a real IV3.

An FTP-push receiver (pyftpdlib) can be added as a third class with the same
interface without touching the recorder.
"""
import json
import os
import socket
import threading


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
                "note": "Not connected - OCR component pending"}


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


def make_receiver(kcfg, out_dir, clock, emit):
    if kcfg.get("mode") == "tcp":
        return TcpReceiver(kcfg, out_dir, clock, emit)
    return NullReceiver()

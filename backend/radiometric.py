"""Radiometric poller: one thread per camera, paced at rate_hz.

Every response body is written untouched to radiometric_<cam>/<seq>.bin and
indexed in index.csv with send / header / receive times from the master clock.
Conversion to .npy happens offline. The only live work is a cheap look at the
payload: FFC freeze flag, duplicate detection and the max temperature, so the
operator sees range saturation during the run instead of after it.
"""
import collections
import csv
import hashlib
import json
import os
import struct
import threading
import time

import requests

from .isapi import P2P_PATH, classify, get_boundary, parse_multipart

try:
    import numpy as np
except ImportError:  # the capture path works without numpy; only live stats are lost
    np = None

INDEX_FIELDS = ["seq", "t_send", "t_hdr", "t_recv", "ttfb_ms", "rtt_ms", "status", "bytes", "file",
                "p2p_len", "p2p_ok", "freeze", "dup", "tmin", "tmax", "tmean", "saturated",
                "overrun", "error"]


def http_fetcher(camera, timeout):
    session = camera.new_session()
    url = camera.url(P2P_PATH.format(ch=camera.thermal_channel))

    def fetch(clock):
        t_send = clock.now()
        try:
            r = session.get(url, timeout=timeout, stream=True)
            t_hdr = clock.now()
            body = r.content
            t_recv = clock.now()
            return r.status_code, r.headers.get("Content-Type", ""), body, t_send, t_hdr, t_recv, ""
        except requests.RequestException as e:
            t = clock.now()
            return -1, "", b"", t_send, t, t, type(e).__name__
    return fetch


def simulated_fetcher(w, h, freeze_every=97):
    """Produces bodies in the camera's own multipart format, so the whole
    parsing path is exercised without hardware."""
    state = {"n": 0}

    def fetch(clock):
        t_send = clock.now()
        time.sleep(0.04)
        n = state["n"]
        state["n"] += 1
        t = time.time()
        vals = [25.0 + 10.0 * ((x + y + int(t * 10)) % 40) / 40.0 for y in range(h) for x in range(w)]
        p2p = struct.pack("<%df" % len(vals), *vals)
        meta = {"JpegPictureWithAppendData": {
            "channel": 2, "jpegPicLen": 4, "jpegPicWidth": w, "jpegPicHeight": h,
            "p2pDataLen": len(p2p), "temperatureDataLength": 4,
            "isFreezedata": (n % freeze_every) == freeze_every - 1}}
        b = b"boundary"
        body = (b"--" + b + b"\r\nContent-Type: application/json\r\n\r\n" + json.dumps(meta).encode()
                + b"\r\n--" + b + b"\r\nContent-Type: image/pjpeg\r\nContent-Length: 4\r\n\r\n\xff\xd8\xff\xd9"
                + b"\r\n--" + b + b"\r\nContent-Type: application/octet-stream\r\nContent-Length: %d\r\n\r\n"
                % len(p2p) + p2p + b"\r\n--" + b + b"--\r\n")
        t_hdr = clock.now()
        return 200, "multipart/form-data; boundary=boundary", body, t_send, t_hdr, clock.now(), ""
    return fetch


class RadiometricPoller(object):
    def __init__(self, cam_id, fetch, out_dir, rate_hz, range_max_c, clock, emit):
        self.name = "%s_radiometric" % cam_id
        self.cam_id = cam_id
        self.fetch = fetch
        self.out_dir = out_dir
        self.period = 1.0 / rate_hz
        self.rate_hz = rate_hz
        self.range_max_c = range_max_c
        self.clock = clock
        self.emit = emit
        self.stop_event = threading.Event()
        self.thread = None
        self.health = "starting"
        self.seq = 0
        self.ok = 0
        self.failed = 0
        self.unique = 0
        self.freeze_total = 0
        self.saturated_total = 0
        self.last_ok_t = None
        self.last_rtt_ms = None
        self.last_tmax = None
        self.bytes_total = 0
        self.t_start = None
        self.recent_unique = collections.deque(maxlen=64)   # host times of new matrices
        self._last_hash = None
        self._first_meta_saved = False
        self._freeze_active = False

    def start(self):
        os.makedirs(self.out_dir, exist_ok=True)
        self.t_start = self.clock.now()
        self.thread = threading.Thread(target=self._run, name=self.name)
        self.thread.daemon = True
        self.thread.start()
        self.emit("stream_started", stream=self.name)

    def _inspect(self, ctype, body, row):
        parts = parse_multipart(body, get_boundary(ctype))
        meta, p2p, _ = classify(parts)
        info = (meta or {}).get("JpegPictureWithAppendData", meta or {})
        if not self._first_meta_saved and meta:
            with open(os.path.join(self.out_dir, "first_meta.json"), "w") as f:
                json.dump(meta, f, indent=2)
            self._first_meta_saved = True
        freeze = bool(info.get("isFreezedata"))
        row["freeze"] = int(freeze)
        if freeze != self._freeze_active:
            self._freeze_active = freeze
            self.emit("ffc_freeze_start" if freeze else "ffc_freeze_end", stream=self.name, seq=row["seq"])
        if freeze:
            self.freeze_total += 1
        if p2p is None:
            row["error"] = "no octet-stream part"
            return False
        declared = int(info.get("p2pDataLen") or 0)
        row["p2p_len"] = len(p2p)
        row["p2p_ok"] = int(declared > 0 and len(p2p) >= declared)
        digest = hashlib.md5(p2p).digest()
        row["dup"] = int(digest == self._last_hash)
        self._last_hash = digest
        if not row["dup"]:
            self.unique += 1
            self.recent_unique.append(row["t_recv_f"])
        tdl = int(info.get("temperatureDataLength") or 0)
        if np is not None and tdl == 4:
            n = (declared or len(p2p)) // 4
            arr = np.frombuffer(p2p[:n * 4], dtype="<f4")
            tmax = float(arr.max())
            row.update(tmin=round(float(arr.min()), 2), tmax=round(tmax, 2), tmean=round(float(arr.mean()), 2))
            self.last_tmax = round(tmax, 1)
            if tmax >= self.range_max_c - 0.5:
                row["saturated"] = 1
                self.saturated_total += 1
                if self.saturated_total == 1:
                    self.emit("range_saturation", stream=self.name, tmax=round(tmax, 2),
                              range_max_c=self.range_max_c, level="warning")
            else:
                row["saturated"] = 0
        return bool(row["p2p_ok"])

    def _run(self):
        index_path = os.path.join(self.out_dir, "index.csv")
        next_slot = time.perf_counter()
        with open(index_path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS, extrasaction="ignore")
            writer.writeheader()
            while not self.stop_event.is_set():
                wait = next_slot - time.perf_counter()
                if wait > 0 and self.stop_event.wait(wait):
                    break
                next_slot += self.period
                status, ctype, body, t_send, t_hdr, t_recv, err = self.fetch(self.clock)
                overrun = 0
                if time.perf_counter() > next_slot:
                    overrun, next_slot = 1, time.perf_counter()
                row = dict.fromkeys(INDEX_FIELDS, "")
                row.update(seq=self.seq, t_send="%.6f" % t_send, t_hdr="%.6f" % t_hdr,
                           t_recv="%.6f" % t_recv, ttfb_ms=round((t_hdr - t_send) * 1000, 2),
                           rtt_ms=round((t_recv - t_send) * 1000, 2), status=status,
                           bytes=len(body), overrun=overrun, error=err, t_recv_f=t_recv)
                good = False
                if status == 200 and body:
                    fn = "%06d.bin" % self.seq
                    with open(os.path.join(self.out_dir, fn), "wb") as f:
                        f.write(body)                               # untouched payload
                    row["file"] = fn
                    self.bytes_total += len(body)
                    try:
                        good = self._inspect(ctype, body, row)
                    except Exception as e:  # noqa - never let inspection kill capture
                        row["error"] = "inspect: %s" % type(e).__name__
                elif status > 0:
                    row["error"] = "HTTP %d" % status
                if good:
                    self.ok += 1
                    self.last_ok_t = t_recv
                    self.last_rtt_ms = row["rtt_ms"]
                else:
                    self.failed += 1
                    if self.failed in (1, 10, 100) or self.failed % 1000 == 0:
                        self.emit("radiometric_error", stream=self.name, seq=self.seq,
                                  error=row["error"] or "bad payload", failures=self.failed,
                                  level="warning")
                    if status == 401 and self.failed >= 3 and self.ok == 0:
                        self.emit("radiometric_stopped", stream=self.name,
                                  reason="repeated HTTP 401, avoiding account lock-out", level="warning")
                        break
                writer.writerow(row)
                fh.flush()
                self.seq += 1

    def check(self):
        now = self.clock.now()
        alive = self.thread is not None and self.thread.is_alive()
        if not alive:
            health = "stopped" if self.stop_event.is_set() else "dead"
        elif self.stop_event.is_set():
            health = "stopping"
        elif self.last_ok_t is None:
            health = "starting" if now - self.t_start < 10 else "stalled"
        elif now - self.last_ok_t > max(3 * self.period, 3.0) + 2:
            health = "stalled"
        else:
            health = "ok"
        if health != self.health:
            self.emit("stream_health", stream=self.name, health=health, previous=self.health,
                      level="warning" if health in ("dead", "stalled") else "info")
            self.health = health
        return health

    def status(self):
        now = self.clock.now()
        recent = [t for t in self.recent_unique if now - t <= 10.0]
        return {
            "name": self.name, "type": "radiometric", "health": self.health,
            "polls": self.seq, "ok": self.ok, "failed": self.failed, "unique": self.unique,
            "fps": round(len(recent) / 10.0, 2) if now - self.t_start >= 10 else round(
                self.unique / max(now - self.t_start, 1), 2),
            "target_fps": self.rate_hz,
            "rtt_ms": self.last_rtt_ms, "tmax": self.last_tmax,
            "freeze": self.freeze_total, "saturated": self.saturated_total,
            "freeze_active": self._freeze_active,
            "mb": round(self.bytes_total / 1e6, 1),
            "since_ok_s": round(now - self.last_ok_t, 1) if self.last_ok_t else None,
        }

    def stop(self):
        self.stop_event.set()

    def finish(self, timeout):
        if self.thread:
            self.thread.join(timeout)
        self.check()
        self.emit("stream_finished", stream=self.name, polls=self.seq, ok=self.ok, failed=self.failed)

"""One Recording = one session folder.

<YYYYMMDD_HHMMSS>_<mould>_run<NNN>/
  metadata.json          operator entries, crops, camera config, host, verification
  events.jsonl           every state change, watchdog event, operator note
  capture.log            human-readable log of the same
  verification.json      post-stop checks
  cad_asset.glb          if uploaded
  raw/
    <stream>_NNN.mkv, <stream>_segments.csv, <stream>_progress.csv, <stream>_ffmpeg.log
    radiometric_<cam>/NNNNNN.bin + index.csv + first_meta.json
    keyence/records.jsonl
    camera_config/<cam>/*.xml|json
"""
import json
import logging
import os
import platform
import shutil
import socket
import sys
import threading
import time

from . import config as config_mod
from . import camerainfo, isapi, verify, winutil
from .stores import slugify
from .clock import iso
from .keyence import make_receiver
from .radiometric import RadiometricPoller, http_fetcher, simulated_fetcher
from .video import (COPY_CODEC, SIM_CODEC, FfmpegStream, rtsp_input_args, simulated_input_args)

log = logging.getLogger("aid4sme")
SCHEMA = "aid4sme.raw_session/1"


def new_session_id(sessions_dir, mould_id, run_number):
    base = "%s_%s_run%03d" % (time.strftime("%Y%m%d_%H%M%S"), slugify(mould_id or "nomould"), run_number)
    sid, n = base, 1
    while os.path.exists(os.path.join(sessions_dir, sid)):
        n += 1
        sid = "%s_%d" % (base, n)
    return sid


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


class Recording(object):
    def __init__(self, ctl, draft, run_number):
        self.ctl = ctl
        self.cfg = ctl.cfg
        self.clock = ctl.clock
        self.draft = draft
        self.run_number = run_number
        self.stop_after_s = float((draft.get("options") or {}).get("stop_after_s") or 0)
        self.sid = new_session_id(ctl.sessions_dir, draft["metadata"].get("mould_id"), run_number)
        self.dir = os.path.join(ctl.sessions_dir, self.sid)
        self.raw = os.path.join(self.dir, "raw")
        self.state = "starting"
        self.t_start = None
        self.t_stop = None
        self.stop_reason = None
        self.streams = []
        self.pollers = []
        self.keyence = None
        self.marks = []
        self.recent_events = []
        self.result = None
        self._events_lock = threading.Lock()
        self._events = None
        self._log_handler = None
        self._stop_evt = threading.Event()
        self._watchdog = None
        self._had_stall = set()
        self.metadata = None
        self.range_key = draft["metadata"].get("thermal_range") or self.cfg["default_thermal_range"]

    # ------------------------------------------------------------------ #
    def emit(self, etype, level="info", **fields):
        t = self.clock.now()
        rec = {"t": round(t, 6), "time": iso(t), "type": etype}
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False)
        with self._events_lock:
            if self._events:
                self._events.write(line + "\n")
                self._events.flush()
            self.recent_events.append({"time": rec["time"], "type": etype, "level": level,
                                       "detail": {k: v for k, v in fields.items()}})
            del self.recent_events[:-30]
        getattr(log, "warning" if level == "warning" else "info")("%s %s", etype, fields)

    # ------------------------------------------------------------------ #
    def start(self):
        cfg, sim = self.cfg, self.cfg["simulate"]
        os.makedirs(self.raw)
        self._events = open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8")
        self._log_handler = logging.FileHandler(os.path.join(self.dir, "capture.log"), encoding="utf-8")
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(self._log_handler)
        self.emit("session_created", session=self.sid, simulate=sim)

        # 1. Camera configuration snapshot, before any load is put on the cameras.
        cam_meta = {}
        snaps = {}
        threads = []

        def snap(cam):
            dest = os.path.join(self.raw, "camera_config", cam.id)
            snaps[cam.id] = cam.snapshot(cfg["config_snapshot_paths"], dest)

        for cam in self.ctl.cameras.values():
            th = threading.Thread(target=snap, args=(cam,))
            th.start()
            threads.append(th)
        for th in threads:
            th.join(90)
        reference = self.ctl.reference_profile()
        for cid, snap_ in snaps.items():
            ref_sections = ((reference or {}).get("cameras") or {}).get(cid)
            dev = self.ctl.devices.get(cid, {})
            details = camerainfo.build(cfg, self.ctl.cameras[cid], snap_, ref_sections,
                                       dev.get("drift_s"), self.range_key)
            cam_meta[cid] = {
                "ip": self.ctl.cameras[cid].ip,
                "device": details.get("identity"),
                "streams": {st["kind"]: {k: st.get(k) for k in ("name", "codec", "width", "height", "fps",
                                                                "bitrate_type", "bitrate_kbps", "gop",
                                                                "overlay", "input_name")}
                            for st in details.get("streams", [])},
                "thermal": {t["key"]: t["value"] for t in details.get("thermal", [])},
                "settings_warnings": [c for c in details.get("checks", []) if c.get("status") == "warn"],
                "config_snapshot_dir": "raw/camera_config/%s" % cid,
                "reference_profile": (reference or {}).get("name"),
                "config_vs_reference": (None if ref_sections is None else
                                        isapi.diff_sections(ref_sections, snap_, cfg["config_ignore_keys"])),
                "clock_drift_s": dev.get("drift_s"),
            }
        self.emit("config_snapshot_done", cameras=list(snaps))

        # 2. CAD asset.
        cad_name = None
        if self.draft.get("cad") and os.path.isfile(self.ctl.draft_cad_path):
            shutil.copyfile(self.ctl.draft_cad_path, os.path.join(self.dir, "cad_asset.glb"))
            cad_name = "cad_asset.glb"

        # 3. Metadata (status=recording) - updated at stop.
        self.metadata = {
            "schema": SCHEMA,
            "session_id": self.sid,
            "run_number": self.run_number,
            "status": "recording",
            "planned_stop_after_s": self.stop_after_s or None,
            "operator_verdict": None,
            "simulated": sim,
            "operator_metadata": self.draft["metadata"],
            "thermal_range": dict(key=self.range_key, **cfg["thermal_ranges"][self.range_key]),
            "regions": self.draft.get("regions", {}),
            "cad_asset": cad_name,
            "cad_original_filename": (self.draft.get("cad") or {}).get("filename"),
            "cameras": cam_meta,
            "streams": {},
            "radiometric": {"enabled": cfg["radiometric"]["enabled"], "rate_hz": cfg["radiometric"]["rate_hz"],
                            "sensor": [cfg["radiometric"]["sensor_width"], cfg["radiometric"]["sensor_height"]]},
            "keyence": {"mode": cfg["keyence"]["mode"]},
            "segment_seconds": cfg["segment_seconds"],
            "timebase": "Host master clock: Unix epoch seconds, perf_counter resolution. "
                        "All t_* fields in this session share it.",
            "host": {"hostname": socket.gethostname(), "platform": platform.platform(),
                     "python": sys.version.split()[0], "ffmpeg": self.ctl.ffmpeg_line,
                     "app_version": config_mod.APP_VERSION},
        }

        # 4. Launch.
        self.t_start = self.clock.now()
        self.metadata["started_at"] = iso(self.t_start)
        self.metadata["started_epoch"] = round(self.t_start, 6)
        for name, cam_cfg, kind in config_mod.stream_names(cfg):
            scfg = cfg["streams"][kind]
            if sim:
                inp, codec = simulated_input_args(kind, cfg["nominal_fps"]), SIM_CODEC
            else:
                inp = rtsp_input_args(cam_cfg, scfg["rtsp_channel"], self.ctl.ffmpeg_major, cfg["rtsp_timeout_s"])
                codec = COPY_CODEC
            s = FfmpegStream(name, inp, codec, self.raw, cfg, self.clock, self.emit)
            self.metadata["streams"][name] = {
                "camera": cam_cfg["id"], "kind": kind, "rtsp_channel": scfg["rtsp_channel"],
                "width": scfg["width"], "height": scfg["height"], "nominal_fps": cfg["nominal_fps"],
                "files": "raw/%s_NNN.mkv" % name}
            self.streams.append(s)
        write_json(os.path.join(self.dir, "metadata.json"), self.metadata)

        for s in self.streams:
            s.start()
        rcfg = cfg["radiometric"]
        if rcfg["enabled"]:
            range_max = cfg["thermal_ranges"][self.range_key]["max_c"]
            for cam in self.ctl.cameras.values():
                out = os.path.join(self.raw, "radiometric_%s" % cam.id)
                fetch = (simulated_fetcher(rcfg["sensor_width"], rcfg["sensor_height"]) if sim
                         else http_fetcher(cam, rcfg["timeout_s"]))
                p = RadiometricPoller(cam.id, fetch, out, rcfg["rate_hz"], range_max, self.clock, self.emit)
                p.start()
                self.pollers.append(p)
        self.keyence = make_receiver(cfg["keyence"], os.path.join(self.raw, "keyence"), self.clock, self.emit)
        self.keyence.start()

        self.state = "recording"
        self.emit("recording_started", session=self.sid)
        self._watchdog = threading.Thread(target=self._watch, name="watchdog")
        self._watchdog.daemon = True
        self._watchdog.start()

    # ------------------------------------------------------------------ #
    def _watch(self):
        winutil.prevent_sleep(True)
        try:
            while not self._stop_evt.wait(1.0):
                for s in self.streams + self.pollers:
                    if s.check() in ("stalled", "dead"):
                        self._had_stall.add(s.name)
                self.keyence.check()
                elapsed = self.clock.now() - self.t_start
                if self.stop_after_s and elapsed >= self.stop_after_s:
                    self.stop("planned_duration")
                elif elapsed >= self.cfg["max_record_seconds"]:
                    self.stop("max_duration")
                free_gb = shutil.disk_usage(self.dir).free / 1e9
                if free_gb < self.cfg["abort_free_disk_gb"]:
                    self.stop("disk_full")
        finally:
            winutil.prevent_sleep(False)

    def mark(self, note):
        t = self.clock.now()
        m = {"time": iso(t), "t": round(t, 6), "elapsed_s": round(t - self.t_start, 1), "note": note}
        self.marks.append(m)
        self.emit("operator_note", note=note, elapsed_s=m["elapsed_s"])
        return m

    def stop(self, reason="operator"):
        if self.state != "recording":
            return False
        self.state = "stopping"
        self.stop_reason = reason
        self.t_stop = self.clock.now()
        self.emit("stop_requested", reason=reason)
        th = threading.Thread(target=self._finish, name="finisher")
        th.daemon = True
        th.start()
        return True

    def _finish(self):
        try:
            for s in self.streams:
                s.request_stop()
            for p in self.pollers:
                p.stop()
            self.keyence.stop()
            how = {}
            grace = self.cfg["stop_grace_s"]
            for s in self.streams:
                how[s.name] = s.finish(grace)
            for p in self.pollers:
                p.finish(self.cfg["radiometric"]["timeout_s"] + 2)
            self.keyence.finish(3)
            self._stop_evt.set()
            self.emit("capture_stopped")
            self.state = "verifying"
            self.result = self._verify(how)
        except Exception as e:  # noqa
            log.exception("finish failed")
            self.result = {"overall_pass": False, "error": str(e)}
        finally:
            self._finalise()
            self.state = "finished"

    def abort(self, error):
        """Start failed part-way: stop whatever was launched and close the folder."""
        self.emit("start_failed", error=error, level="warning")
        self.stop_reason = "start_failed"
        self.t_stop = self.clock.now()
        self._stop_evt.set()
        for s in self.streams:
            if s.proc:
                s.request_stop()
                s.finish(3)
        for p in self.pollers:
            p.stop()
            p.finish(3)
        if self.keyence:
            self.keyence.stop()
        self.result = {"overall_pass": False, "error": error}
        if self.t_start is None:
            self.t_start = self.t_stop
        self._finalise()
        if self.metadata:
            self.metadata["status"] = "failed"
            write_json(os.path.join(self.dir, "metadata.json"), self.metadata)
        self.state = "finished"

    def _verify(self, how):
        cfg = self.cfg
        wall = self.t_stop - self.t_start
        video = [verify.verify_video(self.raw, s.name, cfg["ffprobe"], cfg["nominal_fps"], wall,
                                     how.get(s.name), s.name in self._had_stall) for s in self.streams]
        rad = [verify.verify_radiometric(p.out_dir, p.name, p.rate_hz) for p in self.pollers]
        first = self.streams[0].name if self.streams else None
        res = {"duration_s": round(wall, 1), "video": video, "radiometric": rad,
               "keyence": self.keyence.status(),
               "start_offsets_ms_vs_%s" % first: verify.relative_offsets(video, first),
               "start_offsets_note": "Host-arrival estimate from FFmpeg progress reports. Excludes each "
                                     "stream's camera-side latency; not a substitute for scene "
                                     "cross-correlation.",
               "stop_reason": self.stop_reason,
               "overall_pass": all(v["pass"] for v in video) and all(r["pass"] for r in rad)}
        write_json(os.path.join(self.dir, "verification.json"), res)
        self.emit("verification_done", overall_pass=res["overall_pass"])
        return res

    def _finalise(self):
        if self.metadata is None:
            self.metadata = {"schema": SCHEMA, "session_id": self.sid,
                             "operator_metadata": self.draft.get("metadata")}
        md = self.metadata
        md["status"] = "complete" if (self.result or {}).get("overall_pass") else "check"
        md["stopped_at"] = iso(self.t_stop) if self.t_stop else None
        md["duration_s"] = round(self.t_stop - self.t_start, 2) if self.t_stop and self.t_start else None
        md["stop_reason"] = self.stop_reason
        md["operator_notes_during_run"] = self.marks
        md["verification_summary"] = summary(self.result)
        try:
            write_json(os.path.join(self.dir, "metadata.json"), md)
        except OSError:
            log.exception("could not write metadata")
        self.emit("session_closed", status=md["status"])
        with self._events_lock:
            if self._events:
                self._events.close()
                self._events = None
        if self._log_handler:
            log.removeHandler(self._log_handler)
            self._log_handler.close()

    # ------------------------------------------------------------------ #
    def status(self):
        now = self.clock.now()
        end = self.t_stop if self.t_stop else now
        return {
            "session_id": self.sid, "folder": self.dir, "state": self.state,
            "run_number": self.run_number, "mould_id": self.draft["metadata"].get("mould_id"),
            "stop_after_s": self.stop_after_s or None,
            "elapsed_s": round(end - self.t_start, 1) if self.t_start else 0,
            "max_s": self.cfg["max_record_seconds"],
            "streams": ([s.status() for s in self.streams] + [p.status() for p in self.pollers]
                        + ([self.keyence.status()] if self.keyence else [])),
            "marks": self.marks[-10:],
            "events": self.recent_events[-8:],
            "stop_reason": self.stop_reason,
            "free_gb": round(shutil.disk_usage(self.dir).free / 1e9, 1),
        }


def summary(result):
    if not result:
        return None
    return {"overall_pass": result.get("overall_pass"),
            "video": {v["stream"]: v["pass"] for v in result.get("video", [])},
            "radiometric": {r["stream"]: r["pass"] for r in result.get("radiometric", [])}}

"""Single source of truth for the dashboard.

Every rule that gates recording lives here, not in the browser. Messages to
the operator are returned as codes with parameters; the dashboard translates
them (English / Slovenian).
"""
import collections
import json
import logging
import os
import re
import shutil
import socket
import struct
import threading
import time

from . import camerainfo
from . import config as config_mod
from . import isapi
from .clock import CLOCK, iso
from .recorder import Recording, write_json
from .simcam import SimCamera
from .keyence import make_receiver
from .stores import JsonStore
from .video import ffmpeg_version

log = logging.getLogger("aid4sme")

ACTIVE = ("starting", "recording", "stopping", "verifying")
METADATA_FIELDS = ("operator", "mould_id", "part_number", "material", "shot_counter_start",
                   "thermal_range", "notes")
AUTO_INCREMENT_FIELDS = ("mould_id", "part_number", "shot_counter_start")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")


class StateError(Exception):
    pass


def increment_trailing(value):
    """M-012 -> M-013, part7 -> part8, 'abc' -> 'abc' (no number, unchanged)."""
    m = re.match(r"^(.*?)(\d+)(\D*)$", value or "")
    if not m:
        return value
    digits = m.group(2)
    return m.group(1) + str(int(digits) + 1).zfill(len(digits)) + m.group(3)


class Controller(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.clock = CLOCK
        data = cfg["data_dir"]
        self.sessions_dir = os.path.join(data, "sessions")
        self.draft_dir = os.path.join(data, "draft")
        for d in (self.sessions_dir, self.draft_dir):
            os.makedirs(d, exist_ok=True)
        self.profiles = JsonStore(os.path.join(data, "camera_profiles"))
        self.parts = JsonStore(os.path.join(data, "part_presets"))
        self.prefs_path = os.path.join(data, "preferences.json")
        self.draft_path = os.path.join(self.draft_dir, "draft.json")
        self.draft_cad_path = os.path.join(self.draft_dir, "cad_asset.glb")
        self.lock = threading.RLock()
        self.cameras = self._build_cameras()
        self.devices = {}
        self.camera_checks = {}
        self.keyence_state = None
        self.keyence_preview = None          # live view receiver, only between runs
        self.keyence_preview_wanted = 0.0
        self.recording = None
        self.prefs = self._load_prefs()
        self.draft = self._load_draft()
        self.ffmpeg_major, self.ffmpeg_line = ffmpeg_version(cfg["ffmpeg"])
        self._preview_cache = {}
        self._matrix_cache = {}
        self._locks = collections.defaultdict(threading.Lock)
        self._index = {}
        self._index_at = 0.0
        self._recover_interrupted()
        self._monitor_stop = threading.Event()
        self._check_due = 0.0
        self._monitor = threading.Thread(target=self._monitor_loop, name="device-monitor")
        self._monitor.daemon = True
        self._monitor.start()

    def _build_cameras(self):
        cls = SimCamera if self.cfg["simulate"] else isapi.Camera
        return collections.OrderedDict((c["id"], cls(c)) for c in self.cfg["cameras"])

    @property
    def state(self):
        return self.recording.state if self.recording else "idle"

    def _require_idle(self):
        if self.state in ACTIVE:
            raise StateError("busy_recording")

    def _recover_interrupted(self):
        for sid in os.listdir(self.sessions_dir):
            path = os.path.join(self.sessions_dir, sid, "metadata.json")
            try:
                with open(path, encoding="utf-8") as f:
                    md = json.load(f)
            except (OSError, ValueError):
                continue
            if md.get("status") == "recording":
                md["status"] = "interrupted"
                md["stop_reason"] = "server_stopped"
                write_json(path, md)
                log.warning("Marked %s as interrupted", sid)

    # ------------------------------------------------------------------ #
    # Preferences
    # ------------------------------------------------------------------ #
    def _load_prefs(self):
        prefs = {"language": "en", "theme": "light", "reference_profile": None, "auto_increment": []}
        try:
            with open(self.prefs_path, encoding="utf-8") as f:
                prefs.update(json.load(f))
        except (OSError, ValueError):
            pass
        return prefs

    def set_prefs(self, data):
        with self.lock:
            if data.get("language") in ("en", "sl"):
                self.prefs["language"] = data["language"]
            if data.get("theme") in ("light", "dark"):
                self.prefs["theme"] = data["theme"]
            if isinstance(data.get("auto_increment"), list):
                self.prefs["auto_increment"] = [f for f in data["auto_increment"] if f in AUTO_INCREMENT_FIELDS]
            if "reference_profile" in data:
                ref = data["reference_profile"]
                if ref:
                    self.profiles.load(ref)            # KeyError / OSError if unknown
                self.prefs["reference_profile"] = ref or None
                self._check_due = 0
            write_json(self.prefs_path, self.prefs)
            return self.prefs

    # ------------------------------------------------------------------ #
    # Device monitor: clocks every few seconds, settings every two minutes
    # ------------------------------------------------------------------ #
    def _monitor_loop(self):
        while not self._monitor_stop.is_set():
            active = self.state in ACTIVE
            for cam in list(self.cameras.values()):
                self.devices[cam.id] = self._check_clock(cam)
            self.keyence_state = self._check_keyence()
            if self.keyence_preview and (self.state in ACTIVE or
                                         time.time() - self.keyence_preview_wanted > 10):
                self._stop_keyence_preview()
            if not active:
                # Keep the session clock on the wall clock; never while recording.
                off = self.clock.wall_offset()
                if abs(off) > 0.5:
                    corr = self.clock.resync()
                    log.info("Master clock re-anchored to the wall clock: %+.3f s", corr)
            if not active and time.time() >= self._check_due:
                try:
                    self.check_cameras()
                except Exception:  # noqa
                    log.exception("settings check failed")
                self._check_due = time.time() + 120
            self._monitor_stop.wait(30 if active else self.cfg["device_poll_s"])

    def _check_clock(self, cam):
        entry = {"id": cam.id, "ip": cam.ip, "checked_at": iso(self.clock.now())}
        try:
            # Compared against the PC's wall clock, not the session clock, which may
            # have parted from it since the server started.
            w0 = time.time()
            dev_t, t_send, t_recv = cam.device_time(self.clock)
            w1 = time.time()
            entry.update(reachable=True, rtt_ms=round((t_recv - t_send) * 1000, 1),
                         drift_s=round(dev_t - (w0 + w1) / 2, 1))
        except Exception as e:  # noqa
            entry.update(reachable=False, error=str(e)[:160], auth="401" in str(e))
        return entry

    def _check_keyence(self):
        """The IV3 only answers while it is reachable; check before a run, not during."""
        kc = self.cfg["keyence"]
        if kc["mode"] != "iv3":
            return {"mode": kc["mode"]}
        state = {"mode": "iv3", "host": kc["host"], "port": int(kc["port"]),
                 "trigger_interval_s": kc["trigger_interval_s"], "ftp_port": kc["ftp_port"]}
        if self.state in ACTIVE:
            return dict(self.keyence_state or state, recording=True)
        try:
            s = socket.create_connection((kc["host"], int(kc["port"])), 1.5)
            s.close()
            state["reachable"] = True
        except OSError as e:
            state.update(reachable=False, error=type(e).__name__)
        return state

    def _keyence_preview_dir(self):
        return os.path.join(self.draft_dir, "keyence_preview")

    def _start_keyence_preview(self):
        kc = dict(self.cfg["keyence"])
        kc["trigger_interval_s"] = kc.get("preview_interval_s", 3.0)
        folder = self._keyence_preview_dir()
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
        rx = make_receiver(kc, folder, self.clock, lambda *a, **k: None)
        rx.start()
        self.keyence_preview = rx
        log.info("Keyence live view started")

    def _stop_keyence_preview(self):
        rx, self.keyence_preview = self.keyence_preview, None
        if rx:
            rx.stop()
            try:
                rx.finish(2)
            except Exception:                      # noqa - best effort
                pass
            log.info("Keyence live view stopped")

    def keyence_preview_image(self):
        """Latest IV3 picture, triggering the camera in the background while watched."""
        if self.cfg["keyence"]["mode"] != "iv3":
            raise KeyError("keyence")
        if self.state in ACTIVE:
            raise StateError("previews_paused")
        self.keyence_preview_wanted = time.time()
        if self.keyence_preview is None:
            self._start_keyence_preview()
        latest = self.keyence_preview.latest_image()
        if latest is None:
            raise IOError("waiting for the first image from the IV3")
        body, ctype, _ = latest
        return body, ctype

    def keyence_status(self):
        st = dict(self.keyence_state or {"mode": self.cfg["keyence"]["mode"]})
        rx = self.keyence_preview if self.keyence_preview else (
            self.recording.keyence if self.recording and self.state in ACTIVE else None)
        if rx is not None and getattr(rx, "last_image_t", None):
            st["last_image_age_s"] = round(self.clock.now() - rx.last_image_t, 1)
            st["trigger_no"] = rx.last_trigger_no
            st["result"] = {k: v for k, v in (rx.last_result or {}).items() if isinstance(v, str)}
            st["images"] = rx.images
        st["ftp_folder"] = self.cfg["data_dir"]
        st["image_size"] = [self.cfg["keyence"]["image_width"], self.cfg["keyence"]["image_height"]]
        return st

    def keyence_trigger(self):
        """One picture on demand, from the Cameras page."""
        if self.state in ACTIVE:
            raise StateError("busy_recording")
        if self.cfg["keyence"]["mode"] != "iv3":
            raise ValueError("keyence_not_configured")
        self.keyence_preview_wanted = time.time()
        if self.keyence_preview is None:
            self._start_keyence_preview()
        rx = self.keyence_preview
        before = rx.images
        deadline = time.time() + 8
        while time.time() < deadline and rx.images == before:
            time.sleep(0.2)
        return {"ok": rx.images > before, "images": rx.images, "trigger_no": rx.last_trigger_no,
                "connected": rx.connected, "failed": rx.failed}

    def update_keyence(self, data):
        with self.lock:
            self._require_idle()
            kc = dict(self.cfg["keyence"])
            if data.get("mode") in ("off", "iv3", "tcp"):
                kc["mode"] = data["mode"]
            if data.get("host"):
                if not HOST_RE.match(str(data["host"]).strip()):
                    raise ValueError("invalid_address")
                kc["host"] = str(data["host"]).strip()
            for key, lo, hi in (("port", 1, 65535), ("ftp_port", 1, 65535)):
                if data.get(key):
                    kc[key] = max(lo, min(int(data[key]), hi))
            for key, lo, hi in (("trigger_interval_s", 0.5, 300.0), ("preview_interval_s", 1.0, 60.0)):
                if data.get(key):
                    kc[key] = max(lo, min(float(data[key]), hi))
            if not self.cfg["simulate"]:
                config_mod.save_section(self.cfg, "keyence", kc)
            else:
                self.cfg["keyence"] = kc
            self._stop_keyence_preview()
            self.keyence_state = self._check_keyence()
            return self.keyence_status()

    def reference_profile(self):
        slug = self.prefs.get("reference_profile")
        if not slug:
            return None
        try:
            return self.profiles.load(slug)
        except (KeyError, OSError, ValueError):
            return None

    def camera_details(self, cid):
        """Always read live from the camera: settings may have been changed in its own web page."""
        cam = self.cameras[cid]
        self.devices[cid] = self._check_clock(cam)
        sections = cam.read_sections(self.cfg["config_snapshot_paths"])
        ref = self.reference_profile()
        ref_sections = ((ref or {}).get("cameras") or {}).get(cid)
        info = camerainfo.build(self.cfg, cam, sections, ref_sections, self.devices[cid].get("drift_s"),
                                self.draft["metadata"].get("thermal_range"))
        if ref_sections is not None and info.get("reachable"):
            changes = isapi.diff_sections(ref_sections, sections, self.cfg["config_ignore_keys"],
                                          only=self.cfg["restorable_sections"])
            info["reference"] = {"name": ref["name"], "slug": self.prefs["reference_profile"],
                                 "changes": changes}
        info["read_at"] = iso(self.clock.now())
        self.camera_checks[cid] = {
            "reachable": info.get("reachable"),
            "resolutions": {s["kind"]: (s.get("width"), s.get("height")) for s in info.get("streams", [])},
            "warnings": [c for c in info.get("checks", []) if c["status"] == "warn"],
            "reference_changes": len((info.get("reference") or {}).get("changes") or []),
            "read_at": info["read_at"],
        }
        return info

    def check_cameras(self):
        if self.state in ACTIVE:
            return self.camera_checks
        for cid in list(self.cameras):
            try:
                self.camera_details(cid)
            except Exception as e:  # noqa
                self.camera_checks[cid] = {"reachable": False, "error": str(e)[:160], "warnings": []}
        return self.camera_checks

    # ------------------------------------------------------------------ #
    # Camera writes
    # ------------------------------------------------------------------ #
    def set_channel_name(self, cid, kind, name):
        """Rename the channel shown on the video. Writes the streaming channel (verified path)
        and, when present, the video input channel; then reads both back."""
        self._require_idle()
        name = (name or "").strip()
        if not name or len(name) > 32 or "<" in name or ">" in name:
            raise ValueError("invalid_name")
        cam = self.cameras[cid]
        scfg = self.cfg["streams"][kind]
        # On HM-TD3028T-2/Q firmware the name exists in three documents; the overlay one is what is drawn.
        targets = [("/ISAPI/Streaming/channels/%s" % scfg["rtsp_channel"], "channelName", None),
                   ("/ISAPI/System/Video/inputs/channels/%s" % scfg["input_channel"], "name", None),
                   ("/ISAPI/System/Video/inputs/channels/%s/overlays" % scfg["input_channel"], "name",
                    "channelNameOverlay")]
        results = []
        for path, tag, parent in targets:
            status, _, body = cam.get(path)
            text = body.decode("utf-8", "replace")
            current = _get_in(text, parent, tag)
            if status != 200 or current is None:
                continue
            st, _, resp = cam.request("PUT", path, _set_in(text, parent, tag, name).encode("utf-8"))
            ok, msg = isapi.response_status(resp.decode("utf-8", "replace"))
            _, _, back = cam.get(path)
            now = _get_in(back.decode("utf-8", "replace"), parent, tag)
            results.append({"path": path, "http": st, "ok": st == 200 and ok and now == name,
                            "message": msg, "value": now})
        if not results:
            raise ValueError("name_not_supported")
        self._preview_cache.clear()
        return {"results": results, "ok": all(r["ok"] for r in results)}

    def trigger_ffc(self, cid):
        self._require_idle()
        path = self.cfg.get("ffc_path")
        if not path:
            raise ValueError("ffc_not_configured")
        status, _, body = self.cameras[cid].request("PUT", path, b"")
        ok, msg = isapi.response_status(body.decode("utf-8", "replace"))
        return {"ok": status == 200 and ok, "http": status, "message": msg}

    def backup_stream(self, cid):
        self._require_idle()
        return self.cameras[cid].stream("/ISAPI/System/configurationData", timeout=60)

    # ------------------------------------------------------------------ #
    # Camera settings profiles
    # ------------------------------------------------------------------ #
    def list_profiles(self):
        out = []
        for p in self.profiles.all():
            out.append({"slug": p["slug"], "name": p["name"], "note": p.get("note", ""),
                        "created_at": p.get("created_at"), "cameras": sorted(p.get("cameras", {})),
                        "is_reference": p["slug"] == self.prefs.get("reference_profile")})
        return sorted(out, key=lambda p: p.get("created_at") or "", reverse=True)

    def save_profile(self, name, note="", make_reference=False):
        self._require_idle()
        name = (name or "").strip()[:80]
        if not name:
            raise ValueError("name_required")
        cams = {}
        for cid, cam in self.cameras.items():
            sections = cam.read_sections(self.cfg["config_snapshot_paths"])
            if not any(e.get("status") == 200 for e in sections.values()):
                raise StateError("camera_offline:%s" % cid)
            cams[cid] = {"ip": cam.ip, "sections": {
                k: {kk: vv for kk, vv in v.items() if kk in ("path", "status", "text", "flat")}
                for k, v in sections.items()}}
        slug = self.profiles.unique_slug(name)
        self.profiles.save(slug, {"name": name, "note": note, "created_at": iso(self.clock.now()),
                                  "cameras": {cid: c["sections"] for cid, c in cams.items()},
                                  "camera_ips": {cid: c["ip"] for cid, c in cams.items()}})
        if make_reference:
            self.set_prefs({"reference_profile": slug})
        return slug

    def delete_profile(self, slug):
        self.profiles.delete(slug)
        if self.prefs.get("reference_profile") == slug:
            self.set_prefs({"reference_profile": None})

    def profile_preview(self, slug):
        """What a restore would change, per camera and section, compared with live settings."""
        prof = self.profiles.load(slug)
        out = {}
        for cid, saved in prof.get("cameras", {}).items():
            if cid not in self.cameras:
                continue
            live = self.cameras[cid].read_sections(
                {k: v for k, v in self.cfg["config_snapshot_paths"].items() if k in self.cfg["restorable_sections"]})
            if not any(e.get("status", -1) > 0 for e in live.values()):
                out[cid] = {"reachable": False, "changes": []}
                continue
            out[cid] = {"reachable": True, "changes": isapi.diff_sections(
                saved, live, self.cfg["config_ignore_keys"], only=self.cfg["restorable_sections"])}
        return {"name": prof["name"], "cameras": out}

    def restore_profile(self, slug, camera_ids):
        self._require_idle()
        prof = self.profiles.load(slug)
        report = {}
        for cid in camera_ids:
            saved = prof.get("cameras", {}).get(cid)
            if saved is None or cid not in self.cameras:
                continue
            cam = self.cameras[cid]
            results = []
            for name in self.cfg["restorable_sections"]:
                sec = saved.get(name) or {}
                if sec.get("status") != 200 or not sec.get("text"):
                    continue
                path = sec["path"]
                try:
                    st, _, resp = cam.request("PUT", path, sec["text"].encode("utf-8"), timeout=8)
                    ok, msg = isapi.response_status(resp.decode("utf-8", "replace"))
                    results.append({"section": name, "http": st, "ok": st == 200 and ok, "message": msg})
                except Exception as e:  # noqa
                    results.append({"section": name, "http": -1, "ok": False, "message": str(e)[:120]})
            after = self.profile_preview(slug)["cameras"].get(cid, {})
            report[cid] = {"results": results, "remaining_changes": after.get("changes", [])}
        self._preview_cache.clear()
        self._check_due = 0
        return report

    # ------------------------------------------------------------------ #
    # Connection settings (camera addresses and passwords)
    # ------------------------------------------------------------------ #
    def connection_settings(self):
        return {"cameras": [{"id": c["id"], "ip": c["ip"], "user": c.get("user", ""),
                             "password_set": bool(c.get("password"))} for c in self.cfg["cameras"]],
                "config_file": self.cfg["_path"], "data_dir": self.cfg["data_dir"],
                "ffmpeg": self.ffmpeg_line, "simulate": self.cfg["simulate"]}

    def _merged_camera(self, entry):
        current = next((c for c in self.cfg["cameras"] if c["id"] == entry.get("id")), None)
        if current is None:
            raise KeyError(entry.get("id"))
        ip = (entry.get("ip") or "").strip()
        user = (entry.get("user") or "").strip()
        if not HOST_RE.match(ip):
            raise ValueError("invalid_address")
        if not user:
            raise ValueError("user_required")
        merged = dict(current, ip=ip, user=user)
        if entry.get("password"):
            merged["password"] = entry["password"]
        return merged

    def test_connection(self, entry):
        merged = self._merged_camera(entry)
        cam = (SimCamera if self.cfg["simulate"] else isapi.Camera)(merged)
        try:
            status, _, body = cam.get("/ISAPI/System/deviceInfo", timeout=4)
        except Exception as e:  # noqa
            return {"ok": False, "reason": "unreachable", "detail": type(e).__name__}
        if status == 401:
            return {"ok": False, "reason": "unauthorized"}
        if status != 200:
            return {"ok": False, "reason": "http", "detail": status}
        text = body.decode("utf-8", "replace")
        live = self.cameras.get(merged["id"])
        if live is not None and (live.ip, live.user, live.password) == (merged["ip"], merged["user"], merged["password"]):
            live.clear_auth_pause()          # credentials proven good: resume at once
            self._preview_cache.clear()
        return {"ok": True, "model": isapi.xml_get(text, "model"), "name": isapi.xml_get(text, "deviceName")}

    def update_connections(self, entries):
        with self.lock:
            self._require_idle()
            merged = [self._merged_camera(e) for e in entries]
            ids = [m["id"] for m in merged]
            cams = [next((m for m in merged if m["id"] == c["id"]), c) for c in self.cfg["cameras"]]
            if len(set(ids)) != len(ids):
                raise ValueError("duplicate_camera")
            if not self.cfg["simulate"]:
                config_mod.save_cameras(self.cfg, cams)
            else:
                self.cfg["cameras"] = cams
            self.cameras = self._build_cameras()
            self.devices = {}
            self.camera_checks = {}
            self._preview_cache.clear()
            self._check_due = 0
            return self.connection_settings()

    # ------------------------------------------------------------------ #
    # Draft: what the next run will be recorded with
    # ------------------------------------------------------------------ #
    def _default_draft(self):
        return {"metadata": {"thermal_range": self.cfg["default_thermal_range"]}, "regions": {},
                "cad": None, "options": {"stop_after_s": 0}, "part_preset": None}

    def _load_draft(self):
        base = self._default_draft()
        try:
            with open(self.draft_path, encoding="utf-8") as f:
                base.update(json.load(f))
        except (OSError, ValueError):
            pass
        return base

    def _save_draft(self):
        self.draft["updated_at"] = iso(self.clock.now())
        write_json(self.draft_path, self.draft)

    def set_metadata(self, data):
        with self.lock:
            self._require_idle()
            md = {k: (str(v).strip() if v is not None else "") for k, v in data.items() if k in METADATA_FIELDS}
            if md.get("thermal_range") not in self.cfg["thermal_ranges"]:
                md["thermal_range"] = self.cfg["default_thermal_range"]
            self.draft["metadata"] = md
            self._save_draft()
            return self.draft

    def set_options(self, data):
        with self.lock:
            self._require_idle()
            try:
                stop_after = max(0, min(int(float(data.get("stop_after_s") or 0)), self.cfg["max_record_seconds"]))
            except (TypeError, ValueError):
                raise ValueError("invalid_duration")
            self.draft["options"] = {"stop_after_s": stop_after}
            self._save_draft()
            return self.draft

    def stream_frame(self, cam_id, kind):
        """Resolution the camera really sends, falling back to the configured one."""
        live = ((self.camera_checks.get(cam_id) or {}).get("resolutions") or {}).get(kind)
        if live and live[0] and live[1]:
            return live
        return self.cfg["streams"][kind]["width"], self.cfg["streams"][kind]["height"]

    def _region_entry(self, cam_id, kind, r):
        if kind == "keyence":
            w, h = self.cfg["keyence"]["image_width"], self.cfg["keyence"]["image_height"]
        else:
            w, h = self.stream_frame(cam_id, kind)
        x0 = min(max(float(r["x"]), 0.0), 1.0)
        y0 = min(max(float(r["y"]), 0.0), 1.0)
        x1 = min(max(x0 + float(r["w"]), 0.0), 1.0)
        y1 = min(max(y0 + float(r["h"]), 0.0), 1.0)
        entry = {"id": str(r.get("id") or "r%d" % int(time.time() * 1000))[:40],
                 "name": (str(r.get("name") or "").strip() or "Region")[:40],
                 "normalized": {"x": round(x0, 5), "y": round(y0, 5), "w": round(x1 - x0, 5), "h": round(y1 - y0, 5)},
                 "px": {"x": int(round(x0 * w)), "y": int(round(y0 * h)), "w": int(round((x1 - x0) * w)),
                        "h": int(round((y1 - y0) * h)), "frame": [w, h]}}
        if kind == "thermal":
            sw, sh = self.cfg["radiometric"]["sensor_width"], self.cfg["radiometric"]["sensor_height"]
            entry["radiometric_px"] = {"x": int(x0 * sw), "y": int(y0 * sh), "w": int(round((x1 - x0) * sw)),
                                       "h": int(round((y1 - y0) * sh)), "frame": [sw, sh],
                                       "assumes": "thermal video shows the full sensor field without digital zoom"}
        return entry

    def set_regions(self, stream, regions):
        with self.lock:
            self._require_idle()
            streams = {n: (c["id"], k) for n, c, k in config_mod.stream_names(self.cfg)}
            if self.cfg["keyence"]["mode"] == "iv3":
                streams["keyence"] = ("keyence", "keyence")      # regions mark the fields to read later
            if stream not in streams:
                raise KeyError(stream)
            entries = [self._region_entry(streams[stream][0], streams[stream][1], r) for r in (regions or [])[:12]
                       if float(r.get("w", 0)) > 0.002 and float(r.get("h", 0)) > 0.002]
            if entries:
                self.draft["regions"][stream] = entries
            else:
                self.draft["regions"].pop(stream, None)
            self._save_draft()
            return self.draft

    def save_cad(self, filename, chunks):
        self._require_idle()
        tmp = self.draft_cad_path + ".tmp"
        size = 0
        with open(tmp, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
                size += len(chunk)
        with open(tmp, "rb") as f:
            magic = f.read(4)
        if magic != b"glTF":
            os.remove(tmp)
            raise ValueError("not_glb")
        os.replace(tmp, self.draft_cad_path)
        with self.lock:
            self.draft["cad"] = {"filename": os.path.basename(filename or "model.glb"), "size": size}
            self._save_draft()
        return self.draft

    def clear_cad(self):
        with self.lock:
            self._require_idle()
            self.draft["cad"] = None
            if os.path.isfile(self.draft_cad_path):
                os.remove(self.draft_cad_path)
            self._save_draft()
            return self.draft

    # ------------------------------------------------------------------ #
    # Part presets
    # ------------------------------------------------------------------ #
    def list_parts(self):
        return [{"slug": p["slug"], "name": p["name"], "mould_id": p["metadata"].get("mould_id"),
                 "part_number": p["metadata"].get("part_number"), "material": p["metadata"].get("material"),
                 "has_cad": bool(p.get("cad")), "regions": sum(len(v) for v in p.get("regions", {}).values()),
                 "saved_at": p.get("saved_at")} for p in self.parts.all()]

    def save_part(self, name):
        self._require_idle()
        name = (name or "").strip()[:80]
        if not name:
            raise ValueError("name_required")
        md = {k: self.draft["metadata"].get(k, "") for k in ("mould_id", "part_number", "material", "thermal_range")}
        existing = next((p for p in self.parts.all() if p["name"] == name), None)
        slug = existing["slug"] if existing else self.parts.unique_slug(name)
        obj = {"name": name, "metadata": md, "regions": self.draft.get("regions", {}),
               "cad": self.draft.get("cad"), "saved_at": iso(self.clock.now())}
        if obj["cad"] and os.path.isfile(self.draft_cad_path):
            self.parts.attach(slug, self.draft_cad_path)
        self.parts.save(slug, obj)
        with self.lock:
            self.draft["part_preset"] = slug
            self._save_draft()
        return slug

    def apply_part(self, slug):
        with self.lock:
            self._require_idle()
            p = self.parts.load(slug)
            md = dict(self.draft["metadata"])
            md.update({k: v for k, v in p["metadata"].items() if v})
            self.draft["metadata"] = md
            self.draft["regions"] = p.get("regions", {})
            cad_src = os.path.join(self.parts.folder, slug + ".glb")
            if p.get("cad") and os.path.isfile(cad_src):
                shutil.copyfile(cad_src, self.draft_cad_path)
                self.draft["cad"] = p["cad"]
            self.draft["part_preset"] = slug
            self._save_draft()
            return self.draft

    def delete_part(self, slug):
        self.parts.delete(slug)
        with self.lock:
            if self.draft.get("part_preset") == slug:
                self.draft["part_preset"] = None
                self._save_draft()

    # ------------------------------------------------------------------ #
    # Previews and thermal matrix (setup only)
    # ------------------------------------------------------------------ #
    def _stream(self, stream):
        streams = {n: (c, k) for n, c, k in config_mod.stream_names(self.cfg)}
        if stream not in streams:
            raise KeyError(stream)
        return streams[stream]

    def preview(self, stream):
        if self.state in ACTIVE:
            raise StateError("previews_paused")
        if stream == "keyence":
            return self.keyence_preview_image()
        cam_cfg, kind = self._stream(stream)
        with self._locks["preview:" + stream]:
            cached = self._preview_cache.get(stream)
            if cached and time.time() - cached[0] < self.cfg["preview"]["cache_s"]:
                return cached[1], cached[2]
            cam = self.cameras[cam_cfg["id"]]
            body, ctype = cam.picture(self.cfg["streams"][kind]["picture_channel"], self.cfg["preview"]["timeout_s"])
            self._preview_cache[stream] = (time.time(), body, ctype)
            return body, ctype

    def thermal_matrix(self, cid):
        if self.state in ACTIVE:
            raise StateError("previews_paused")
        cam = self.cameras[cid]
        with self._locks["matrix:" + cid]:
            cached = self._matrix_cache.get(cid)
            if cached and time.time() - cached[0] < 1.0:
                return cached[1]
            ctype, body = cam.p2p(self.cfg["radiometric"]["timeout_s"])
            w, h, data = isapi.extract_matrix(ctype, body, self.cfg["radiometric"]["sensor_width"],
                                              self.cfg["radiometric"]["sensor_height"])
            vals = struct.unpack("<%df" % (w * h), data)
            result = (w, h, data, min(vals), max(vals))
            self._matrix_cache[cid] = (time.time(), result)
            return result

    # ------------------------------------------------------------------ #
    # Session index, run numbers, forecast
    # ------------------------------------------------------------------ #
    def _refresh_index(self, force=False):
        if not force and time.time() - self._index_at < 5:
            return self._index
        seen = set()
        for sid in os.listdir(self.sessions_dir):
            d = os.path.join(self.sessions_dir, sid)
            mp = os.path.join(d, "metadata.json")
            try:
                mtime = os.path.getmtime(mp)
            except OSError:
                continue
            seen.add(sid)
            cached = self._index.get(sid)
            if cached and cached["_mtime"] == mtime:
                continue
            try:
                with open(mp, encoding="utf-8") as f:
                    md = json.load(f)
            except (OSError, ValueError):
                continue
            om = md.get("operator_metadata") or {}
            self._index[sid] = {
                "_mtime": mtime, "session_id": sid, "status": md.get("status"),
                "started_at": md.get("started_at"), "duration_s": md.get("duration_s"),
                "run_number": md.get("run_number"), "mould_id": om.get("mould_id"),
                "part_number": om.get("part_number"), "material": om.get("material"),
                "operator": om.get("operator"), "simulated": md.get("simulated", False),
                "verdict": (md.get("operator_verdict") or {}).get("verdict"),
                "notes": len(md.get("operator_notes_during_run") or []),
                "size_mb": round(_dir_size(d) / 1e6, 1), "folder": d}
        for sid in list(self._index):
            if sid not in seen:
                del self._index[sid]
        self._index_at = time.time()
        return self._index

    def next_run_number(self, mould_id):
        key = (mould_id or "").strip().lower()
        nums = [s["run_number"] or 0 for s in self._refresh_index().values()
                if (s.get("mould_id") or "").strip().lower() == key]
        return (max(nums) if nums else 0) + 1

    def forecast(self, free_bytes):
        rows = [s for s in self._refresh_index().values()
                if s["status"] == "complete" and s.get("duration_s") and not s.get("simulated")]
        rows = sorted(rows, key=lambda s: s.get("started_at") or "")[-20:]
        rate = (sum(s["size_mb"] for s in rows) * 1e6 / sum(s["duration_s"] for s in rows)) if rows else 3.6e6
        usable = max(free_bytes - self.cfg["abort_free_disk_gb"] * 1e9, 0)
        return {"bytes_per_s": round(rate), "hours_left": round(usable / rate / 3600, 1), "measured": bool(rows)}

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #
    def blockers_and_warnings(self):
        blockers, warnings = [], []
        md = self.draft.get("metadata", {})
        missing = [f for f in self.cfg["required_metadata"] if not md.get(f)]
        if missing:
            blockers.append({"code": "missing_fields", "fields": missing})
        for cid, cam in self.cameras.items():
            d = self.devices.get(cid)
            if d is None:
                blockers.append({"code": "camera_checking", "camera": cid})
            elif not d.get("reachable"):
                blockers.append({"code": "camera_auth" if d.get("auth") else "camera_offline",
                                 "camera": cid, "ip": cam.ip})
            elif d.get("drift_s") is not None and abs(d["drift_s"]) > self.cfg["clock_drift_warn_s"]:
                warnings.append({"code": "clock_drift", "camera": cid, "value": d["drift_s"]})
            cc = self.camera_checks.get(cid) or {}
            if cc.get("reference_changes"):
                warnings.append({"code": "settings_changed", "camera": cid, "count": cc["reference_changes"]})
            nwarn = len([w for w in cc.get("warnings", []) if not w["id"].endswith("_vs_reference")])
            if nwarn:
                warnings.append({"code": "settings_not_recommended", "camera": cid, "count": nwarn})
        if not self.prefs.get("reference_profile"):
            warnings.append({"code": "no_reference"})
        free = shutil.disk_usage(self.sessions_dir).free / 1e9
        if free < self.cfg["min_free_disk_gb"]:
            blockers.append({"code": "disk_low", "free": round(free, 1), "need": self.cfg["min_free_disk_gb"]})
        if self.ffmpeg_major < 0:
            blockers.append({"code": "ffmpeg_missing", "path": self.cfg["ffmpeg"]})
        ks = self.keyence_state or {}
        if ks.get("mode") == "iv3" and ks.get("reachable") is False:
            warnings.append({"code": "keyence_offline", "ip": ks.get("host")})
        if not self.draft.get("regions"):
            warnings.append({"code": "no_regions"})
        if not self.draft.get("cad"):
            warnings.append({"code": "no_cad"})
        return blockers, warnings

    def start(self):
        with self.lock:
            if self.state in ACTIVE:
                raise StateError("busy_recording")
            if self.state == "finished":
                self.recording = None
            blockers, _ = self.blockers_and_warnings()
            if blockers:
                raise StateError("blocked")
            self._preview_cache.clear()
            run = self.next_run_number(self.draft["metadata"].get("mould_id"))
            rec = Recording(self, json.loads(json.dumps(self.draft)), run)
            self.recording = rec
        try:
            rec.start()
        except Exception as e:  # noqa
            log.exception("start failed")
            rec.abort(str(e))
            raise StateError("start_failed:%s" % e)
        return rec.sid

    def stop(self, reason="operator"):
        with self.lock:
            if not self.recording or self.recording.state != "recording":
                raise StateError("not_recording")
            self.recording.stop(reason)

    def mark(self, note):
        with self.lock:
            if not self.recording or self.recording.state != "recording":
                raise StateError("not_recording")
            return self.recording.mark((note or "").strip()[:500] or "(mark)")

    def acknowledge(self):
        """Back to setup for the next run; applies the chosen automatic increments."""
        with self.lock:
            if self.state in ACTIVE:
                raise StateError("busy_recording")
            finished = self.recording
            self.recording = None
            md = self.draft.get("metadata", {})
            md["notes"] = ""
            if finished and finished.metadata and finished.metadata.get("status") in ("complete", "check"):
                for field in self.prefs.get("auto_increment", []):
                    md[field] = increment_trailing(md.get(field, ""))
            if "shot_counter_start" not in self.prefs.get("auto_increment", []):
                md["shot_counter_start"] = ""
            self._save_draft()
            self._index_at = 0
            return self.draft

    def set_verdict(self, sid, verdict, reason):
        if verdict not in ("usable", "discard", "unsure", ""):
            raise ValueError("invalid_verdict")
        if os.path.basename(sid) != sid:
            raise KeyError(sid)
        path = os.path.join(self.sessions_dir, sid, "metadata.json")
        with self.lock:
            with open(path, encoding="utf-8") as f:
                md = json.load(f)
            md["operator_verdict"] = None if not verdict else {
                "verdict": verdict, "reason": (reason or "").strip()[:500], "at": iso(self.clock.now())}
            write_json(path, md)
        self._index_at = 0
        return md["operator_verdict"]

    def shutdown(self):
        self._monitor_stop.set()
        self._stop_keyence_preview()
        rec = self.recording
        if rec and rec.state == "recording":
            rec.stop("server_shutdown")
        deadline = time.time() + 40
        while rec and rec.state in ACTIVE and time.time() < deadline:
            time.sleep(0.5)

    # ------------------------------------------------------------------ #
    # Status / sessions
    # ------------------------------------------------------------------ #
    def status(self):
        now = self.clock.now()
        rec = self.recording
        blockers, warnings = self.blockers_and_warnings()
        du = shutil.disk_usage(self.sessions_dir)
        devices = []
        for cid, cam in self.cameras.items():
            d = dict(self.devices.get(cid) or {"id": cid, "ip": cam.ip, "reachable": None})
            cc = self.camera_checks.get(cid) or {}
            d["warnings"] = len(cc.get("warnings", []))
            d["reference_changes"] = cc.get("reference_changes", 0)
            devices.append(d)
        ref = self.reference_profile()
        return {
            "state": self.state,
            "server_time": iso(now), "epoch": round(now, 3),
            "devices": devices,
            "disk": {"free_gb": round(du.free / 1e9, 1), "total_gb": round(du.total / 1e9, 1),
                     "forecast": self.forecast(du.free)},
            "blockers": blockers, "warnings": warnings,
            "next_run": self.next_run_number(self.draft["metadata"].get("mould_id")),
            "reference_profile": ref["name"] if ref else None,
            "keyence": self.keyence_status(),
            "prefs": self.prefs,
            "recording": rec.status() if rec else None,
            "result": rec.result if rec and rec.state == "finished" else None,
            "simulate": self.cfg["simulate"],
        }

    def list_sessions(self):
        rows = [{k: v for k, v in s.items() if not k.startswith("_")} for s in self._refresh_index(force=True).values()]
        return sorted(rows, key=lambda s: s.get("started_at") or s["session_id"], reverse=True)

    def session_detail(self, sid):
        if os.path.basename(sid) != sid:
            raise KeyError(sid)
        d = os.path.join(self.sessions_dir, sid)
        with open(os.path.join(d, "metadata.json"), encoding="utf-8") as f:
            md = json.load(f)
        ver = None
        vp = os.path.join(d, "verification.json")
        if os.path.isfile(vp):
            with open(vp, encoding="utf-8") as f:
                ver = json.load(f)
        return {"metadata": md, "verification": ver, "folder": d}


def _block(text, parent):
    m = re.search(r"<%s(?:\s[^>]*)?>.*?</%s>" % (parent, parent), text, re.S)
    return m


def _get_in(text, parent, tag):
    if not parent:
        return isapi.xml_get(text, tag)
    m = _block(text, parent)
    return isapi.xml_get(m.group(0), tag) if m else None


def _set_in(text, parent, tag, value):
    if not parent:
        return isapi.xml_set(text, tag, value)
    m = _block(text, parent)
    return text[:m.start()] + isapi.xml_set(m.group(0), tag, value) + text[m.end():]


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total

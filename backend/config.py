"""Configuration.

config.local.json (never committed) holds site-specific values, including
camera credentials. The dashboard's Settings page may rewrite the "cameras"
section of that file; a timestamped backup is kept next to it every time.
"""
import copy
import json
import os
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "Aid4SME Dashboard"
APP_VERSION = "1.0.0"

DEFAULTS = {
    "data_dir": "data",
    "host": "0.0.0.0",
    "port": 8000,
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    "simulate": False,
    "cameras": [
        {"id": "cam1", "ip": "192.168.1.30", "user": "admin", "password": "", "thermal_channel": "2"},
        {"id": "cam2", "ip": "192.168.1.50", "user": "admin", "password": "", "thermal_channel": "2"},
    ],
    "streams": {
        "optical": {"rtsp_channel": "101", "picture_channel": "101", "input_channel": "1",
                    "width": 2688, "height": 1520},
        "thermal": {"rtsp_channel": "201", "picture_channel": "201", "input_channel": "2",
                    "width": 1280, "height": 960},
    },
    "nominal_fps": 25.0,
    "segment_seconds": 60,
    "max_record_seconds": 1800,
    "rtsp_timeout_s": 5,
    "stop_grace_s": 12,
    "radiometric": {"enabled": True, "rate_hz": 1.0, "timeout_s": 5.0,
                    "sensor_width": 256, "sensor_height": 192},
    "thermal_ranges": {"low": {"label": "-20 \u2013 150 \u00b0C", "min_c": -20.0, "max_c": 150.0},
                       "high": {"label": "0 \u2013 550 \u00b0C", "min_c": 0.0, "max_c": 550.0}},
    "default_thermal_range": "low",
    "preview": {"interval_ms": 1000, "cache_s": 0.4, "timeout_s": 4.0, "thermal_matrix_ms": 2000},
    # mode: "off" | "iv3" (trigger over TCP, receive images over FTP) | "tcp" (text records)
    "keyence": {"mode": "off", "host": "192.168.1.40", "port": 8500, "delimiter": "\\r",
                "trigger_interval_s": 5.0, "ftp_port": 2121, "ftp_user": "ftpuser",
                "ftp_pass": "ftppass", "ftp_wait_s": 2.0, "stale_after_s": 0,
                "ftp_passive_ports": [2130, 2140]},
    "required_metadata": ["operator", "mould_id", "part_number", "material"],
    "min_free_disk_gb": 20.0,
    "abort_free_disk_gb": 2.0,
    "clock_drift_warn_s": 2.0,
    "device_poll_s": 5.0,
    # Recommended camera settings, used by the settings check.
    "recommended": {
        "codec": ["H.265", "H.264"],
        "bitrate_type": "CBR",
        "palette_contains": ["white"],
        "agc_contains": ["linear", "manual"],
    },
    # Endpoints read for the camera details view, profiles and the settings check.
    # Missing endpoints (HTTP 404) are harmless; they are shown as "not available".
    "config_snapshot_paths": {
        "deviceInfo": "/ISAPI/System/deviceInfo",
        "time": "/ISAPI/System/time",
        "ntpServers": "/ISAPI/System/time/ntpServers",
        "streamingOptical": "/ISAPI/Streaming/channels/101",
        "streamingThermal": "/ISAPI/Streaming/channels/201",
        "inputOptical": "/ISAPI/System/Video/inputs/channels/1",
        "inputThermal": "/ISAPI/System/Video/inputs/channels/2",
        "imageOptical": "/ISAPI/Image/channels/1",
        "imageThermal": "/ISAPI/Image/channels/2",
        "ffcThermal": "/ISAPI/Image/channels/2/FFC",
        "overlaysOptical": "/ISAPI/System/Video/inputs/channels/1/overlays",
        "overlaysThermal": "/ISAPI/System/Video/inputs/channels/2/overlays",
        "thermometryBasicParam": "/ISAPI/Thermal/channels/2/thermometry/basicParam",
        "thermometryRules": "/ISAPI/Thermal/channels/2/thermometry/1",
        "pixelToPixelParam": "/ISAPI/Thermal/channels/2/thermometry/pixelToPixelParam",
    },
    # Sections a camera profile may write back. Network, users and time are never restored.
    "restorable_sections": ["streamingOptical", "streamingThermal", "imageOptical", "imageThermal",
                            "ffcThermal", "overlaysOptical", "overlaysThermal", "thermometryBasicParam",
                            "pixelToPixelParam"],
    "config_ignore_keys": ["localTime", "currentTime", "upTime", "deviceUpTime"],
    # Optional: ISAPI path that triggers a manual shutter calibration (FFC). Hidden when empty.
    "ffc_path": "",
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def config_path(path=None):
    return path or os.environ.get("AID4SME_CONFIG") or os.path.join(ROOT, "config.local.json")


def load(path=None):
    path = config_path(path)
    if not os.path.isfile(path):
        raise SystemExit("Config not found: %s\nCopy config.example.json to config.local.json "
                         "and fill in the camera passwords." % path)
    with open(path, "r", encoding="utf-8") as f:
        user = json.load(f)
    cfg = _merge(DEFAULTS, user)
    if not os.path.isabs(cfg["data_dir"]):
        cfg["data_dir"] = os.path.join(ROOT, cfg["data_dir"])
    cfg["keyence"]["delimiter"] = cfg["keyence"]["delimiter"].encode("latin-1").decode("unicode_escape")
    cfg["_path"] = path
    return cfg


def save_cameras(cfg, cameras):
    """Write the cameras section back to config.local.json, keeping a backup."""
    path = cfg["_path"]
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    backup = "%s.%s.bak" % (path, time.strftime("%Y%m%d_%H%M%S"))
    shutil.copyfile(path, backup)
    raw["cameras"] = cameras
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)
    os.replace(tmp, path)
    cfg["cameras"] = cameras
    return backup


def stream_names(cfg):
    """[(stream_name, cam, kind)] in display order: cam1_optical, cam1_thermal, cam2_..."""
    return [("%s_%s" % (cam["id"], kind), cam, kind)
            for cam in cfg["cameras"] for kind in cfg["streams"]]


def public(cfg):
    """Config subset safe to send to the browser (no credentials)."""
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "cameras": [{"id": c["id"], "ip": c["ip"]} for c in cfg["cameras"]],
        "streams": [{"name": n, "camera": c["id"], "kind": k,
                     "width": cfg["streams"][k]["width"], "height": cfg["streams"][k]["height"]}
                    for n, c, k in stream_names(cfg)],
        "nominal_fps": cfg["nominal_fps"],
        "max_record_seconds": cfg["max_record_seconds"],
        "radiometric": {"enabled": cfg["radiometric"]["enabled"], "rate_hz": cfg["radiometric"]["rate_hz"],
                        "sensor_width": cfg["radiometric"]["sensor_width"],
                        "sensor_height": cfg["radiometric"]["sensor_height"]},
        "thermal_ranges": cfg["thermal_ranges"],
        "default_thermal_range": cfg["default_thermal_range"],
        "preview_interval_ms": cfg["preview"]["interval_ms"],
        "thermal_matrix_ms": cfg["preview"]["thermal_matrix_ms"],
        "required_metadata": cfg["required_metadata"],
        "keyence": {"mode": cfg["keyence"]["mode"], "host": cfg["keyence"]["host"],
                    "trigger_interval_s": cfg["keyence"]["trigger_interval_s"],
                    "ftp_port": cfg["keyence"]["ftp_port"]},
        "keyence_mode": cfg["keyence"]["mode"],
        "ffc_available": bool(cfg.get("ffc_path")),
        "simulate": cfg["simulate"],
    }

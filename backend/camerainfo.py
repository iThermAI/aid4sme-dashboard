"""Camera details and settings check, computed from live ISAPI reads.

Streaming-channel fields are exact (confirmed against the HM-TD3028T-2/Q).
Thermal image and measurement fields are located by name patterns, because
their element names vary between firmware versions; every value carries the
place it was read from, and the complete raw values are always available.
Check results are codes plus parameters; the dashboard translates them.
"""
import re

from .isapi import xml_get

# Exact element paths, confirmed on HM-TD3028T-2/Q firmware V5.5.336 and V5.5.342.
# DDE and bi-spectrum display mode are not exposed over ISAPI on this firmware;
# fusion is selected through the palette (Fusion1/Fusion2), so the palette check covers it.
THERMAL_FIELDS = [
    # key, sections searched, regex on the lower-cased flattened path
    ("palette", ("imageThermal",), r"^imagechannel/palettes/mode$"),
    ("agc", ("imageThermal",), r"^imagechannel/agc/agcmode$"),
    ("level_span", ("imageThermal",), r"^imagechannel/temprange/mode$"),
    ("noise_reduction", ("imageThermal",), r"^imagechannel/noisereduce/advancedmode/interframenoisereducelevel$"),
    ("digital_zoom", ("imageThermal",), r"^imagechannel/digitalzoom/zoomratio$"),
    ("ffc_mode", ("ffcThermal",), r"^ffc/mode$"),
    ("range", ("thermometryBasicParam",), r"^thermometrybasicparam/temperaturerange$"),
    ("emissivity", ("thermometryBasicParam",), r"^thermometrybasicparam/emissivity$"),
    ("distance", ("thermometryBasicParam",), r"^thermometrybasicparam/distance$"),
    ("p2p_emissivity", ("pixelToPixelParam",), r"^pixeltopixelparam/emissivity$"),
    ("p2p_distance", ("pixelToPixelParam",), r"^pixeltopixelparam/distance$"),
    ("p2p_refresh", ("thermometryBasicParam",), r"^thermometrybasicparam/refreshpixeltopixedataintervaltime$"),
    ("reflective", ("thermometryBasicParam",), r"^thermometrybasicparam/reflectiveenable$"),
    ("measurement_overlay", ("thermometryBasicParam",), r"^thermometrybasicparam/streamoverlay$"),
]


def _find(sections, names, pattern):
    rx = re.compile(pattern)
    for name in names:
        flat = (sections.get(name) or {}).get("flat") or {}
        for key, val in flat.items():
            if rx.search(key.lower()):
                return val, "%s: %s" % (name, key)
    return None, None


def parse_range(value):
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:-|~|to|_)\s*(\d+(?:\.\d+)?)", value or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def _bool(v):
    if v is None:
        return None
    return str(v).strip().lower() in ("true", "1", "on", "open", "enable", "enabled")


def stream_info(text):
    g = lambda tag: xml_get(text, tag)
    fps_raw = g("maxFrameRate")
    fps = None
    if fps_raw and fps_raw.isdigit():
        fps = int(fps_raw) / 100.0 if int(fps_raw) >= 100 else float(fps_raw)
    num = lambda v: int(v) if v and v.lstrip("-").isdigit() else None
    return {
        "name": g("channelName"),
        "codec": g("videoCodecType"),
        "width": num(g("videoResolutionWidth")),
        "height": num(g("videoResolutionHeight")),
        "fps": fps,
        "bitrate_type": g("videoQualityControlType"),
        "bitrate_kbps": num(g("constantBitRate")) if (g("videoQualityControlType") or "").upper() == "CBR"
        else num(g("vbrUpperCap")),
        "gop": num(g("GovLength")),
        "keyframe_interval_ms": num(g("keyFrameInterval")),
    }


def build(cfg, cam, sections, reference_flat=None, drift_s=None, selected_range=None):
    """cam: Camera. sections: output of Camera.read_sections. reference_flat: {section: {flat}}."""
    s = lambda n: sections.get(n) or {}
    text = lambda n: s(n).get("text", "") if s(n).get("status") == 200 else ""
    reachable = any(e.get("status", -1) > 0 for e in sections.values())
    info = {"camera": cam.id, "ip": cam.ip, "reachable": reachable}
    if not reachable:
        errors = sorted(set(e.get("error", "") for e in sections.values()))
        info["error"] = ", ".join(e for e in errors if e) or "no response"
        return info

    dev = text("deviceInfo")
    info["identity"] = {k: xml_get(dev, k) for k in ("deviceName", "model", "serialNumber", "macAddress",
                                                      "firmwareVersion", "firmwareReleasedDate")}
    ntp = text("ntpServers")
    info["time"] = {"mode": xml_get(text("time"), "timeMode"),
                    "ntp_server": xml_get(ntp, "ipAddress") or xml_get(ntp, "hostName"),
                    "ntp_interval_min": xml_get(ntp, "synchronizeInterval"),
                    "drift_s": drift_s}

    checks = []
    streams = []
    for kind, section, over in (("optical", "streamingOptical", "overlaysOptical"),
                                ("thermal", "streamingThermal", "overlaysThermal")):
        st = {"kind": kind, "available": s(section).get("status") == 200}
        if st["available"]:
            st.update(stream_info(text(section)))
            exp_w, exp_h = cfg["streams"][kind]["width"], cfg["streams"][kind]["height"]
            fps = cfg["nominal_fps"]
            codecs = cfg["recommended"]["codec"]
            add = lambda cid, ok, **p: checks.append(dict(id=cid, status="ok" if ok else "warn", stream=kind, **p))
            add("resolution", (st["width"], st["height"]) == (exp_w, exp_h),
                value="%sx%s" % (st["width"], st["height"]), expected="%sx%s" % (exp_w, exp_h))
            add("fps", st["fps"] is not None and abs(st["fps"] - fps) < 0.01, value=st["fps"], expected=fps)
            add("gop", st["gop"] is not None and abs(st["gop"] - fps) < 0.5, value=st["gop"], expected=int(fps))
            add("bitrate_type", (st["bitrate_type"] or "").upper() == cfg["recommended"]["bitrate_type"],
                value=st["bitrate_type"], expected=cfg["recommended"]["bitrate_type"])
            add("codec", st["codec"] == codecs[0], value=st["codec"], expected=codecs[0])
        ov = text(over)
        st["overlay"] = {
            "channel_name": _bool(_first_under(ov, "channelNameOverlay", "enabled")),
            "date_time": _bool(_first_under(ov, "DateTimeOverlay", "enabled")),
            "time_shown": _bool(_first_under(ov, "DateTimeOverlay", "displayTime")),
        }
        if ov:
            shown = st["overlay"]["date_time"] and st["overlay"]["time_shown"] is not False
            checks.append({"id": "osd_time", "status": "ok" if shown else "warn", "stream": kind})
        inp = text("inputOptical" if kind == "optical" else "inputThermal")
        st["input_name"] = xml_get(inp, "name") if inp else None
        streams.append(st)
    info["streams"] = streams

    # Time
    tmode = (info["time"]["mode"] or "").upper()
    checks.append({"id": "ntp", "status": "ok" if tmode == "NTP" else ("warn" if tmode else "unknown"),
                   "value": info["time"]["mode"]})
    if drift_s is not None:
        checks.append({"id": "clock", "status": "ok" if abs(drift_s) <= cfg["clock_drift_warn_s"] else "warn",
                       "value": drift_s})

    # Thermal image and measurement
    thermal = []
    values = {}
    for key, names, pattern in THERMAL_FIELDS:
        val, src = _find(sections, names, pattern)
        values[key] = val
        entry = {"key": key, "value": val, "source": src}
        if key in ("distance", "p2p_distance") and val is not None:
            sec = "thermometryBasicParam" if key == "distance" else "pixelToPixelParam"
            entry["unit"], _ = _find(sections, (sec,), r"/distanceunit$")
        if key == "level_span" and val is not None:
            lo, _ = _find(sections, ("imageThermal",), r"^imagechannel/temprange/temperaturelowerlimit$")
            hi, _ = _find(sections, ("imageThermal",), r"^imagechannel/temprange/temperatureupperlimit$")
            if lo is not None and hi is not None:
                entry["detail"] = "%s \u2013 %s \u00b0C" % (lo, hi)
        thermal.append(entry)
    info["thermal"] = thermal

    rec = cfg["recommended"]

    def contains_check(cid, key, words):
        v = values.get(key)
        if v is None:
            checks.append({"id": cid, "status": "unknown"})
        else:
            checks.append({"id": cid, "status": "ok" if any(w in v.lower() for w in words) else "warn", "value": v})

    contains_check("palette", "palette", rec["palette_contains"])
    contains_check("agc", "agc", rec["agc_contains"])
    def equals_check(cid, key, expected):
        v = values.get(key)
        checks.append({"id": cid, "status": "unknown" if v is None else
                       ("ok" if v.strip().lower() == expected else "warn"), "value": v, "expected": expected})

    equals_check("level_span", "level_span", "manual")
    equals_check("noise_reduction", "noise_reduction", "0")
    equals_check("digital_zoom", "digital_zoom", "1x")
    equals_check("p2p_refresh", "p2p_refresh", "1")

    # The radiometric matrix uses the pixel-to-pixel parameters; they must match the measurement settings.
    def num_or_none(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    for a, b in (("emissivity", "p2p_emissivity"), ("distance", "p2p_distance")):
        va, vb = num_or_none(values.get(a)), num_or_none(values.get(b))
        if va is not None and vb is not None:
            checks.append({"id": "p2p_mismatch", "status": "ok" if abs(va - vb) < 1e-6 else "warn",
                           "value": values.get(b), "expected": values.get(a), "field": a})

    rules = (sections.get("thermometryRules") or {}).get("flat") or {}
    if rules:
        active = sum(1 for k, v in rules.items()
                     if re.search(r"thermometryregion(\[\d+\])?/enabled$", k.lower()) and _bool(v))
        checks.append({"id": "rules_enabled", "status": "ok" if active == 0 else "warn", "value": active})
    ovl = values.get("measurement_overlay")
    if ovl is not None:
        checks.append({"id": "measurement_overlay", "status": "warn" if _bool(ovl) else "ok", "value": ovl})
    rng = parse_range(values.get("range"))
    if rng and selected_range:
        want = cfg["thermal_ranges"].get(selected_range, {})
        checks.append({"id": "range", "status": "ok" if abs(rng[1] - want.get("max_c", rng[1])) < 1 else "warn",
                       "value": values.get("range"), "expected": want.get("label")})

    # Measurement parameters that must not change silently between runs.
    if reference_flat:
        for key in ("emissivity", "distance"):
            cur = values.get(key)
            src = next((t["source"] for t in thermal if t["key"] == key), None)
            if cur is None or not src:
                continue
            section, path = src.split(": ", 1)
            old = ((reference_flat.get(section) or {}).get("flat") or {}).get(path)
            if old is not None:
                checks.append({"id": key + "_vs_reference", "status": "ok" if old == cur else "warn",
                               "value": cur, "expected": old})

    info["checks"] = checks
    info["sections"] = [{"name": n, "path": e.get("path"), "status": e.get("status"),
                         "values": sorted((e.get("flat") or {}).items())}
                        for n, e in sections.items()]
    return info


def _first_under(text, parent, tag):
    m = re.search(r"<%s(?:\s[^>]*)?>(.*?)</%s>" % (parent, parent), text or "", re.S)
    return xml_get(m.group(1), tag) if m else None

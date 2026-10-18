#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aid4SME - incremental dataset builder.

Point it at the data folder (the folder that holds the run folders) and it brings
everything up to date:

    python tools\\build_dataset.py D:\\aid4sme_data
    python tools\\build_dataset.py D:\\aid4sme_data --dry-run        what would be rebuilt
    python tools\\build_dataset.py D:\\aid4sme_data --only run014     one run, then the tables
    python tools\\build_dataset.py D:\\aid4sme_data --no-video-crops  skip the slow part

Per run it writes <run>/derived/ (raw/ is never touched):
    frames/<stream>_frames.csv     every frame: index, timestamp in file, host time
    frames/<stream>_motion.csv     per-frame motion signal (used for alignment)
    crops/<stream>__<region>.mp4   each operator region cut out of the video (H.264, frame-for-frame)
    radiometric_<cam>.npy          float32 [n, 192, 256] in deg C, full sensor
    radiometric_<cam>.csv          capture time and uncertainty of every matrix
    crops/radiometric_<cam>__<region>.npy   the region cut out of every matrix
    keyence.csv                    one row per IV3 picture with its host time
    sync.json                      offset of each stream against cam1_optical
    telemetry.jsonl                events, notes, matrices, pictures in time order
    summary.json                   what was produced
    build_state.json               fingerprints used to decide what to rebuild

Across all runs it writes <data>/dataset/:
    runs.csv          one row per run: labels (regrind %, shot, out of material), verdict,
                      timing, counts, and the machine values of the cycle that run saw
    cycles.csv        one row per machine cycle from the MC6 export, on the PC clock
    run_cycles.csv    every run x cycle overlap with frame and matrix index ranges
    regions.csv       every region of every run, with its crop files
    machine_columns.csv, machine_setpoints.csv, dataset.json, README.md

Change detection: a run is rebuilt only when its raw files, its regions or the
builder settings changed; file dates are ignored, so copying the data to another PC
does not trigger a rebuild. The dataset tables are rebuilt whenever any run, any
machine export or dataset_config.json changed.

Requirements: Python 3.8+, numpy, FFmpeg + ffprobe (4.x or newer). Nothing else.
"""
from __future__ import print_function

import argparse
import csv
import datetime
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

try:
    import numpy as np
except ImportError:
    sys.exit("This tool needs numpy:  pip install numpy")

BUILDER_VERSION = "2.1.0"
STATE_VERSION = "2"     # per-run state format; change only when every run must be rebuilt
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOTION_W, MOTION_H = 128, 72
MAX_SHIFT_S = 2.0
GRID_MS = 5.0
REFERENCE = "cam1_optical"
STREAMS = ("cam1_optical", "cam1_thermal", "cam2_optical", "cam2_thermal")
SETTLE_S = 120          # a run whose files changed in the last 2 minutes may still be recording

DEFAULT_CONFIG = {
    "_help": ("Settings for tools/build_dataset.py. Edit and re-run the builder; only what "
              "depends on a changed setting is rebuilt."),
    "machine_clock_offsets": [
        {"date": "2026-10-07", "offset_s": 499.5, "uncertainty_s": 1.0,
         "note": ("PC time minus MC6 machine clock. Read from the machine's on-screen clock in "
                  "Keyence pictures of runs 014, 047, 111 and 134 (bounds intersect at "
                  "499.43-499.50 s); the export itself has 1 s resolution.")}
    ],
    "_machine_clock_help": ("The MC6 clock is not synchronised with the PC. Add one entry per "
                            "recording day: open any Keyence picture of that day, read the "
                            "machine clock (top left of the screen) and subtract it from the "
                            "picture's PC time in raw/keyence/index.csv. Days without an entry "
                            "fall back to default_machine_clock_offset_s, if set."),
    "default_machine_clock_offset_s": None,
    "mould_open_lead_s": 3.56,
    "mould_open_lead_tolerance_s": 1.5,
    "clock_auto_search_s": 20,
    "_clock_check_help": ("The builder checks each day's offset against the videos: the mould opens "
                          "mould_open_lead_s before the next machine cycle starts (3.56 s measured on "
                          "2026-10-07 for mould 1834; re-measure for a different mould). Days without a "
                          "configured offset are estimated from the videos within clock_auto_search_s of the "
                          "nearest configured day, or by a wide search when none is configured."),
    "batch_gap_s": 120,
    "video_crops": True,
    "video_crop_crf": 18,
    "video_crop_preset": "veryfast",
    "label_overrides": {},
    "_label_overrides_help": ('Correct labels per run, e.g. {"run014": {"regrind_pct": 10}}. '
                              "Keys: regrind_pct, shot_in_batch, out_of_material, exclude, note."),
}


# =========================================================================== #
# Small helpers
# =========================================================================== #
def log(msg=""):
    print(msg)
    sys.stdout.flush()


def run(cmd, **kw):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, **kw)


def read_json(path, default=None):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, IOError, ValueError):
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False))
    os.replace(tmp, path)


def write_csv(path, fields, rows):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def read_csv(path):
    try:
        with io.open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, IOError):
        return []


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha1_obj(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


def fnum(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# Local time zone of the capture PC per recording day ('YYYY-MM-DD' -> seconds east of UTC),
# taken from the runs' own started_at stamps, so results do not depend on the time zone
# setting of the PC that runs this tool.
TZ = {}


def tz_default():
    if TZ:
        vals = list(TZ.values())
        return max(set(vals), key=vals.count)
    return -(time.altzone if time.localtime().tm_isdst else time.timezone)


def learn_tz(started_at):
    m = re.match(r"(\d{4}-\d\d-\d\d)T.*([+-])(\d\d):(\d\d)$", started_at or "")
    if m:
        TZ[m.group(1)] = (1 if m.group(2) == "+" else -1) * (int(m.group(3)) * 3600 + int(m.group(4)) * 60)


def local_to_epoch(naive):
    off = TZ.get(naive.strftime("%Y-%m-%d"), tz_default())
    return (naive - datetime.datetime(1970, 1, 1)).total_seconds() - off


def iso(t):
    if t is None or t == "":
        return ""
    off = tz_default()
    day = (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=t + off)).strftime("%Y-%m-%d")
    off = TZ.get(day, off)
    d = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=t + off)
    sign = "+" if off >= 0 else "-"
    return d.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "%s%02d:%02d" % (sign, abs(off) // 3600, abs(off) % 3600 // 60)


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "").strip()).strip("_") or "region"


def run_short(session_id):
    m = re.search(r"(run\d+)$", session_id or "")
    return m.group(1) if m else session_id


# =========================================================================== #
# Radiometric payload parsing (same logic as backend/isapi.py, kept here so the
# tool has no dependency on the dashboard's packages)
# =========================================================================== #
def _parse_headers(raw):
    headers = {}
    for line in raw.decode("latin-1").split("\r\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def _parse_multipart(body, boundary):
    delim = b"--" + boundary
    parts = []
    pos = body.find(delim)
    while pos >= 0:
        pos += len(delim)
        if body[pos:pos + 2] == b"--":
            break
        hdr_end = body.find(b"\r\n\r\n", pos)
        if hdr_end < 0:
            break
        headers = _parse_headers(body[pos:hdr_end])
        start = hdr_end + 4
        clen = headers.get("content-length", "")
        if clen.isdigit() and int(clen) > 0:
            end = start + int(clen)
            data = body[start:end]
            pos = body.find(delim, end)
        else:
            nxt = body.find(delim, start)
            end = nxt if nxt >= 0 else len(body)
            data = body[start:end]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            pos = nxt
        parts.append((headers, data))
    return parts


def extract_matrix(body, sensor_w, sensor_h):
    meta, p2p = None, None
    for headers, data in _parse_multipart(body, b"boundary"):
        ctype = headers.get("content-type", "").lower()
        if meta is None and ("json" in ctype or data.lstrip()[:1] == b"{"):
            try:
                meta = json.loads(data.decode("utf-8", "replace"))
                continue
            except ValueError:
                pass
        if "octet-stream" in ctype:
            p2p = data
    info = (meta or {}).get("JpegPictureWithAppendData", meta or {})
    if p2p is None:
        raise ValueError("no temperature data in the camera response")
    tdl = int(info.get("temperatureDataLength") or 0)
    declared = int(info.get("p2pDataLen") or 0)
    if declared and len(p2p) > declared:
        p2p = p2p[:declared]
    if tdl != 4:
        raise ValueError("temperature data is not float32 (temperatureDataLength=%s)" % tdl)
    n = len(p2p) // 4
    w, h = int(info.get("jpegPicWidth") or 0), int(info.get("jpegPicHeight") or 0)
    if not (w and h and w * h == n):
        w, h = sensor_w, sensor_h
    if w * h != n:
        raise ValueError("unexpected matrix size (%d values)" % n)
    return np.frombuffer(p2p[:n * 4], dtype="<f4").reshape(h, w)


# =========================================================================== #
# FFmpeg
# =========================================================================== #
class FF(object):
    def __init__(self, ffmpeg, ffprobe):
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        for exe in (ffmpeg, ffprobe):
            try:
                run([exe, "-version"])
            except (OSError, subprocess.CalledProcessError):
                sys.exit("Not found: %s  (use --ffmpeg / --ffprobe, or set them in config.local.json)" % exe)
        self.version = run([ffmpeg, "-version"]).decode("utf-8", "replace").splitlines()[0]
        help_text = run([ffmpeg, "-hide_banner", "-h", "full"]).decode("utf-8", "replace")
        self.fps_mode = "-fps_mode" in help_text
        enc = run([ffmpeg, "-hide_banner", "-encoders"]).decode("utf-8", "replace")
        self.has_x264 = " libx264 " in enc

    def passthrough(self):
        return ["-fps_mode", "passthrough"] if self.fps_mode else ["-vsync", "passthrough"]


def concat_segments(ff, raw_dir, name, out_path):
    segs = sorted(glob.glob(os.path.join(raw_dir, name + "_[0-9][0-9][0-9].mkv")))
    if not segs:
        return None, 0
    listing = out_path + ".txt"
    with io.open(listing, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(u"file '%s'\n" % os.path.abspath(s).replace("\\", "/").replace("'", "'\\''"))
    try:
        run([ff.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "concat",
             "-safe", "0", "-i", listing, "-c", "copy", "-fflags", "+genpts", out_path])
    finally:
        os.remove(listing)
    return out_path, len(segs)


def frame_times(ff, path):
    """Timestamp of every frame in the file, in seconds, in order."""
    out = run([ff.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "packet=pts_time,dts_time", "-of", "csv=p=0", path]).decode("utf-8", "replace")
    times = []
    for line in out.splitlines():
        for p in line.strip().split(","):
            if p not in ("", "N/A"):
                times.append(float(p))
                break
    # These cameras occasionally send a packet with no timestamp and FFmpeg repeats the
    # previous one. Spread repeats over one frame interval so frame times stay strictly
    # increasing, and report how many were repaired.
    repaired = 0
    diffs = [b - a for a, b in zip(times, times[1:]) if b > a]
    step = sorted(diffs)[len(diffs) // 2] if diffs else 1.0 / 25.0
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            times[i] = times[i - 1] + step
            repaired += 1
    return times, repaired


def count_frames(ff, path):
    try:
        out = run([ff.ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
                   "-show_entries", "stream=nb_read_packets,width,height", "-of", "json", path])
        s = json.loads(out.decode("utf-8", "replace"))["streams"][0]
        return int(s["nb_read_packets"]), int(s["width"]), int(s["height"])
    except Exception:                                                   # noqa
        return None, None, None


def even_crop(px, frame_w, frame_h):
    """Clamp a region to the frame and make width/height even (H.264 4:2:0 needs it)."""
    x = max(0, min(int(px["x"]), frame_w - 2))
    y = max(0, min(int(px["y"]), frame_h - 2))
    w = max(2, min(int(px["w"]), frame_w - x))
    h = max(2, min(int(px["h"]), frame_h - y))
    return x, y, w - (w % 2), h - (h % 2)


def decode_pass(ff, path, crops, log_path, motion=True, crf=18, preset="veryfast"):
    """One decode of the video produces the motion signal and every region crop.

    crops: list of (out_path, (x, y, w, h)). Returns numpy motion array (or None).
    Frames are passed through one-for-one (no duplication, no dropping), so frame i of
    every crop is frame i of <stream>_frames.csv.
    """
    if not motion and not crops:
        return None
    labels = (["[m0]"] if motion else []) + ["[c%d]" % i for i in range(len(crops))]
    parts = []
    if len(labels) > 1:
        parts.append("[0:v]split=%d%s" % (len(labels), "".join(labels)))
        src = dict((l, l) for l in labels)
    else:
        src = {labels[0]: "[0:v]"}
    if motion:
        parts.append("%sscale=%d:%d,format=gray[m]" % (src["[m0]"], MOTION_W, MOTION_H))
    for i, (_, (x, y, w, h)) in enumerate(crops):
        parts.append("%scrop=%d:%d:%d:%d[o%d]" % (src["[c%d]" % i], w, h, x, y, i))
    cmd = [ff.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", path,
           "-filter_complex", ";".join(parts)]
    if motion:
        cmd += ["-map", "[m]"] + ff.passthrough() + ["-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
    for i, (out, _) in enumerate(crops):
        if ff.has_x264:
            codec = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
        else:
            codec = ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj420p"]
        cmd += ["-map", "[o%d]" % i] + ff.passthrough() + codec + ["-an", out + ".part.mp4"]
    with open(log_path, "wb") as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE if motion else subprocess.DEVNULL,
                                stderr=errf)
        out = []
        if motion:
            size = MOTION_W * MOTION_H
            prev = None
            while True:
                buf = proc.stdout.read(size)
                if len(buf) < size:
                    break
                cur = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
                out.append(0.0 if prev is None else float(np.abs(cur - prev).mean()))
                prev = cur
                if len(out) % 250 == 0:
                    heartbeat()
            proc.stdout.close()
        code = proc.wait()
    if code != 0:
        with io.open(log_path, encoding="utf-8", errors="replace") as f:
            raise RuntimeError("ffmpeg failed on %s: %s" % (os.path.basename(path), f.read()[-400:]))
    for out_path, _ in crops:
        os.replace(out_path + ".part.mp4", out_path)
    return np.array(out, dtype=np.float32) if motion else None


# =========================================================================== #
# Timing anchors and alignment
# =========================================================================== #
def progress_anchor(raw_dir, name):
    """Host time at which each stream's timestamp zero occurred (lower envelope of
    host_time - out_time over FFmpeg's progress reports)."""
    offs = []
    for row in read_csv(os.path.join(raw_dir, name + "_progress.csv")):
        try:
            if row.get("frame") and row.get("out_time_us"):
                offs.append(float(row["host_time"]) - int(row["out_time_us"]) / 1e6)
        except (ValueError, KeyError):
            pass
    if not offs:
        return None
    offs.sort()
    return {"anchor_host_time": offs[0], "samples": len(offs),
            "spread_p05_ms": round((offs[len(offs) // 20] - offs[0]) * 1000, 1)}


def normalise(x):
    x = x - x.mean()
    s = x.std()
    return x / s if s > 1e-9 else x


def cross_correlate(ref, sig, dt_s):
    a, b = normalise(ref), normalise(sig)
    n = int(round(MAX_SHIFT_S / dt_s))
    full = np.correlate(a, b, "full") / len(a)
    centre = len(b) - 1
    lo, hi = max(centre - n, 0), min(centre + n + 1, len(full))
    window = full[lo:hi]
    k = int(np.argmax(window))
    peak = float(window[k])
    shift = k + lo - centre
    if 0 < k < len(window) - 1:
        y0, y1, y2 = window[k - 1], window[k], window[k + 1]
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-12:
            shift += 0.5 * (y0 - y2) / denom
    return -shift * dt_s, peak


def align_streams(signals, reference, arrival):
    """Correlation only between optical and thermal of the SAME camera (shared view);
    between cameras the offset is the arrival-time estimate (they look at different things)."""
    have = dict((k, v) for k, v in signals.items() if v is not None and len(v[0]) > 10)
    dt = GRID_MS / 1000.0
    out = {}

    def cam_of(name):
        return name.split("_")[0]

    def measure(a, b):
        t0 = max(have[a][0][0], have[b][0][0])
        t1 = min(have[a][0][-1], have[b][0][-1])
        if t1 - t0 < 5:
            return None
        grid = np.arange(t0, t1, dt)
        off, q = cross_correlate(np.interp(grid, *have[a]), np.interp(grid, *have[b]), dt)
        return round(off * 1000, 1), round(q, 3)

    ref_cam = cam_of(reference)
    for name in sorted(set(list(have) + list(arrival))):
        cam = cam_of(name)
        est = arrival.get(name)
        if name == reference:
            out[name] = {"offset_ms": 0.0, "method": "reference", "trust": "reference"}
            continue
        own_optical = "%s_optical" % cam
        if name in have and own_optical in have and name != own_optical:
            m = measure(own_optical, name)
            if m and cam == ref_cam:
                out[name] = {"offset_ms": m[0], "correlation": m[1], "method": "scene cross-correlation",
                             "arrival_estimate_ms": est,
                             "trust": "low" if m[1] < 0.3 else "medium" if m[1] < 0.6 else "high"}
                continue
            base = arrival.get(own_optical)
            if m and base is not None:
                out[name] = {"offset_ms": round(base + m[0], 1), "correlation": m[1],
                             "method": "cross-correlation within %s, carried across on arrival times" % cam,
                             "arrival_estimate_ms": est, "trust": "low"}
                continue
        out[name] = {"offset_ms": est, "method": "arrival estimate (no shared view to measure against)",
                     "arrival_estimate_ms": est, "trust": "low"}
    return out


# =========================================================================== #
# Per-run fingerprints
# =========================================================================== #
def files_sig(paths):
    """Names and sizes only: raw files never change after recording, and file dates
    change when data is copied between PCs."""
    return sorted([os.path.basename(p), os.path.getsize(p)] for p in paths if os.path.isfile(p))


def run_fingerprints(session, md, cfg):
    raw = os.path.join(session, "raw")
    regions = md.get("regions") or {}
    fp = {}
    for name in STREAMS:
        segs = glob.glob(os.path.join(raw, name + "_[0-9][0-9][0-9].mkv"))
        prog = os.path.join(raw, name + "_progress.csv")
        crop_cfg = {"on": bool(cfg.get("video_crops")), "crf": cfg.get("video_crop_crf"),
                    "preset": cfg.get("video_crop_preset"), "regions": regions.get(name) or []}
        fp["video:" + name] = sha1_obj({"segs": files_sig(segs),
                                        "progress": sha1_file(prog) if os.path.isfile(prog) else None,
                                        "crops": crop_cfg if crop_cfg["on"] else None,
                                        "motion": cfg.get("_motion", True), "v": "2.0"})
    for cam in ("cam1", "cam2"):
        idx = os.path.join(raw, "radiometric_%s" % cam, "index.csv")
        fp["rad:" + cam] = sha1_obj({"index": sha1_file(idx) if os.path.isfile(idx) else None,
                                     "regions": [r.get("radiometric_px") for k, rs in regions.items()
                                                 if k.startswith(cam + "_thermal") for r in rs],
                                     "v": "2.0"})
    kidx = os.path.join(raw, "keyence", "index.csv")
    fp["keyence"] = sha1_obj({"index": sha1_file(kidx) if os.path.isfile(kidx) else None, "v": "2.0"})
    return fp


def missing_parts(session, md):
    """What a finished run should contain but does not (e.g. an interrupted copy)."""
    raw = os.path.join(session, "raw")
    miss = []
    for name in sorted((md.get("streams") or {})):
        if not glob.glob(os.path.join(raw, name + "_[0-9][0-9][0-9].mkv")):
            miss.append(name + " video")
        elif not os.path.isfile(os.path.join(raw, name + "_progress.csv")):
            miss.append(name + " timing")
    cams = sorted(set(v.get("camera") for v in (md.get("streams") or {}).values() if v.get("camera")))
    if md.get("radiometric") is not None or not md:
        for cam in cams:
            if not os.path.isfile(os.path.join(raw, "radiometric_%s" % cam, "index.csv")):
                miss.append(cam + " radiometric")
    if (md.get("keyence") or {}).get("mode") not in (None, "off") and \
            not os.path.isfile(os.path.join(raw, "keyence", "index.csv")):
        miss.append("keyence")
    if not os.path.isfile(os.path.join(session, "verification.json")):
        miss.append("verification.json")
    return miss


def newest_mtime(session):
    newest = 0
    for root, _, files in os.walk(os.path.join(session, "raw")):
        for f in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, f)))
            except OSError:
                pass
    return newest


# =========================================================================== #
# Per-run build
# =========================================================================== #
def build_video(ff, session, md, name, out, cfg):
    raw = os.path.join(session, "raw")
    fdir = os.path.join(out, "frames")
    cdir = os.path.join(out, "crops")
    ldir = os.path.join(out, "logs")
    for d in (fdir, cdir, ldir):
        if not os.path.isdir(d):
            os.makedirs(d)
    joined = os.path.join(out, name + ".joined.mkv")
    joined, nseg = concat_segments(ff, raw, name, joined)
    if not joined:
        return None
    try:
        anchor = progress_anchor(raw, name)
        pts, repaired = frame_times(ff, joined)
        host = [anchor["anchor_host_time"] + p for p in pts] if anchor else []
        write_csv(os.path.join(fdir, name + "_frames.csv"), ["frame", "pts_s", "host_time"],
                  [{"frame": i, "pts_s": "%.6f" % p, "host_time": "%.6f" % host[i] if host else ""}
                   for i, p in enumerate(pts)])

        stream = (md.get("streams") or {}).get(name) or {}
        fw, fh = int(stream.get("width") or 0), int(stream.get("height") or 0)
        crops, crop_info = [], []
        for old in glob.glob(os.path.join(cdir, name + "__*.mp4")):
            os.remove(old)
        if cfg.get("video_crops"):
            used = set()
            for r in (md.get("regions") or {}).get(name) or []:
                px = r.get("px") or {}
                frame = px.get("frame") or [fw, fh]
                x, y, w, h = even_crop(px, int(frame[0]), int(frame[1]))
                rn = safe_name(r.get("name") or r.get("id"))
                if rn in used:
                    rn = rn + "_" + safe_name(r.get("id"))
                used.add(rn)
                path = os.path.join(cdir, "%s__%s.mp4" % (name, rn))
                crops.append((path, (x, y, w, h)))
                crop_info.append({"region_id": r.get("id"), "region_name": r.get("name"),
                                  "file": "crops/" + os.path.basename(path), "crop_xywh": [x, y, w, h]})
        motion = decode_pass(ff, joined, crops, os.path.join(ldir, name + "_decode.log"),
                             motion=cfg.get("_motion", True), crf=cfg.get("video_crop_crf", 18),
                             preset=cfg.get("video_crop_preset", "veryfast"))
        for c in crop_info:
            n, w, h = count_frames(ff, os.path.join(out, c["file"]))
            c["frames"], c["frame_count_matches"] = n, (n == len(pts))
        if motion is not None:
            write_csv(os.path.join(fdir, name + "_motion.csv"), ["frame", "host_time", "motion"],
                      [{"frame": i, "host_time": "%.6f" % host[i] if i < len(host) else "",
                        "motion": "%.4f" % m} for i, m in enumerate(motion)])
    finally:
        if os.path.isfile(joined):
            os.remove(joined)
    return {"segments": nseg, "frames": len(pts),
            "duration_s": round(pts[-1] - pts[0], 2) if len(pts) > 1 else 0,
            "first_host_time": host[0] if host else None, "last_host_time": host[-1] if host else None,
            "anchor_host_time": anchor["anchor_host_time"] if anchor else None,
            "anchor_spread_p05_ms": anchor["spread_p05_ms"] if anchor else None,
            "repaired_timestamps": repaired,
            "motion_frames": int(len(motion)) if motion is not None else 0,
            "crops": crop_info}


def build_radiometric(session, md, cam, out):
    raw = os.path.join(session, "raw")
    src = os.path.join(raw, "radiometric_%s" % cam)
    index = read_csv(os.path.join(src, "index.csv"))
    if not index:
        return None
    sensor = tuple((md.get("radiometric") or {}).get("sensor") or (256, 192))
    rows, mats = [], []
    for r in index:
        if r.get("status") != "200" or not r.get("file"):
            continue
        path = os.path.join(src, r["file"])
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            body = fh.read()
        try:
            arr = extract_matrix(body, sensor[0], sensor[1])
        except Exception as e:                                          # noqa - report and skip
            rows.append({"seq": r.get("seq"), "error": str(e)[:80], "file": r["file"]})
            continue
        t_send, t_hdr = float(r["t_send"]), float(r["t_hdr"])
        mats.append(arr)
        rows.append({
            "seq": int(r["seq"]), "index": len(mats) - 1,
            # No capture time from the camera: the instant lies between the request
            # leaving and the first response byte arriving.
            "host_time": "%.6f" % ((t_send + t_hdr) / 2),
            "uncertainty_ms": round((t_hdr - t_send) * 1000 / 2, 1),
            "tmin_c": round(float(arr.min()), 2), "tmax_c": round(float(arr.max()), 2),
            "tmean_c": round(float(arr.mean()), 2),
            "freeze": r.get("freeze", ""), "duplicate": r.get("dup", ""), "file": r["file"]})
    if not mats:
        return None
    stack = np.stack(mats).astype("float32")
    np.save(os.path.join(out, "radiometric_%s.npy" % cam), stack)
    write_csv(os.path.join(out, "radiometric_%s.csv" % cam),
              ["seq", "index", "host_time", "uncertainty_ms", "tmin_c", "tmax_c", "tmean_c",
               "freeze", "duplicate", "file", "error"], rows)

    # region crops of the matrices
    cdir = os.path.join(out, "crops")
    if not os.path.isdir(cdir):
        os.makedirs(cdir)
    for old in glob.glob(os.path.join(cdir, "radiometric_%s__*.npy" % cam)):
        os.remove(old)
    crops, used = [], set()
    for r in (md.get("regions") or {}).get("%s_thermal" % cam) or []:
        rp = r.get("radiometric_px")
        if not rp:
            continue
        x, y = max(0, int(rp["x"])), max(0, int(rp["y"]))
        w, h = min(int(rp["w"]), stack.shape[2] - x), min(int(rp["h"]), stack.shape[1] - y)
        if w <= 0 or h <= 0:
            continue
        rn = safe_name(r.get("name") or r.get("id"))
        if rn in used:
            rn = rn + "_" + safe_name(r.get("id"))
        used.add(rn)
        fn = "radiometric_%s__%s.npy" % (cam, rn)
        np.save(os.path.join(cdir, fn), np.ascontiguousarray(stack[:, y:y + h, x:x + w]))
        crops.append({"region_id": r.get("id"), "region_name": r.get("name"), "file": "crops/" + fn,
                      "crop_xywh": [x, y, w, h]})
    good = [r for r in rows if "index" in r]
    return {"file": "radiometric_%s.npy" % cam, "shape": list(stack.shape),
            "matrices": len(good), "failed": len(rows) - len(good),
            "duplicates": sum(1 for r in good if str(r.get("duplicate")) == "1"),
            "first_host_time": float(good[0]["host_time"]), "last_host_time": float(good[-1]["host_time"]),
            "median_uncertainty_ms": float(np.median([r["uncertainty_ms"] for r in good])),
            "tmax_c": max(r["tmax_c"] for r in good), "crops": crops}


def build_keyence(session, md, out):
    index = read_csv(os.path.join(session, "raw", "keyence", "index.csv"))
    if not index:
        return None
    by_seq = {}
    for r in index:
        seq = r.get("seq") or "0"
        e = by_seq.setdefault(seq, {"seq": int(seq), "image": "", "result": "", "host_time": "",
                                    "uncertainty_ms": "", "trigger_no": "", "device_time": "",
                                    "total_status": "", "error": ""})
        if r.get("kind") == "image" and r.get("file"):
            e["image"] = "raw/keyence/" + r["file"]
            # Picture taken between trigger leaving and response arriving; the FTP
            # transfer happens afterwards.
            if r.get("t_trigger") and r.get("t_response"):
                t0, t1 = float(r["t_trigger"]), float(r["t_response"])
                e["host_time"] = "%.6f" % ((t0 + t1) / 2)
                e["uncertainty_ms"] = round((t1 - t0) * 1000 / 2, 1)
            elif r.get("t_received"):
                e["host_time"] = "%.6f" % float(r["t_received"])
        elif r.get("kind") == "result" and r.get("file"):
            e["result"] = "raw/keyence/" + r["file"]
            for k in ("trigger_no", "device_time", "total_status"):
                if r.get(k):
                    e[k] = r[k]
        if r.get("error"):
            e["error"] = r["error"]
    rows = [e for e in sorted(by_seq.values(), key=lambda x: x["seq"]) if e["image"] or e["error"]]
    if not rows:
        return None
    write_csv(os.path.join(out, "keyence.csv"),
              ["seq", "host_time", "uncertainty_ms", "image", "result", "trigger_no", "device_time",
               "total_status", "error"], rows)
    timed = [float(r["host_time"]) for r in rows if r["host_time"]]
    region = ((md.get("regions") or {}).get("keyence") or [None])[0]
    return {"file": "keyence.csv", "images": sum(1 for r in rows if r["image"]),
            "with_time": len(timed), "failed": sum(1 for r in rows if r["error"]),
            "first_host_time": timed[0] if timed else None, "last_host_time": timed[-1] if timed else None,
            "region_px": (region or {}).get("px")}


def load_motion(out, name):
    rows = read_csv(os.path.join(out, "frames", name + "_motion.csv"))
    t = [fnum(r["host_time"]) for r in rows]
    m = [fnum(r["motion"]) for r in rows]
    pairs = [(a, b) for a, b in zip(t, m) if a is not None and b is not None]
    if len(pairs) < 10:
        return None
    return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])


def build_session(ff, session, cfg, force=False, dry=False):
    """Bring one run's derived/ folder up to date. Returns (summary, actions)."""
    md = read_json(os.path.join(session, "metadata.json"), {})
    out = os.path.join(session, "derived")
    state_path = os.path.join(out, "build_state.json")
    state = read_json(state_path, {}) or {}
    if state.get("state_version") != STATE_VERSION and state.get("builder") != "2.0.0":
        state = {"steps": {}}
    steps = state.setdefault("steps", {})
    fps = run_fingerprints(session, md, cfg)
    old_summary = read_json(os.path.join(out, "summary.json"), {}) or {}

    outputs = state.setdefault("outputs", {})

    def outputs_ok(key):
        return all(os.path.isfile(os.path.join(out, f)) for f in outputs.get(key, []))

    todo = [k for k, v in sorted(fps.items()) if force or steps.get(k) != v or not outputs_ok(k)]
    meta_sig = sha1_file(os.path.join(session, "metadata.json"))
    events_path = os.path.join(session, "events.jsonl")
    events_sig = sha1_file(events_path) if os.path.isfile(events_path) else None
    light = todo or state.get("metadata") != meta_sig or state.get("events") != events_sig \
        or not os.path.isfile(os.path.join(out, "summary.json"))
    if dry or (not todo and not light):
        return old_summary, todo + (["metadata"] if light and not todo else [])

    if not os.path.isdir(out):
        os.makedirs(out)
    for pat in ("*.joined.mkv", "*.joined.mkv.txt", "*.tmp", os.path.join("crops", "*.part.mp4"),
                os.path.join("frames", "*.tmp")):
        for stale in glob.glob(os.path.join(out, pat)):         # left by an interrupted build
            try:
                os.remove(stale)
            except OSError:
                pass
    summary = {"session_id": md.get("session_id"), "builder": BUILDER_VERSION,
               "video": dict(old_summary.get("video") or {}),
               "radiometric": dict(old_summary.get("radiometric") or {}),
               "keyence": old_summary.get("keyence")}

    for key in todo:
        kind, _, what = key.partition(":")
        t0 = time.time()
        heartbeat()
        if kind == "video":
            res = build_video(ff, session, md, what, out, cfg)
            if res:
                summary["video"][what] = res
                log("    %-14s %5d frames, %d segment(s), %.0f s video, %d crop(s)%s  [%.0f s]"
                    % (what, res["frames"], res["segments"], res["duration_s"], len(res["crops"]),
                       ", %d repeated timestamps repaired" % res["repaired_timestamps"]
                       if res["repaired_timestamps"] else "", time.time() - t0))
                bad = [c["file"] for c in res["crops"] if not c["frame_count_matches"]]
                if bad:
                    log("    WARNING frame count of %s differs from the source" % ", ".join(bad))
            else:
                summary["video"].pop(what, None)
                log("    %-14s no segments" % what)
        elif kind == "rad":
            res = build_radiometric(session, md, what, out)
            if res:
                summary["radiometric"][what] = res
                log("    radiometric %s  %d matrices %s, +/- %.0f ms, max %.1f C, %d crop(s)"
                    % (what, res["matrices"], res["shape"], res["median_uncertainty_ms"], res["tmax_c"],
                       len(res["crops"])))
            else:
                summary["radiometric"].pop(what, None)
        elif kind == "keyence":
            summary["keyence"] = build_keyence(session, md, out)
            if summary["keyence"]:
                log("    keyence        %d pictures" % summary["keyence"]["images"])
        produced = []
        if kind == "video" and summary["video"].get(what):
            produced = ["frames/%s_frames.csv" % what] + \
                (["frames/%s_motion.csv" % what] if cfg.get("_motion", True) else []) + \
                [c["file"] for c in summary["video"][what]["crops"]]
        elif kind == "rad" and summary["radiometric"].get(what):
            produced = ["radiometric_%s.npy" % what, "radiometric_%s.csv" % what] + \
                [c["file"] for c in summary["radiometric"][what]["crops"]]
        elif kind == "keyence" and summary.get("keyence"):
            produced = ["keyence.csv"]
        outputs[key] = produced
        steps[key] = fps[key]
        state["builder"], state["state_version"] = BUILDER_VERSION, STATE_VERSION
        write_json(state_path, state)               # progress survives an interruption

    # ---- alignment (cheap; from the motion files) -------------------------- #
    signals = dict((n, load_motion(out, n)) for n in STREAMS if n in summary["video"])
    ver = read_json(os.path.join(session, "verification.json"), {}) or {}
    arrival = ver.get("start_offsets_ms_vs_cam1_optical") or {}
    if REFERENCE in signals and signals[REFERENCE] is not None:
        offsets = align_streams(signals, REFERENCE, arrival)
        problem = None
    else:
        offsets, problem = dict((k, {"offset_ms": v, "method": "arrival estimate", "trust": "low"})
                                for k, v in arrival.items()), "no motion signal for the reference"
    sync = {"reference": REFERENCE, "grid_ms": GRID_MS,
            "note": ("offset_ms is how much later a stream's content is than the reference. "
                     "Subtract offset_ms/1000 from that stream's host times to put all streams on "
                     "the reference timeline."),
            "streams": offsets, "problem": problem}
    for cam, rad in summary["radiometric"].items():
        sync["streams"]["%s_radiometric" % cam] = {
            "offset_ms": 0.0, "method": "arrival midpoint, see radiometric_%s.csv" % cam,
            "median_uncertainty_ms": round(rad["median_uncertainty_ms"], 1), "trust": "medium"}
    if summary.get("keyence"):
        sync["streams"]["keyence"] = {"offset_ms": 0.0, "method": "trigger midpoint, see keyence.csv",
                                      "trust": "high"}
    write_json(os.path.join(out, "sync.json"), sync)
    summary["sync"] = sync

    # ---- telemetry ---------------------------------------------------------- #
    entries = []
    if os.path.isfile(events_path):
        with io.open(events_path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    entries.append({"host_time": e.get("t"), "kind": "event", "data": e})
                except ValueError:
                    pass
    for note in md.get("operator_notes_during_run") or []:
        entries.append({"host_time": note.get("t"), "kind": "note", "data": note})
    for r in read_csv(os.path.join(out, "keyence.csv")) if summary.get("keyence") else []:
        if r.get("host_time"):
            entries.append({"host_time": float(r["host_time"]), "kind": "keyence",
                            "data": {"image": r["image"], "trigger_no": r["trigger_no"]}})
    for cam in summary["radiometric"]:
        for r in read_csv(os.path.join(out, "radiometric_%s.csv" % cam)):
            if r.get("host_time"):
                entries.append({"host_time": float(r["host_time"]), "kind": "matrix",
                                "data": {"camera": cam, "index": r["index"], "tmax_c": r["tmax_c"],
                                         "uncertainty_ms": r["uncertainty_ms"]}})
    entries = sorted([e for e in entries if e.get("host_time")], key=lambda e: e["host_time"])
    tmp = os.path.join(out, "telemetry.jsonl.tmp")
    with io.open(tmp, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, os.path.join(out, "telemetry.jsonl"))
    summary["telemetry_entries"] = len(entries)
    summary["built_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    summary["ffmpeg"] = ff.version
    write_json(os.path.join(out, "summary.json"), summary)
    # remove outputs of the previous builder version, if any
    for stale in ("dataset.json",):
        p = os.path.join(out, stale)
        if os.path.isfile(p):
            os.remove(p)
    state["metadata"], state["events"] = meta_sig, events_sig
    state["builder"], state["state_version"] = BUILDER_VERSION, STATE_VERSION
    write_json(state_path, state)
    return summary, todo or ["metadata"]


# =========================================================================== #
# MC6 machine export (Excel 2003 SpreadsheetML written by the KraussMaffei MC6)
# =========================================================================== #
SS = "{urn:schemas-microsoft-com:office:spreadsheet}"

# Best-effort English keys for the MC6 column headers (Slovenian HMI). The original
# header and unit are always kept in machine_columns.csv.
KNOWN_COLUMNS = [
    ("Cikel-čas C", "cycle_time_s"), ("Plast-čas C", "plasticizing_time_s"),
    ("Plast-hod C", "plasticizing_stroke_mm"), ("Brizg-čas C", "injection_time_s"),
    ("Masa-blazin.", "melt_cushion_mm"), ("Prekl MasaTlZ", "switchover_melt_pressure_bar"),
    ("Max MasaTl", "max_melt_pressure_bar"), ("Pot prekl Z", "switchover_position_mm"),
    ("Olje Z14", "oil_temp_z14_c"), ("Prirobn Z15", "feed_flange_temp_z15_c"),
    ("Or Zap cas C", "mould_close_time_s"), ("ZS vzp čas C", "clamp_force_build_time_s"),
    ("ZS razg čas C", "clamp_force_release_time_s"), ("OrOdpir cas C", "mould_open_time_s"),
    ("Čas hlajenja Z", "cooling_time_s"), ("Raz- kalupljenje", "demoulding_time_s"),
    ("Čas pavze Z", "pause_time_s"), ("NaknTl čas C", "holding_pressure_time_s"),
    ("AgrNaz čas C", "unit_retract_time_s"), ("Ekviv. obdelov.", "equivalent_processing"),
    ("Ind. visk.", "viscosity_index"), ("APC – Ref. pot 0°", "apc_ref_position_mm"),
    ("Pril. nak. tlak.", "holding_pressure_adjust_pct"),
    ("APC+ Vol.", "apc_volume_cm3"), ("APC+ Vol.Xfr", "apc_volume_transfer_cm3"),
]


def _slug(s):
    s = s.lower().replace("č", "c").replace("š", "s").replace("ž", "z").replace("°", "")
    s = s.replace("³", "3").replace("–", "-")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def column_key(top, bottom, unit):
    label = " ".join(x for x in (top, bottom) if x).strip()
    label = re.sub(r"\s+", " ", re.sub(r"-\s+", "-", label))     # "Cikel- čas C" -> "Cikel-čas C"
    for orig, key in KNOWN_COLUMNS:
        if label.replace(" ", "") == orig.replace(" ", ""):
            return key, True
    m = re.match(r"Cilind\. Z\s*(\d+)$", label)
    if m:
        return "barrel_temp_z%s_c" % m.group(1), True
    m = re.match(r"Oro-gr Z\s*(\d+)$", label)
    if m:
        return "hot_runner_z%s_c" % m.group(1), True
    m = re.match(r"Durchfl\. Temp Z(\d+)$", label)
    if m:
        return "cooling_flow_z%s_per_min" % m.group(1), True
    m = re.match(r"Temp (\d+)$", label)
    if m:
        return "cooling_temp_z%s_c" % m.group(1), True
    u = _slug(unit.strip("[]")) if unit else ""
    return (_slug(label) or "col") + ("_" + u if u else ""), False


def parse_machine_export(path):
    """Returns (columns, cycles, setpoints). Each cycle is a dict of column key -> value."""
    root = ET.parse(path).getroot()
    sheet = None
    for ws in root.iter(SS + "Worksheet"):
        if ws.get(SS + "Name") == "Cycles" or sheet is None:
            sheet = ws
    rows = []
    for r in sheet.iter(SS + "Row"):
        vals, col = [], 0
        for c in r.findall(SS + "Cell"):
            idx = c.get(SS + "Index")
            if idx:
                while len(vals) < int(idx) - 1:
                    vals.append(None)
            d = c.find(SS + "Data")
            vals.append(d.text.strip() if d is not None and d.text is not None else None)
        rows.append(vals)
    hdr = None
    for i, r in enumerate(rows):
        if r and r[0] == "Datum" and len(r) > 2:
            hdr = i
            break
    if hdr is None or hdr < 2:
        raise ValueError("no 'Datum' header row found")
    units, top, bottom = rows[hdr], rows[hdr - 2], rows[hdr - 1]
    ncol = max(len(units), len(top), len(bottom))

    def cell(r, j):
        return (r[j] if j < len(r) else None) or ""

    columns, seen = [], {}
    for j in range(3, ncol):
        key, known = column_key(cell(top, j), cell(bottom, j), cell(units, j))
        if key in seen:
            seen[key] += 1
            key = "%s_%d" % (key, seen[key])
        else:
            seen[key] = 1
        columns.append({"key": key, "index": j, "header": (cell(top, j) + " " + cell(bottom, j)).strip(),
                        "unit": cell(units, j).strip("[]"), "translated": known})
    cycles, setpoints = [], []
    for r in rows[hdr + 1:]:
        if not r or not r[0]:
            continue
        if re.match(r"\d\d\.\d\d\.\d\d$", r[0]) and len(r) > 2 and r[1] and r[2]:
            try:
                t = datetime.datetime.strptime(r[0] + " " + r[1], "%d.%m.%y %H:%M:%S")
            except ValueError:
                continue
            c = {"machine_time": t, "cycle_counter": int(float(r[2]))}
            for col in columns:
                c[col["key"]] = fnum(cell(r, col["index"]))
            cycles.append(c)
        else:
            sp = {"row": r[0]}
            for col in columns:
                sp[col["key"]] = cell(r, col["index"])
            setpoints.append(sp)
    return columns, cycles, setpoints


def find_machine_exports(root):
    cands = []
    for pat in ("*.xml", "*.XML", os.path.join("machine_exports", "**", "*.xml"),
                os.path.join("machine_exports", "**", "*.XML")):
        cands += glob.glob(os.path.join(root, pat), recursive=True)
    out = []
    for p in sorted(set(os.path.normcase(os.path.abspath(c)) for c in cands)):
        try:
            with open(p, "rb") as f:
                head = f.read(4000)
        except (OSError, IOError):
            continue
        if b"urn:schemas-microsoft-com:office:spreadsheet" in head and \
                (b"KraussMaffei" in head or b"Cycles" in head or b"MC6" in head):
            out.append(p)
    return out


def load_machine(root, cfg, warnings):
    exports = find_machine_exports(root)
    columns, merged, setpoints, sources = None, {}, [], []
    for p in exports:
        try:
            cols, cycles, sp = parse_machine_export(p)
        except Exception as e:                                          # noqa
            warnings.append("machine export %s could not be read: %s" % (os.path.basename(p), e))
            continue
        if columns is None:
            columns = cols
        elif [c["key"] for c in cols] != [c["key"] for c in columns]:
            known = set(c["key"] for c in columns)
            columns += [c for c in cols if c["key"] not in known]
        for c in cycles:
            merged[(c["machine_time"], c["cycle_counter"])] = c      # later exports win
        setpoints += [dict(s, source=os.path.basename(p)) for s in sp]
        span = (min(c["machine_time"] for c in cycles), max(c["machine_time"] for c in cycles)) \
            if cycles else (None, None)
        sources.append({"file": os.path.relpath(p, root), "sha1": sha1_file(p), "cycles": len(cycles),
                        "first": span[0].isoformat() if span[0] else None,
                        "last": span[1].isoformat() if span[1] else None})
    cycles = sorted(merged.values(), key=lambda c: (c["machine_time"], c["cycle_counter"]))

    for c in cycles:
        c["machine_epoch"] = local_to_epoch(c["machine_time"])     # machine wall clock read as PC local time
        c["day"] = c["machine_time"].strftime("%Y-%m-%d")
        c["cycle_uid"] = "%s_c%03d" % (c["machine_time"].strftime("%Y%m%d_%H%M%S"), c["cycle_counter"])
        c["pc_start"] = c["pc_end"] = c["clock_offset_s"] = None
        c["clock_offset_uncertainty_s"], c["clock_offset_source"] = None, "missing"
    # A cycle runs from its own timestamp to the next one (the MC6 writes the row at cycle
    # start; its cycle time is filled in when the next cycle starts).
    known = [c.get("cycle_time_s") for c in cycles if c.get("cycle_time_s")]
    typical = float(np.median(known)) if known else None
    for i, c in enumerate(cycles):
        nxt = cycles[i + 1] if i + 1 < len(cycles) else None
        dur, src = c.get("cycle_time_s"), "mc6_cycle_time"
        if not dur and nxt is not None:
            gap = nxt["machine_epoch"] - c["machine_epoch"]
            if 0 < gap < 120:
                dur, src = gap, "gap_to_next_cycle"
        if not dur and typical:
            dur, src = typical, "typical_cycle_time"
        c["duration_s"], c["duration_source"] = dur, src if dur else ""
    return {"columns": columns or [], "cycles": cycles, "setpoints": setpoints, "sources": sources}


# =========================================================================== #
# Machine clock: configured offset, checked (or estimated) from the videos
# =========================================================================== #
def score_offset(opens, starts, d, lead, tol):
    """How many mould openings fall 'lead' seconds (+/- tol) before a machine cycle start
    when the machine clock is shifted by d. Returns (count, lead per matched opening)."""
    m = opens - d
    k = np.searchsorted(starts, m, "right")
    ok = k < len(starts)
    dt = np.full(len(m), 1e9)
    dt[ok] = starts[k[ok]] - m[ok]
    hit = np.abs(dt - lead) <= tol
    return int(hit.sum()), dt[hit]


def estimate_offset(opens, starts, lead, tol, lo, hi):
    """Best machine-clock offset in [lo, hi]: coarse 0.25 s grid, then 0.05 s around the
    best; the result is the centre of the best-scoring plateau. Also returns the best score
    found more than 5 s away (the main risk is a shift by exactly one cycle)."""
    if len(opens) == 0 or len(starts) == 0:
        return None
    grid = np.arange(lo, hi + 0.25, 0.25)
    sc = np.array([score_offset(opens, starts, d, lead, tol)[0] for d in grid])
    best = float(grid[int(np.argmax(sc))])
    fine = np.arange(best - 1.5, best + 1.5, 0.05)
    fs = np.array([score_offset(opens, starts, d, lead, tol)[0] for d in fine])
    top = fine[fs == fs.max()]
    centre = float((top.min() + top.max()) / 2)
    far = sc[np.abs(grid - centre) > 5]
    return {"offset_s": round(centre, 2), "matched": int(fs.max()), "of": int(len(opens)),
            "plateau_s": [round(float(top.min()), 2), round(float(top.max()), 2)],
            "runner_up_matched": int(far.max()) if len(far) else 0}


def resolve_clock(machine, opens_by_day, cfg, warnings):
    """Decide the offset (PC time - machine time) for every recording day and put the
    machine cycles on the PC clock.

    Configured offsets are used as given and checked against the videos. Days without one
    are estimated from the videos: near the closest configured day's offset when there is
    one, otherwise by a wide search that is accepted only when it is unambiguous."""
    lead = float(cfg.get("mould_open_lead_s") or 3.56)
    tol = float(cfg.get("mould_open_lead_tolerance_s") or 1.5)
    near = float(cfg.get("clock_auto_search_s") or 20)
    conf = dict((o["date"], o) for o in cfg.get("machine_clock_offsets") or [] if o.get("date"))
    default = cfg.get("default_machine_clock_offset_s")
    report = {}
    days = sorted(set(c["day"] for c in machine["cycles"]))
    for day in days:
        cyc = [c for c in machine["cycles"] if c["day"] == day]
        starts = np.array(sorted(c["machine_epoch"] for c in cyc))
        opens = np.array(sorted(opens_by_day.get(day, [])))
        rep_ = {"runs_with_mould_opening": int(len(opens)), "machine_cycles": len(cyc)}
        used, unc, src = None, None, "missing"
        if day in conf:
            used, unc, src = float(conf[day]["offset_s"]), float(conf[day].get("uncertainty_s", 1.0)), "config"
            est = estimate_offset(opens, starts, lead, tol, used - near, used + near) if len(opens) >= 3 else None
            rep_["video_estimate"] = est
            if est and est["matched"] >= max(3, 0.5 * est["of"]) and abs(est["offset_s"] - used) > 1.5:
                warnings.append("clock %s: configured offset %.1f s but the videos say %.1f s (%d/%d runs agree); "
                                "check machine_clock_offsets" % (day, used, est["offset_s"], est["matched"], est["of"]))
            elif est and est["matched"] < 0.5 * est["of"]:
                warnings.append("clock %s: only %d of %d runs agree with the configured offset; check it"
                                % (day, est["matched"], est["of"]))
        elif len(opens) >= 3:
            priors = sorted(conf.values(), key=lambda o: abs((datetime.datetime.strptime(o["date"], "%Y-%m-%d")
                                                              - datetime.datetime.strptime(day, "%Y-%m-%d")).days))
            prior = float(priors[0]["offset_s"]) if priors else (float(default) if default is not None else None)
            if prior is not None:
                est = estimate_offset(opens, starts, lead, tol, prior - near, prior + near)
                ok = est and est["matched"] >= max(3, 0.5 * est["of"])
                how = "near %.1f s (%s)" % (prior, priors[0]["date"] if priors else "default")
            else:
                est = estimate_offset(opens, starts, lead, tol, -3 * 3600, 3 * 3600)
                ok = est and est["matched"] >= max(5, 0.6 * est["of"]) and \
                    est["matched"] - est["runner_up_matched"] >= max(3, 0.05 * est["of"])
                how = "wide search +/- 3 h"
            rep_["video_estimate"] = est
            if ok:
                used, unc, src = est["offset_s"], 1.0, "video estimate, " + how
                warnings.append("clock %s: no configured offset; estimated %.2f s from the videos (%s, %d/%d runs). "
                                "Add it to machine_clock_offsets once confirmed." % (day, used, how, est["matched"], est["of"]))
            else:
                warnings.append("clock %s: no configured offset and the videos do not give a clear one; add it "
                                "to machine_clock_offsets (its cycles are not matched to runs)" % day)
        else:
            if default is not None:
                used, unc, src = float(default), None, "config default"
            else:
                warnings.append("clock %s: no machine clock offset configured and too few runs to estimate it "
                                "(its cycles are not matched to runs)" % day)
        if used is not None and len(opens):
            n, leads = score_offset(opens, starts, used, lead, tol)
            rep_["runs_agreeing"] = n
            if len(leads):
                rep_["mould_open_before_next_cycle_s"] = {
                    "median": round(float(np.median(leads)), 2), "p10": round(float(np.percentile(leads, 10)), 2),
                    "p90": round(float(np.percentile(leads, 90)), 2)}
        rep_.update({"offset_s": used, "uncertainty_s": unc, "source": src})
        report[day] = rep_
        for c in cyc:
            c["clock_offset_s"], c["clock_offset_uncertainty_s"], c["clock_offset_source"] = used, unc, src
            if used is not None:
                c["pc_start"] = c["machine_epoch"] + used
                c["pc_end"] = c["pc_start"] + c["duration_s"] if c["duration_s"] else None
    return report


# =========================================================================== #
# Labels from the operator's notes
# =========================================================================== #
RE_PCT = re.compile(r"(\d{1,3})\s*%\s*(regrind|virgin|original)", re.I)
RE_SHOT = re.compile(r"^\s*(\d{1,3})\s*[.)]\s")
RE_OOM = re.compile(r"(out of material|run out|ran out)", re.I)


def parse_label_text(text):
    out = {}
    if not text:
        return out
    m = RE_PCT.search(text)
    if m:
        pct, kind = int(m.group(1)), m.group(2).lower()
        out["regrind_pct"] = pct if kind == "regrind" else 100 - pct
    m = RE_SHOT.match(text)
    if m:
        out["shot_in_batch"] = int(m.group(1))
    if RE_OOM.search(text):
        out["out_of_material"] = 1
    if re.search(r"\bunusable\b|\bnot usable\b|\bscrap\b|\breject", text, re.I):
        out["quality_note"] = "bad"
    elif re.search(r"\busable\b|\bgood\b", text, re.I):
        out["quality_note"] = "usable"
    return out


def label_runs(runs, cfg):
    """Fill regrind_pct etc. from notes, verdict reason and run notes; runs without a
    label take the label of their batch (runs recorded back-to-back with the same
    material, separated from the next batch by a pause of more than batch_gap_s)."""
    gap = float(cfg.get("batch_gap_s") or 120)
    runs.sort(key=lambda r: r["_start"] or 0)
    batch, prev = 0, None
    for r in runs:
        if prev is None or (r["_start"] or 0) - (prev["_stop"] or 0) > gap \
                or r["material"] != prev["material"] or r["date"] != prev["date"]:
            batch += 1
        r["batch_id"] = batch
        prev = r
    for r in runs:
        lab, src = {}, {}
        for source, text in (("run_notes", r["_meta_notes"]), ("verdict_reason", r["verdict_reason"]),
                             ("note_during_run", r["notes_during_run"])):
            for k, v in parse_label_text(text).items():
                lab[k], src[k] = v, source         # later sources win (most specific)
        r["_lab"], r["_src"] = lab, src
    by_batch = {}
    for r in runs:
        by_batch.setdefault(r["batch_id"], []).append(r)
    for b, members in by_batch.items():
        vals = [m["_lab"]["regrind_pct"] for m in members if "regrind_pct" in m["_lab"]]
        common = max(set(vals), key=vals.count) if vals else None
        for pos, m in enumerate(members, 1):
            m["position_in_batch"] = pos
            m["batch_size"] = len(members)
            if "regrind_pct" in m["_lab"]:
                m["regrind_pct"], m["regrind_source"] = m["_lab"]["regrind_pct"], m["_src"]["regrind_pct"]
                if common is not None and m["_lab"]["regrind_pct"] != common:
                    m["label_warning"] = "differs from the rest of batch %d (%s%%)" % (b, common)
            elif common is not None:
                m["regrind_pct"], m["regrind_source"] = common, "inferred_from_batch"
            else:
                m["regrind_pct"], m["regrind_source"] = "", "unknown"
            m["shot_in_batch"] = m["_lab"].get("shot_in_batch", "")
            m["out_of_material"] = m["_lab"].get("out_of_material", 0)
            m["quality_note"] = m["_lab"].get("quality_note", "")
    for r in runs:
        ov = (cfg.get("label_overrides") or {}).get(r["run"]) or \
            (cfg.get("label_overrides") or {}).get(r["run_id"]) or {}
        for k, v in ov.items():
            r[k] = v
            if k == "regrind_pct":
                r["regrind_source"] = "override"
    return runs


# =========================================================================== #
# Dataset tables
# =========================================================================== #
def content_times(out, name, offset_ms):
    rows = read_csv(os.path.join(out, "frames", name + "_frames.csv"))
    t = [fnum(r["host_time"]) for r in rows]
    if not t or any(x is None for x in t):
        return None
    return np.array(t) - (offset_ms or 0.0) / 1000.0


def index_range(times, t0, t1):
    """First and last index with t0 <= time < t1 (or '' if none)."""
    if times is None or not len(times):
        return "", ""
    a = int(np.searchsorted(times, t0, "left"))
    b = int(np.searchsorted(times, t1, "left")) - 1
    return (a, b) if b >= a else ("", "")


def motion_bursts(out, name, offset_ms):
    """Onsets of large movement bursts (mould opening / ejection) in a stream's motion
    signal, on the reference timeline. Returns a list of (onset_time, peak, area)."""
    rows = read_csv(os.path.join(out, "frames", name + "_motion.csv"))
    pairs = [(fnum(r["host_time"]), fnum(r["motion"])) for r in rows]
    pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
    if len(pairs) < 50:
        return []
    t = np.array([p[0] for p in pairs]) - (offset_ms or 0.0) / 1000.0
    v = np.convolve(np.array([p[1] for p in pairs]), np.ones(5) / 5.0, "same")
    base = float(np.median(v))
    mad = float(np.median(np.abs(v - base))) + 1e-6
    thr = base + max(12 * mad, 2.0)
    above = v > thr
    bursts, i, n = [], 0, len(v)
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j < n and (above[j] or (j + 1 < n and np.any(above[j:min(n, j + 50)]))):
            j += 1                                   # merge sub-bursts closer than 2 s
        peak = float(v[i:j].max())
        lo = base + 0.2 * (peak - base)
        k = i
        while k > 0 and v[k - 1] > lo:
            k -= 1
        if i > 0 or v[0] <= thr:                     # ignore a burst already running at the start
            bursts.append((float(t[k]), peak, float((v[i:j] - base).sum())))
        i = j
    return bursts


def build_tables(root, sessions, cfg, args):
    out_dir = os.path.join(root, args.dataset_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    warnings = []
    for s in sessions:
        learn_tz((read_json(os.path.join(s, "metadata.json"), {}) or {}).get("started_at"))
    machine = load_machine(root, cfg, warnings)
    mcols = [c["key"] for c in machine["columns"]]

    runs, run_cycles, regions, ctx = [], [], [], []
    for s in sessions:
        md = read_json(os.path.join(s, "metadata.json"), {}) or {}
        d = os.path.join(s, "derived")
        sm = read_json(os.path.join(d, "summary.json"), {}) or {}
        sid = md.get("session_id") or os.path.basename(s)
        om = md.get("operator_metadata") or {}
        verdict = md.get("operator_verdict") or {}
        sync = (sm.get("sync") or {}).get("streams") or {}
        times = dict((n, content_times(d, n, (sync.get(n) or {}).get("offset_ms"))) for n in STREAMS
                     if n in (sm.get("video") or {}))
        ref = times.get(REFERENCE)
        start = float(ref[0]) if ref is not None else md.get("started_epoch")
        stop = float(ref[-1]) if ref is not None else (start + (md.get("duration_s") or 0) if start else None)
        rad_t = dict((cam, np.array([float(r["host_time"]) for r in read_csv(os.path.join(d, "radiometric_%s.csv" % cam))
                                     if r.get("host_time")])) for cam in (sm.get("radiometric") or {}))
        key_rows = [r for r in read_csv(os.path.join(d, "keyence.csv")) if r.get("host_time")]
        notes = md.get("operator_notes_during_run") or []
        vsum = md.get("verification_summary") or {}
        r = {"run_id": sid, "run": run_short(sid), "folder": os.path.relpath(s, root),
             "date": (md.get("started_at") or "")[:10], "start_pc": iso(start), "stop_pc": iso(stop),
             "start_epoch": "%.3f" % start if start else "", "duration_s": round(stop - start, 2) if start and stop else "",
             "mould_id": om.get("mould_id", ""), "part_number": om.get("part_number", ""),
             "material": om.get("material", ""), "operator": om.get("operator", ""),
             "thermal_range": (md.get("thermal_range") or {}).get("key", om.get("thermal_range", "")),
             "verdict": verdict.get("verdict", ""), "verdict_reason": verdict.get("reason", ""),
             "notes_during_run": " | ".join(n.get("note", "") for n in notes),
             "status": md.get("status", ""), "stop_reason": md.get("stop_reason", ""),
             "verification_pass": vsum.get("overall_pass", ""), "built": bool(sm),
             "data_complete": int(not missing_parts(s, md)), "missing_on_disk": "; ".join(missing_parts(s, md)),
             "_start": start, "_stop": stop, "_meta_notes": om.get("notes", ""), "label_warning": ""}
        for n in STREAMS:
            v = (sm.get("video") or {}).get(n) or {}
            r["frames_" + n] = v.get("frames", "")
            r["sync_ms_" + n] = (sync.get(n) or {}).get("offset_ms", "")
            r["sync_trust_" + n] = (sync.get(n) or {}).get("trust", "")
        for cam in ("cam1", "cam2"):
            r["matrices_" + cam] = ((sm.get("radiometric") or {}).get(cam) or {}).get("matrices", "")
        r["keyence_pictures"] = len(key_rows)

        # ---- regions -------------------------------------------------------- #
        crop_files = {}
        for n, v in (sm.get("video") or {}).items():
            for c in v.get("crops") or []:
                crop_files[(n, c["region_id"])] = c
        for cam, v in (sm.get("radiometric") or {}).items():
            for c in v.get("crops") or []:
                crop_files[("rad_" + cam, c["region_id"])] = c
        for n, lst in sorted((md.get("regions") or {}).items()):
            for reg in lst:
                px = reg.get("px") or {}
                rp = reg.get("radiometric_px") or {}
                vc = crop_files.get((n, reg.get("id"))) or {}
                rc = crop_files.get(("rad_" + n.split("_")[0], reg.get("id"))) or {} if n.endswith("thermal") else {}
                regions.append({
                    "run_id": sid, "stream": n, "region_id": reg.get("id"), "region_name": reg.get("name"),
                    "x": px.get("x"), "y": px.get("y"), "w": px.get("w"), "h": px.get("h"),
                    "frame_w": (px.get("frame") or ["", ""])[0], "frame_h": (px.get("frame") or ["", ""])[1],
                    "nx": (reg.get("normalized") or {}).get("x"), "ny": (reg.get("normalized") or {}).get("y"),
                    "nw": (reg.get("normalized") or {}).get("w"), "nh": (reg.get("normalized") or {}).get("h"),
                    "rad_x": rp.get("x", ""), "rad_y": rp.get("y", ""), "rad_w": rp.get("w", ""), "rad_h": rp.get("h", ""),
                    "video_crop_file": (os.path.join(r["folder"], "derived", vc["file"]).replace("\\", "/")
                                        if vc.get("file") else ""),
                    "video_crop_xywh": " ".join(str(v) for v in vc.get("crop_xywh", [])),
                    "video_crop_frames": vc.get("frames", ""),
                    "radiometric_crop_file": (os.path.join(r["folder"], "derived", rc["file"]).replace("\\", "/")
                                              if rc.get("file") else "")})

        # ---- mould opening seen by the cameras (largest movement burst) ------ #
        r["mould_open_pc"], r["mould_open_stream"], t_open = "", "", None
        for n in ("cam1_optical", "cam2_optical"):
            if n not in times:
                continue
            bursts = motion_bursts(d, n, (sync.get(n) or {}).get("offset_ms"))
            if bursts:
                t_open = max(bursts, key=lambda b: b[2])[0]
                r["mould_open_pc"], r["mould_open_stream"] = iso(t_open), n
                break
        runs.append(r)
        ctx.append({"sid": sid, "start": start, "stop": stop, "times": times, "rad_t": rad_t,
                    "key_rows": key_rows, "t_open": t_open, "run": r})

    # ---- machine clock per day, then cycles on the PC clock --------------------- #
    opens_by_day = {}
    for c in ctx:
        if c["t_open"] is not None:
            opens_by_day.setdefault(c["run"]["date"], []).append(c["t_open"])
    clock = resolve_clock(machine, opens_by_day, cfg, warnings)
    cycles = sorted([c for c in machine["cycles"] if c["pc_start"] is not None], key=lambda c: c["pc_start"])
    starts = np.array([c["pc_start"] for c in cycles]) if cycles else np.array([])

    for cx in ctx:
        sid, start, stop, times, rad_t, key_rows, r = (cx["sid"], cx["start"], cx["stop"], cx["times"],
                                                         cx["rad_t"], cx["key_rows"], cx["run"])
        best, overl = None, []
        if start and stop and len(starts):
            lo = max(0, int(np.searchsorted(starts, start - 200)) - 1)
            for c in cycles[lo:]:
                if c["pc_start"] > stop:
                    break
                c_end = c["pc_end"] or c["pc_start"] + 1
                ov = min(stop, c_end) - max(start, c["pc_start"])
                if ov <= 0:
                    continue
                dur = c_end - c["pc_start"]
                row = {"run_id": sid, "cycle_uid": c["cycle_uid"], "cycle_counter": c["cycle_counter"],
                       "cycle_start_pc": iso(c["pc_start"]), "cycle_end_pc": iso(c["pc_end"]),
                       "overlap_s": round(ov, 2),
                       "cycle_coverage": round(ov / dur, 3) if dur > 0 else "",
                       "cycle_complete_in_run": int(c["pc_start"] >= start and c_end <= stop),
                       "cycle_start_in_run_s": round(c["pc_start"] - start, 2),
                       "clock_uncertainty_s": c["clock_offset_uncertainty_s"]}
                t0, t1 = max(start, c["pc_start"]), min(stop, c_end)
                for n in STREAMS:
                    a_, b_ = index_range(times.get(n), t0, t1)
                    row["frame_first_" + n], row["frame_last_" + n] = a_, b_
                for cam in ("cam1", "cam2"):
                    a_, b_ = index_range(rad_t.get(cam), t0, t1)
                    row["matrix_first_" + cam], row["matrix_last_" + cam] = a_, b_
                ks = [int(k["seq"]) for k in key_rows if t0 <= float(k["host_time"]) < t1]
                row["keyence_first_seq"], row["keyence_last_seq"] = (ks[0], ks[-1]) if ks else ("", "")
                overl.append(row)
                c.setdefault("_runs", []).append(sid)
                if best is None or ov > best[0]:
                    best = (ov, c, row)
        r["ejected_cycle_uid"], r["mould_open_before_cycle_end_s"] = "", ""
        t_open = cx["t_open"]
        if t_open is not None and len(starts):
            k = int(np.searchsorted(starts, t_open, "right")) - 1
            if k >= 0 and cycles[k]["pc_end"] and t_open < cycles[k]["pc_end"] + 5:
                r["ejected_cycle_uid"] = cycles[k]["cycle_uid"]
                r["mould_open_before_cycle_end_s"] = round(cycles[k]["pc_end"] - t_open, 2)
        run_cycles += overl
        r["cycles_seen"] = len(overl)
        r["cycles_complete"] = sum(o["cycle_complete_in_run"] for o in overl)
        if best:
            c = best[1]
            r["main_cycle_uid"], r["main_cycle_coverage"] = c["cycle_uid"], best[2]["cycle_coverage"]
            r["main_cycle_start_in_run_s"] = best[2]["cycle_start_in_run_s"]
            for k in mcols:
                r["cyc_" + k] = c.get(k)
        else:
            r["main_cycle_uid"] = ""
            if start and machine["cycles"]:
                r["label_warning"] = (r["label_warning"] + "; " if r["label_warning"] else "") + \
                    "no machine cycle found for this run"

    label_runs(runs, cfg)
    runs = [r for r in runs if not r.get("exclude")]
    for r in runs:
        if r.get("label_warning"):
            warnings.append("%s: %s" % (r["run"], r["label_warning"]))
        if not r["data_complete"]:
            warnings.append("%s: incomplete on disk (%s)" % (r["run"], r["missing_on_disk"]))
        elif not r["built"]:
            warnings.append("%s: derived/ not built yet" % r["run"])

    # ---- write ----------------------------------------------------------------- #
    run_fields = (["run_id", "run", "date", "start_pc", "stop_pc", "start_epoch", "duration_s",
                   "regrind_pct", "regrind_source", "batch_id", "position_in_batch", "batch_size",
                   "shot_in_batch", "out_of_material", "verdict", "verdict_reason", "quality_note",
                   "notes_during_run", "label_warning", "mould_id", "part_number", "material", "operator",
                   "thermal_range", "status", "stop_reason", "verification_pass", "data_complete",
                   "missing_on_disk", "folder"]
                  + ["frames_" + n for n in STREAMS] + ["sync_ms_" + n for n in STREAMS]
                  + ["sync_trust_" + n for n in STREAMS]
                  + ["matrices_cam1", "matrices_cam2", "keyence_pictures", "cycles_seen", "cycles_complete",
                     "main_cycle_uid", "main_cycle_coverage", "main_cycle_start_in_run_s",
                     "mould_open_pc", "mould_open_stream", "ejected_cycle_uid", "mould_open_before_cycle_end_s"]
                  + ["cyc_" + k for k in mcols])
    write_csv(os.path.join(out_dir, "runs.csv"), run_fields, runs)

    rc_fields = (["run_id", "cycle_uid", "cycle_counter", "cycle_start_pc", "cycle_end_pc", "overlap_s",
                  "cycle_coverage", "cycle_complete_in_run", "cycle_start_in_run_s", "clock_uncertainty_s"]
                 + [p + n for n in STREAMS for p in ("frame_first_", "frame_last_")]
                 + [p + c for c in ("cam1", "cam2") for p in ("matrix_first_", "matrix_last_")]
                 + ["keyence_first_seq", "keyence_last_seq"])
    write_csv(os.path.join(out_dir, "run_cycles.csv"), rc_fields, run_cycles)

    label_by_run = dict((r["run_id"], r.get("regrind_pct", "")) for r in runs)
    cyc_rows = []
    for c in machine["cycles"]:
        rs = c.get("_runs") or []
        row = {"cycle_uid": c["cycle_uid"], "machine_time": c["machine_time"].isoformat(),
               "cycle_counter": c["cycle_counter"], "start_pc": iso(c["pc_start"]),
               "start_epoch": "%.3f" % c["pc_start"] if c["pc_start"] is not None else "",
               "end_pc": iso(c["pc_end"]), "duration_s": c["duration_s"],
               "duration_source": c.get("duration_source", ""),
               "clock_offset_s": c["clock_offset_s"], "clock_offset_source": c["clock_offset_source"],
               "runs": ";".join(rs), "regrind_pct": label_by_run.get(rs[0], "") if rs else ""}
        for k in mcols:
            row[k] = c.get(k)
        cyc_rows.append(row)
    write_csv(os.path.join(out_dir, "cycles.csv"),
              ["cycle_uid", "machine_time", "cycle_counter", "start_pc", "start_epoch", "end_pc", "duration_s",
               "duration_source", "clock_offset_s", "clock_offset_source", "runs", "regrind_pct"] + mcols, cyc_rows)

    write_csv(os.path.join(out_dir, "regions.csv"),
              ["run_id", "stream", "region_id", "region_name", "x", "y", "w", "h", "frame_w", "frame_h",
               "nx", "ny", "nw", "nh", "rad_x", "rad_y", "rad_w", "rad_h", "video_crop_file", "video_crop_xywh",
               "video_crop_frames", "radiometric_crop_file"], regions)

    col_rows = []
    for col in machine["columns"]:
        vals = [c.get(col["key"]) for c in machine["cycles"] if c.get(col["key"]) is not None]
        col_rows.append({"key": col["key"], "header": col["header"], "unit": col["unit"],
                         "english_key_is_translation": int(col["translated"]),
                         "non_empty": len(vals), "constant": int(len(set(vals)) <= 1),
                         "min": min(vals) if vals else "", "max": max(vals) if vals else ""})
    write_csv(os.path.join(out_dir, "machine_columns.csv"),
              ["key", "header", "unit", "english_key_is_translation", "non_empty", "constant", "min", "max"],
              col_rows)
    write_csv(os.path.join(out_dir, "machine_setpoints.csv"), ["source", "row"] + mcols, machine["setpoints"])

    labelled = [r for r in runs if r.get("regrind_pct") not in ("", None)]
    manifest = {
        "builder": BUILDER_VERSION, "built_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "data_root": os.path.abspath(root),
        "runs": len(runs), "runs_labelled": len(labelled),
        "runs_complete_on_disk": sum(1 for r in runs if r["data_complete"]),
        "runs_built": sum(1 for r in runs if r["built"]),
        "runs_with_machine_cycle": sum(1 for r in runs if r.get("main_cycle_uid")),
        "regrind_pct_counts": dict((str(k), sum(1 for r in labelled if r["regrind_pct"] == k))
                                   for k in sorted(set(r["regrind_pct"] for r in labelled), key=lambda x: float(x))),
        "machine_cycles": len(machine["cycles"]), "machine_exports": machine["sources"],
        "machine_clock": clock,
        "config": dict((k, v) for k, v in cfg.items() if not k.startswith("_")),
        "warnings": warnings,
    }
    write_json(os.path.join(out_dir, "dataset.json"), manifest)
    with io.open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(README)
    return manifest


README = u"""# Aid4SME dataset

Built by `tools/build_dataset.py`. Do not edit these files by hand: re-run the builder.
Settings (machine clock offset, label corrections, crop settings) are in
`../dataset_config.json`.

## Tables

| File | One row per | Use |
|---|---|---|
| `runs.csv` | recorded run | Labels and the main sample index. `regrind_pct` is the experiment variable (0-100 %), `regrind_source` says where it came from (`note_during_run`, `verdict_reason`, `inferred_from_batch`, `override`). `cyc_*` are the MC6 values of the machine cycle the run overlapped most (`main_cycle_uid`). |
| `cycles.csv` | machine cycle (MC6 export) | All 90 MC6 process values per shot, with its start on the PC clock and the runs that saw it. |
| `run_cycles.csv` | run x cycle overlap | Frame indices (per stream), radiometric matrix indices and Keyence pictures that fall inside each cycle. |
| `regions.csv` | operator region | Region boxes in video pixels, normalised and radiometric pixels, and the crop files. |
| `machine_columns.csv` | MC6 column | Original Slovenian header, unit, value range, constant columns. |
| `machine_setpoints.csv` | setpoint row | The export's set values ("Nastavljena vrednost"). |
| `dataset.json` | - | Counts, inputs, clock offsets, warnings. |

## Per run (`<run>/derived/`)

* `crops/<stream>__<region>.mp4` - the operator's region cut from each video, H.264, one output
  frame per input frame: frame *i* of a crop is row *i* of `frames/<stream>_frames.csv`.
* `crops/radiometric_<cam>__<region>.npy` - float32 `[n, h, w]` deg C, same order as
  `radiometric_<cam>.csv`. The full matrices are in `radiometric_<cam>.npy`.
* `frames/<stream>_frames.csv` - host time (PC clock, Unix seconds) of every frame.
* `sync.json` - `offset_ms` per stream; content time = host_time - offset_ms/1000. The index
  ranges in `run_cycles.csv` already include this correction.
* `keyence.csv` - the IV3 pictures of the machine screen with their PC time.

## Timing

All times are on the capture PC clock. The cameras are NTP-synchronised to it. The MC6 machine
clock is not: its cycles are moved onto the PC clock with the per-day offset in
`dataset_config.json` (+/- 1 s, the export's resolution). A machine cycle starts at its
timestamp and lasts `duration_s` (the MC6 cycle time).
"""


# =========================================================================== #
# Main
# =========================================================================== #
def load_config(root):
    path = os.path.join(root, "dataset_config.json")
    cfg = read_json(path)
    if cfg is None:
        if os.path.isfile(path):
            sys.exit("dataset_config.json is not valid JSON - fix it or delete it to get the defaults")
        write_json(path, DEFAULT_CONFIG)
        log("Created %s with default settings." % path)
        cfg = dict(DEFAULT_CONFIG)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def find_sessions(root):
    out = []
    for base in (root, os.path.join(root, "sessions")):
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isfile(os.path.join(p, "metadata.json")) and os.path.isdir(os.path.join(p, "raw")):
                out.append(p)
    return out


LOCK = {"path": None, "last": 0.0}
LOCK_STALE_S = 600       # a running build refreshes its lock at least every minute


def heartbeat():
    """Keep the lock file fresh so a second build can tell a live build from a crashed one."""
    if LOCK["path"] and time.time() - LOCK["last"] > 30:
        try:
            os.utime(LOCK["path"], None)
        except OSError:
            pass
        LOCK["last"] = time.time()


class Lock(object):
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        if os.path.isfile(self.path) and time.time() - os.path.getmtime(self.path) > LOCK_STALE_S:
            log("Removing a stale lock left by an interrupted build.")
            try:
                os.remove(self.path)
            except OSError:
                pass
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ("%d %s" % (os.getpid(), time.ctime())).encode("ascii"))
            os.close(fd)
        except OSError:
            age = time.time() - os.path.getmtime(self.path)
            sys.exit("Another build is running (lock file %s, refreshed %.0f s ago). Wait for it to "
                     "finish; a lock not refreshed for %d minutes is treated as stale."
                     % (self.path, age, LOCK_STALE_S // 60))
        LOCK["path"], LOCK["last"] = self.path, time.time()
        return self

    def __exit__(self, *a):
        LOCK["path"] = None
        try:
            os.remove(self.path)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="Build / update the Aid4SME dataset")
    ap.add_argument("path", help="the data folder holding the run folders (or a single run folder)")
    ap.add_argument("--only", action="append", default=[],
                    help="process only runs whose folder name contains this text (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be rebuilt and stop")
    ap.add_argument("--force", action="store_true", help="rebuild runs even if nothing changed")
    ap.add_argument("--no-video-crops", action="store_true",
                    help="do not cut region videos (much faster; can be added later)")
    ap.add_argument("--skip-motion", action="store_true", help="no motion signal / alignment")
    ap.add_argument("--tables-only", action="store_true", help="only rebuild the dataset tables")
    ap.add_argument("--dataset-dir", default="dataset")
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--ffprobe", default=None)
    args = ap.parse_args()

    path = os.path.abspath(args.path)
    if os.path.isfile(os.path.join(path, "metadata.json")):          # a single run was given
        root, args.only = os.path.dirname(path), args.only + [os.path.basename(path)]
    else:
        root = path
    if not os.path.isdir(root):
        sys.exit("Not a folder: %s" % root)

    cfg = load_config(root)
    if args.no_video_crops:
        cfg["video_crops"] = False
    cfg["_motion"] = not args.skip_motion
    local = read_json(os.path.join(HERE, "config.local.json"), {}) or {}
    ffmpeg = args.ffmpeg or local.get("ffmpeg") or "ffmpeg"
    ffprobe = args.ffprobe or local.get("ffprobe") or "ffprobe"

    sessions = find_sessions(root)
    if not sessions:
        sys.exit("No run folders (with metadata.json and raw/) found in %s" % root)
    selected = [s for s in sessions if not args.only or any(o in os.path.basename(s) for o in args.only)]
    log("Aid4SME dataset builder %s  |  %s  |  %d runs found, %d selected"
        % (BUILDER_VERSION, root, len(sessions), len(selected)))

    if not os.path.isdir(os.path.join(root, args.dataset_dir)):
        os.makedirs(os.path.join(root, args.dataset_dir))
    with Lock(os.path.join(root, args.dataset_dir, ".build.lock")):
        ff = FF(ffmpeg, ffprobe)
        log("FFmpeg: %s%s" % (ff.version, "" if ff.has_x264 else "  (no libx264: crops use MJPEG)"))
        t_all, built, failed, skipped, incomplete = time.time(), 0, [], [], []
        if not args.tables_only:
            for i, s in enumerate(selected, 1):
                name = os.path.basename(s)
                md = read_json(os.path.join(s, "metadata.json"), {}) or {}
                status = md.get("status")
                # 'complete' / 'interrupted' runs are finished whatever their file dates say
                # (copying can reset dates); otherwise a recent change means it may be recording.
                if status == "recording" or (status not in ("complete", "interrupted", "failed", "stopped")
                                             and time.time() - newest_mtime(s) < SETTLE_S):
                    skipped.append(name)
                    log("[%d/%d] %s  still recording - skipped" % (i, len(selected), name))
                    continue
                missing = missing_parts(s, md)
                if missing:
                    incomplete.append(name)
                    log("[%d/%d] %s  incomplete on disk (missing: %s) - skipped; it is built automatically "
                        "once the files are there" % (i, len(selected), name, ", ".join(missing)))
                    continue
                try:
                    t0 = time.time()
                    if args.dry_run:
                        _, todo = build_session(ff, s, cfg, args.force, dry=True)
                        log("[%d/%d] %s  %s" % (i, len(selected), name,
                                                 ("would rebuild: " + ", ".join(todo)) if todo else "up to date"))
                        continue
                    _, todo = build_session(ff, s, cfg, args.force, dry=True)
                    if not todo:
                        log("[%d/%d] %s  up to date" % (i, len(selected), name))
                        continue
                    log("[%d/%d] %s  rebuilding: %s" % (i, len(selected), name, ", ".join(todo)))
                    build_session(ff, s, cfg, args.force)
                    built += 1
                    log("    done in %.0f s" % (time.time() - t0))
                except KeyboardInterrupt:
                    log("\nInterrupted. Finished steps are kept; run again to continue.")
                    sys.exit(1)
                except subprocess.CalledProcessError as e:
                    failed.append(name)
                    log("    FAILED: %s" % e.output.decode("utf-8", "replace")[-400:])
                except Exception as e:                                   # noqa - keep going
                    failed.append(name)
                    log("    FAILED: %s: %s" % (type(e).__name__, e))
        if args.dry_run:
            return
        log("\nDataset tables ...")
        manifest = build_tables(root, sessions, cfg, args)
        log("  %d runs (%d labelled, %d matched to a machine cycle), %d machine cycles"
            % (manifest["runs"], manifest["runs_labelled"], manifest["runs_with_machine_cycle"],
               manifest["machine_cycles"]))
        log("  regrind %%: %s" % ", ".join("%s%%: %d" % kv for kv in manifest["regrind_pct_counts"].items()))
        for w in manifest["warnings"]:
            log("  WARNING %s" % w)
        for day, c in sorted(manifest["machine_clock"].items()):
            lead = c.get("mould_open_before_next_cycle_s") or {}
            log("  machine clock %s: offset %s s (%s), %s/%s runs agree%s" % (
                day, c.get("offset_s"), c.get("source"), c.get("runs_agreeing", 0), c.get("runs_with_mould_opening", 0),
                ", mould opens %.2f s before next cycle" % lead["median"] if lead else ""))
        log("\n%d run(s) rebuilt, %d failed, %d incomplete, %d skipped while recording, in %.0f s  ->  %s"
            % (built, len(failed), len(incomplete), len(skipped), time.time() - t_all,
               os.path.join(root, args.dataset_dir)))
        if failed:
            log("Failed: %s" % ", ".join(failed))
            sys.exit(2)


if __name__ == "__main__":
    main()

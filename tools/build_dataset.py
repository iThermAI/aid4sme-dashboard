#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aid4SME - offline dataset builder.

Turns one raw session folder into aligned, ready-to-train data. Nothing is
re-encoded and nothing in raw/ is modified; everything is written to
<session>/derived/.

    python tools/build_dataset.py D:\\aid4sme_data\\sessions\\20260918_134047_1834_run023
    python tools/build_dataset.py D:\\aid4sme_data\\sessions --all --ffmpeg C:\\ffmpeg\\bin\\ffmpeg.exe

Produces, per session:
    derived/<stream>.mkv          the 60-second segments joined, stream copy
    derived/<stream>_frames.csv   frame index, timestamp in the file, host time
    derived/<stream>_motion.csv   per-frame motion signal used for alignment
    derived/radiometric_<cam>.npy float32 [n, 192, 256] in degrees C
    derived/radiometric_<cam>.csv capture time and uncertainty of every matrix
    derived/sync.json             measured offsets between all streams
    derived/telemetry.jsonl       one time-ordered log of the whole run
    derived/dataset.json          what was produced, and how to read it

Runs on the capture PC: Python 3.8, numpy and the same FFmpeg used to record.
Decoding is done at a tiny resolution, so an old laptop copes; expect a few
minutes per 5-minute run.
"""
from __future__ import print_function

import argparse
import csv
import glob
import json
import os
import re
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

try:
    import numpy as np
except ImportError:
    sys.exit("This tool needs numpy: pip install numpy==1.24.4")

from backend.isapi import extract_matrix          # noqa: E402  (after sys.path)

MOTION_W, MOTION_H = 128, 72
MAX_SHIFT_S = 2.0
GRID_MS = 5.0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def run(cmd, **kw):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, **kw)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def progress_anchor(raw_dir, name):
    """Host time at which each stream's timestamp zero occurred.

    FFmpeg reports its output position about twice a second; host_time - out_time
    is that anchor plus whatever scheduling delay the report suffered. Delay is
    always positive, so the lower envelope of the samples is the best estimate.
    """
    path = os.path.join(raw_dir, name + "_progress.csv")
    offs = []
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                if row.get("frame") and row.get("out_time_us"):
                    offs.append(float(row["host_time"]) - int(row["out_time_us"]) / 1e6)
    except (OSError, ValueError, KeyError):
        return None
    if not offs:
        return None
    offs.sort()
    return {"anchor_host_time": offs[0], "samples": len(offs),
            "spread_p05_ms": round((offs[len(offs) // 20] - offs[0]) * 1000, 1)}


def concat_segments(raw_dir, name, out_path, ffmpeg, force=False):
    segs = sorted(glob.glob(os.path.join(raw_dir, name + "_*.mkv")))
    if not segs:
        return None, 0
    if os.path.isfile(out_path) and not force:
        return out_path, len(segs)
    listing = out_path + ".txt"
    with open(listing, "w", encoding="utf-8") as f:
        for s in segs:
            f.write("file '%s'\n" % s.replace("\\", "/").replace("'", "'\\''"))
    run([ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", listing, "-c", "copy", "-fflags", "+genpts", out_path])
    os.remove(listing)
    return out_path, len(segs)


def frame_times(ffprobe, path):
    """Timestamp of every frame in the file, in seconds, in order."""
    out = run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "packet=pts_time,dts_time", "-of", "csv=p=0", path]).decode("utf-8", "replace")
    times = []
    for line in out.splitlines():
        parts = line.strip().split(",")
        for p in parts:
            if p not in ("", "N/A"):
                times.append(float(p))
                break
    return times


def motion_signal(ffmpeg, path):
    """Mean absolute difference between consecutive frames, decoded tiny.

    This is the signal the alignment uses: mould open, ejection and close are
    sharp shared events that every camera sees at the same instant.
    """
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", path,
           "-an", "-vf", "scale=%d:%d,format=gray" % (MOTION_W, MOTION_H),
           "-f", "rawvideo", "-"]
    size = MOTION_W * MOTION_H
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    prev, out = None, []
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        cur = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
        out.append(0.0 if prev is None else float(np.abs(cur - prev).mean()))
        prev = cur
    proc.stdout.close()
    proc.wait()
    return np.array(out, dtype=np.float32)


# --------------------------------------------------------------------------- #
# Cross-correlation
# --------------------------------------------------------------------------- #
def resample(times, values, grid):
    if len(times) < 2:
        return None
    return np.interp(grid, times, values)


def normalise(x):
    x = x - x.mean()
    s = x.std()
    return x / s if s > 1e-9 else x


def cross_correlate(ref, sig, dt_s):
    """Offset of sig relative to ref, in seconds, positive = sig is later.
    Returns (offset_s, peak_quality 0-1)."""
    a, b = normalise(ref), normalise(sig)
    n = int(round(MAX_SHIFT_S / dt_s))
    full = np.correlate(a, b, "full") / len(a)
    centre = len(b) - 1
    lo, hi = max(centre - n, 0), min(centre + n + 1, len(full))
    window = full[lo:hi]
    k = int(np.argmax(window))
    peak = float(window[k])
    # parabolic interpolation around the peak for sub-sample resolution
    shift = k + lo - centre
    if 0 < k < len(window) - 1:
        y0, y1, y2 = window[k - 1], window[k], window[k + 1]
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-12:
            shift += 0.5 * (y0 - y2) / denom
    return -shift * dt_s, peak


def align_streams(signals, reference):
    """signals: {stream: (host_times, values)}. Returns offsets in ms vs reference."""
    have = {k: v for k, v in signals.items() if v and len(v[0]) > 10}
    if reference not in have:
        return {}, "reference stream has no usable motion signal"
    dt = GRID_MS / 1000.0
    t0 = max(v[0][0] for v in have.values())
    t1 = min(v[0][-1] for v in have.values())
    if t1 - t0 < 5:
        return {}, "streams overlap for less than 5 s"
    grid = np.arange(t0, t1, dt)
    grids = {k: resample(v[0], v[1], grid) for k, v in have.items()}
    ref = grids[reference]
    out = {}
    for name, sig in grids.items():
        if name == reference:
            out[name] = {"offset_ms": 0.0, "quality": 1.0}
            continue
        off, q = cross_correlate(ref, sig, dt)
        out[name] = {"offset_ms": round(off * 1000, 1), "quality": round(q, 3)}
    return out, None


# --------------------------------------------------------------------------- #
# Radiometric
# --------------------------------------------------------------------------- #
def build_radiometric(raw_dir, cam, out_dir, sensor):
    src = os.path.join(raw_dir, "radiometric_%s" % cam)
    index = os.path.join(src, "index.csv")
    if not os.path.isfile(index):
        return None
    rows, mats = [], []
    with open(index) as f:
        for r in csv.DictReader(f):
            if r.get("status") != "200" or not r.get("file"):
                continue
            path = os.path.join(src, r["file"])
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                body = fh.read()
            try:
                w, h, data = extract_matrix("multipart/form-data; boundary=boundary", body,
                                            sensor[0], sensor[1])
            except Exception as e:                                  # noqa - report and skip
                rows.append({"seq": r["seq"], "error": str(e)[:80]})
                continue
            arr = np.frombuffer(data, dtype="<f4").reshape(h, w)
            t_send, t_hdr = float(r["t_send"]), float(r["t_hdr"])
            mats.append(arr)
            rows.append({
                "seq": int(r["seq"]), "index": len(mats) - 1,
                # The camera sends no capture time, so the instant lies between the
                # request leaving and the first response byte arriving.
                "host_time": round((t_send + t_hdr) / 2, 6),
                "uncertainty_ms": round((t_hdr - t_send) * 1000 / 2, 1),
                "tmin_c": round(float(arr.min()), 2), "tmax_c": round(float(arr.max()), 2),
                "tmean_c": round(float(arr.mean()), 2),
                "freeze": r.get("freeze", ""), "duplicate": r.get("dup", ""), "file": r["file"]})
    if not mats:
        return None
    stack = np.stack(mats).astype("float32")
    npy = os.path.join(out_dir, "radiometric_%s.npy" % cam)
    np.save(npy, stack)
    fields = ["seq", "index", "host_time", "uncertainty_ms", "tmin_c", "tmax_c", "tmean_c",
              "freeze", "duplicate", "file", "error"]
    with open(os.path.join(out_dir, "radiometric_%s.csv" % cam), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    good = [r for r in rows if "index" in r]
    return {"file": os.path.basename(npy), "shape": list(stack.shape),
            "matrices": len(good), "failed": len(rows) - len(good),
            "duplicates": sum(1 for r in good if r.get("duplicate") == "1"),
            "first_host_time": good[0]["host_time"], "last_host_time": good[-1]["host_time"],
            "median_uncertainty_ms": float(np.median([r["uncertainty_ms"] for r in good])),
            "tmax_c": max(r["tmax_c"] for r in good)}


# --------------------------------------------------------------------------- #
# One session
# --------------------------------------------------------------------------- #
def build(session, args):
    raw = os.path.join(session, "raw")
    out = os.path.join(session, args.out)
    os.makedirs(out, exist_ok=True)
    md = read_json(os.path.join(session, "metadata.json"), {})
    ver = read_json(os.path.join(session, "verification.json"), {})
    streams = md.get("streams") or {}
    sensor = tuple((md.get("radiometric") or {}).get("sensor") or (256, 192))
    print("\n=== %s" % os.path.basename(session))

    report = {"session_id": md.get("session_id"), "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "video": {}, "radiometric": {}}
    signals = {}

    for name in sorted(streams):
        t0 = time.time()
        mkv = os.path.join(out, name + ".mkv")
        joined, nseg = concat_segments(raw, name, mkv, args.ffmpeg, args.force)
        if not joined:
            print("  %-14s no segments" % name)
            continue
        anchor = progress_anchor(raw, name)
        pts = frame_times(args.ffprobe, joined)
        host = [round(anchor["anchor_host_time"] + p, 6) for p in pts] if anchor else []
        with open(os.path.join(out, name + "_frames.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame", "pts_s", "host_time"])
            for i, p in enumerate(pts):
                w.writerow([i, "%.6f" % p, "%.6f" % host[i] if host else ""])

        motion = None
        if not args.skip_motion:
            motion = motion_signal(args.ffmpeg, joined)
            with open(os.path.join(out, name + "_motion.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["frame", "host_time", "motion"])
                for i, m in enumerate(motion):
                    w.writerow([i, "%.6f" % host[i] if i < len(host) else "", "%.4f" % m])
            if host and len(motion) > 10:
                n = min(len(host), len(motion))
                signals[name] = (np.array(host[:n]), np.array(motion[:n]))

        report["video"][name] = {
            "file": os.path.basename(joined), "segments": nseg, "frames": len(pts),
            "duration_s": round(pts[-1] - pts[0], 2) if len(pts) > 1 else 0,
            "anchor_host_time": anchor["anchor_host_time"] if anchor else None,
            "anchor_spread_p05_ms": anchor["spread_p05_ms"] if anchor else None,
            "motion_frames": int(len(motion)) if motion is not None else 0}
        print("  %-14s %5d frames, %2d segments, %.0fs  (%.0fs)"
              % (name, len(pts), nseg, report["video"][name]["duration_s"], time.time() - t0))

    if not args.keep_joined:
        for name in report["video"]:
            path = os.path.join(out, name + ".mkv")
            if os.path.isfile(path):
                os.remove(path)          # the 60-second segments in raw/ remain untouched
            report["video"][name]["file"] = None

    for cam in sorted(set(s.get("camera") for s in streams.values() if s.get("camera"))):
        rad = build_radiometric(raw, cam, out, sensor)
        if rad:
            report["radiometric"][cam] = rad
            print("  radiometric %-3s %d matrices %s, median uncertainty %.0f ms, max %.1f C"
                  % (cam, rad["matrices"], rad["shape"], rad["median_uncertainty_ms"], rad["tmax_c"]))

    # ---- alignment --------------------------------------------------------- #
    reference = args.reference if args.reference in signals else (sorted(signals)[0] if signals else None)
    offsets, problem = ({}, "no motion signals") if not reference else align_streams(signals, reference)
    arrival = ver.get("start_offsets_ms_vs_cam1_optical") or {}
    sync = {
        "reference": reference,
        "method": "scene cross-correlation of the per-frame motion signal",
        "grid_ms": GRID_MS,
        "note": ("Offset is how much later a stream's content is than the reference. "
                 "Subtract it from that stream's host times to put all streams on one timeline. "
                 "Unlike the arrival estimate, this includes each camera's own delay."),
        "streams": {}, "problem": problem}
    for name, r in sorted(offsets.items()):
        a = arrival.get(name)
        sync["streams"][name] = {
            "offset_ms": r["offset_ms"], "correlation": r["quality"],
            "arrival_estimate_ms": a,
            "difference_vs_arrival_ms": None if a is None else round(r["offset_ms"] - a, 1),
            "trust": "low" if r["quality"] < 0.3 else "medium" if r["quality"] < 0.6 else "high"}
    for cam, rad in report["radiometric"].items():
        sync["streams"]["%s_radiometric" % cam] = {
            "offset_ms": None, "method": "arrival midpoint, see radiometric_<cam>.csv",
            "median_uncertainty_ms": round(rad["median_uncertainty_ms"], 1), "trust": "medium"}
    write_json(os.path.join(out, "sync.json"), sync)
    report["sync"] = sync

    # ---- telemetry ---------------------------------------------------------- #
    entries = []
    for line in open(os.path.join(session, "events.jsonl"), encoding="utf-8") if \
            os.path.isfile(os.path.join(session, "events.jsonl")) else []:
        try:
            e = json.loads(line)
            entries.append({"host_time": e.get("t"), "kind": "event", "data": e})
        except ValueError:
            pass
    for note in md.get("operator_notes_during_run") or []:
        entries.append({"host_time": note.get("t"), "kind": "note", "data": note})
    for cam in report["radiometric"]:
        with open(os.path.join(out, "radiometric_%s.csv" % cam)) as f:
            for r in csv.DictReader(f):
                if r.get("host_time"):
                    entries.append({"host_time": float(r["host_time"]), "kind": "matrix",
                                    "data": {"camera": cam, "index": r["index"], "tmax_c": r["tmax_c"],
                                             "uncertainty_ms": r["uncertainty_ms"]}})
    entries = [e for e in entries if e.get("host_time")]
    entries.sort(key=lambda e: e["host_time"])
    with open(os.path.join(out, "telemetry.jsonl"), "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    report["telemetry_entries"] = len(entries)

    write_json(os.path.join(out, "dataset.json"), report)
    print("  alignment (reference %s):" % reference)
    for name, r in sorted(sync["streams"].items()):
        if r.get("offset_ms") is None:
            print("     %-22s arrival midpoint, +/- %.0f ms" % (name, r["median_uncertainty_ms"]))
        else:
            print("     %-22s %+8.1f ms  correlation %.2f (%s)   arrival estimate %s ms"
                  % (name, r["offset_ms"], r["correlation"], r["trust"], r["arrival_estimate_ms"]))
    if problem:
        print("  alignment not measured: %s" % problem)
    print("  -> %s" % out)
    return report


def main():
    ap = argparse.ArgumentParser(description="Build aligned data from raw Aid4SME sessions")
    ap.add_argument("path", help="a session folder, or the sessions folder with --all")
    ap.add_argument("--all", action="store_true", help="process every session inside path")
    ap.add_argument("--out", default="derived")
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--ffprobe", default=None)
    ap.add_argument("--reference", default="cam1_optical")
    ap.add_argument("--skip-motion", action="store_true", help="no alignment; much faster")
    ap.add_argument("--force", action="store_true", help="rebuild joined video files")
    ap.add_argument("--keep-joined", action="store_true",
                    help="keep derived/<stream>.mkv (doubles disk use; the raw segments are kept either way)")
    args = ap.parse_args()

    cfg = read_json(os.path.join(HERE, "config.local.json"), {}) or {}
    args.ffmpeg = args.ffmpeg or cfg.get("ffmpeg", "ffmpeg")
    args.ffprobe = args.ffprobe or cfg.get("ffprobe", "ffprobe")
    for exe in (args.ffmpeg, args.ffprobe):
        try:
            run([exe, "-version"])
        except (OSError, subprocess.CalledProcessError):
            sys.exit("Not found: %s  (use --ffmpeg / --ffprobe)" % exe)

    if args.all:
        sessions = [os.path.join(args.path, d) for d in sorted(os.listdir(args.path))
                    if os.path.isfile(os.path.join(args.path, d, "metadata.json"))]
    else:
        sessions = [args.path]
    if not sessions:
        sys.exit("No sessions found in %s" % args.path)

    t0 = time.time()
    done = 0
    for s in sessions:
        try:
            build(s, args)
            done += 1
        except subprocess.CalledProcessError as e:
            print("  FAILED: %s" % e.output.decode("utf-8", "replace")[:300])
        except Exception as e:                                       # noqa - keep going
            print("  FAILED: %s: %s" % (type(e).__name__, e))
    print("\n%d of %d sessions built in %.0f s" % (done, len(sessions), time.time() - t0))


if __name__ == "__main__":
    main()

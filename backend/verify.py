"""Post-stop verification of a raw session (runs in a few seconds).

Video: packets per stream via ffprobe, compared with the segment span written
by FFmpeg (detects frames dropped at the source) and with the wall-clock
recording time (detects late start / early death). FFmpeg warnings are counted.

Timing: from <stream>_progress.csv, offset = host_time - out_time for every
progress report. The lower envelope (min) estimates the host time at which the
stream's PTS 0 was captured, plus that stream's minimum pipeline latency. The
difference between streams is a first, clock-free estimate of their relative
start offset. It does not replace scene cross-correlation; its uncertainty is
reported alongside.

Radiometric: summary of index.csv (rate, RTT, TTFB/2 uncertainty, freezes).
"""
import csv
import glob
import json
import os
import statistics
import subprocess

from . import winutil


def pct(values, q):
    s = sorted(values)
    if not s:
        return None
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def describe(values, nd=2):
    if not values:
        return {}
    return {"median": round(statistics.median(values), nd), "p95": round(pct(values, 0.95), nd),
            "max": round(max(values), nd), "min": round(min(values), nd),
            "stdev": round(statistics.pstdev(values), nd)}


def probe(ffprobe, path):
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-count_packets", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_packets,codec_name,width,height:format=start_time,duration",
             "-of", "json", path], stderr=subprocess.STDOUT, timeout=120,
            creationflags=winutil.CREATE_NO_WINDOW)
        d = json.loads(out.decode("utf-8", "replace"))
        s = (d.get("streams") or [{}])[0]
        f = d.get("format") or {}
        return {"packets": int(s.get("nb_read_packets") or 0), "codec": s.get("codec_name"),
                "width": s.get("width"), "height": s.get("height"),
                "start": float(f.get("start_time") or 0), "end": float(f.get("duration") or 0)}
    except Exception as e:  # noqa
        return {"packets": 0, "error": str(e)[:200]}


def segment_spans(raw_dir, name):
    path = os.path.join(raw_dir, name + "_segments.csv")
    spans = {}
    if os.path.isfile(path):
        with open(path) as f:
            for row in csv.reader(f):
                if len(row) >= 3:
                    try:
                        spans[os.path.basename(row[0])] = float(row[2]) - float(row[1])
                    except ValueError:
                        pass
    return spans


def progress_anchor(raw_dir, name):
    path = os.path.join(raw_dir, name + "_progress.csv")
    offs, pts = [], []
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                t, out_us, frame = float(row["host_time"]), int(row["out_time_us"]), int(row["frame"] or 0)
            except (ValueError, TypeError, KeyError):
                continue
            if frame > 0 and out_us > 0:
                offs.append(t - out_us / 1e6)
                pts.append((out_us / 1e6, t))
    if len(offs) < 3:
        return None
    # Least-squares slope of host time vs stream time: camera clock rate vs host clock.
    mx = statistics.mean(p for p, _ in pts)
    my = statistics.mean(t for _, t in pts)
    sxx = sum((p - mx) ** 2 for p, _ in pts)
    slope = sum((p - mx) * (t - my) for p, t in pts) / sxx if sxx else 1.0
    lo = min(offs)
    return {"samples": len(offs), "pts0_host_time_min": round(lo, 4),
            "pts0_host_time_median": round(statistics.median(offs), 4),
            "jitter_ms": describe([(o - lo) * 1000 for o in offs], 1),
            "clock_rate_ppm": round((slope - 1.0) * 1e6, 1)}


def verify_video(raw_dir, name, ffprobe, fps, wall_s, exit_how, had_stall):
    segs = sorted(glob.glob(os.path.join(raw_dir, name + "_*.mkv")))
    spans = segment_spans(raw_dir, name)
    packets, span, info = 0, 0.0, {}
    for seg in segs:
        p = probe(ffprobe, seg)
        packets += p.get("packets", 0)
        info = info or p
        base = os.path.basename(seg)
        if base in spans:
            span += spans[base]
        elif p.get("packets"):
            span += p["packets"] / fps           # segment missing from list (hard stop)
    log_path = os.path.join(raw_dir, name + "_ffmpeg.log")
    warnings = []
    if os.path.isfile(log_path):
        with open(log_path, "rb") as f:
            warnings = [l.decode("utf-8", "replace").strip() for l in f if l.strip()]
    ratio_span = packets / (span * fps) if span else 0.0
    missing_vs_wall = max(0.0, wall_s * fps - packets)
    # Allow up to 3 s at the start (RTSP setup + first keyframe) before calling it a loss.
    ok = (packets > 0 and ratio_span >= 0.99 and missing_vs_wall <= 3 * fps + 0.01 * wall_s * fps
          and exit_how == "graceful" and not had_stall)
    return {"stream": name, "pass": ok, "segments": len(segs), "packets": packets,
            "span_s": round(span, 2), "ratio_vs_span": round(ratio_span, 4),
            "start_delay_s": round(missing_vs_wall / fps, 2),
            "codec": info.get("codec"), "resolution": "%sx%s" % (info.get("width"), info.get("height")),
            "mb": round(sum(os.path.getsize(s) for s in segs) / 1e6, 1),
            "stop": exit_how, "stalled_during_run": had_stall,
            "ffmpeg_warnings": len(warnings), "ffmpeg_warning_sample": warnings[:3],
            "timing": progress_anchor(raw_dir, name)}


def verify_radiometric(rad_dir, name, rate_hz):
    path = os.path.join(rad_dir, "index.csv")
    rows = []
    if os.path.isfile(path):
        with open(path) as f:
            rows = [r for r in csv.DictReader(f) if r["seq"] != "0"]      # first poll = warm-up
    ok = [r for r in rows if r["status"] == "200" and r["p2p_ok"] == "1"]
    out = {"stream": name, "polls": len(rows), "ok": len(ok), "failed": len(rows) - len(ok)}
    if len(ok) >= 2:
        t = [float(r["t_recv"]) for r in ok]
        span = t[-1] - t[0]
        uniq = [r for r in ok if r["dup"] != "1"]
        out["unique_matrices"] = len(uniq)
        out["unique_fps"] = round(max(len(uniq) - 1, 0) / span, 3) if span > 0 else 0.0
        out["rtt_ms"] = describe([float(r["rtt_ms"]) for r in ok])
        out["capture_uncertainty_ms"] = describe([float(r["ttfb_ms"]) / 2 for r in ok])
        out["freeze_frames"] = sum(1 for r in ok if r["freeze"] == "1")
        out["saturated_frames"] = sum(1 for r in ok if r["saturated"] == "1")
        tmax = [float(r["tmax"]) for r in ok if r["tmax"]]
        out["tmax_c"] = round(max(tmax), 2) if tmax else None
        out["overruns"] = sum(1 for r in rows if r["overrun"] == "1")
    fps = out.get("unique_fps", 0.0)
    out["pass"] = bool(ok) and fps >= 0.9 * rate_hz and out["failed"] <= max(1, 0.01 * len(rows))
    return out


def relative_offsets(video_results, reference):
    ref = next((v["timing"] for v in video_results if v["stream"] == reference and v["timing"]), None)
    if not ref:
        return {}
    out = {}
    for v in video_results:
        if v["timing"]:
            out[v["stream"]] = round((v["timing"]["pts0_host_time_min"] - ref["pts0_host_time_min"]) * 1000, 1)
    return out

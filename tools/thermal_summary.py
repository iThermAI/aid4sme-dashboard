#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aid4SME - thermal summary per run, from an already built dataset.

For every run it takes the first radiometric matrix 1-5 s after the mould opened
(runs.csv: mould_open_pc) and reports temperature statistics inside each
radiometric region crop of cam1 and cam2. Writes <data>/dataset/thermal_at_open.csv.

    python tools\\thermal_summary.py C:\\aid4sme_data

Needs only Python 3.8+ and numpy; reads derived/ files, never raw/.
"""
from __future__ import print_function

import csv
import datetime
import glob
import io
import os
import sys

import numpy as np

WINDOW = (1.0, 5.0)     # seconds after mould opening


def read_csv(path):
    try:
        with io.open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (IOError, OSError):
        return []


def to_epoch(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/thermal_summary.py <data folder>")
    root = os.path.abspath(sys.argv[1])
    runs = read_csv(os.path.join(root, "dataset", "runs.csv"))
    if not runs:
        sys.exit("dataset/runs.csv not found - run tools/build_dataset.py first")
    out, done = [], 0
    for r in runs:
        d = os.path.join(root, r["folder"], "derived")
        t_open = to_epoch(r.get("mould_open_pc"))
        row = {"run_id": r["run_id"], "run": r["run"], "regrind_pct": r.get("regrind_pct", ""),
               "batch_id": r.get("batch_id", ""), "position_in_batch": r.get("position_in_batch", ""),
               "out_of_material": r.get("out_of_material", ""), "ejected_cycle_uid": r.get("ejected_cycle_uid", ""),
               "mould_open_pc": r.get("mould_open_pc", "")}
        for cam in ("cam1", "cam2"):
            rows = [x for x in read_csv(os.path.join(d, "radiometric_%s.csv" % cam)) if x.get("index") not in (None, "")]
            crops = sorted(glob.glob(os.path.join(d, "crops", "radiometric_%s__*.npy" % cam)))
            if not rows or not crops:
                continue
            arr = np.load(crops[0], mmap_mode="r")          # first region of that camera
            times = np.array([float(x["host_time"]) for x in rows])
            idx = np.array([int(x["index"]) for x in rows])
            # whole-run: hottest 1 % of the region, per matrix -> max and median over the run
            p99_all = [float(np.percentile(arr[i], 99)) for i in idx if i < len(arr)]
            if p99_all:
                row[cam + "_run_p99_max"] = round(max(p99_all), 2)
                row[cam + "_run_p99_median"] = round(float(np.median(p99_all)), 2)
            if t_open is None:
                continue
            sel = np.where((times >= t_open + WINDOW[0]) & (times <= t_open + WINDOW[1]))[0]
            if not len(sel) or idx[sel[0]] >= len(arr):
                continue
            k = sel[0]
            m = np.asarray(arr[idx[k]], dtype=np.float32)
            row.update({
                cam + "_s_after_open": round(float(times[k] - t_open), 2),
                cam + "_matrix_index": int(idx[k]),
                cam + "_p99": round(float(np.percentile(m, 99)), 2),
                cam + "_p90": round(float(np.percentile(m, 90)), 2),
                cam + "_mean": round(float(m.mean()), 2),
                cam + "_max": round(float(m.max()), 2),
                cam + "_frac_above_60c": round(float((m > 60).mean()), 4),
                cam + "_region": os.path.basename(crops[0])})
        if "cam1_p99" in row:
            done += 1
        out.append(row)
    keys = []
    for r in out:
        for k in r:
            if k not in keys:
                keys.append(k)
    path = os.path.join(root, "dataset", "thermal_at_open.csv")
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print("%d runs, %d with a cam1 matrix %.0f-%.0f s after mould opening -> %s"
          % (len(out), done, WINDOW[0], WINDOW[1], path))


if __name__ == "__main__":
    main()

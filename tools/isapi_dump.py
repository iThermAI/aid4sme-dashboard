#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only dump of a HIKMICRO / Hikvision camera's ISAPI settings.

Sends only GET requests; nothing on the camera is changed. The result is a
folder and a .zip with one file per endpoint plus summary.txt, used to map the
exact setting names of a firmware version (palette, AGC, distance, ...).

    python tools/isapi_dump.py 192.168.1.30 --password XXXXX
    python tools/isapi_dump.py 192.168.1.30 --user admin --password XXXXX --out dumps

The files contain the device model, serial number and settings, but no
passwords. Network and user-account endpoints are deliberately not read.
"""
from __future__ import print_function

import argparse
import os
import re
import shutil
import sys
import time

try:
    import requests
    from requests.auth import HTTPDigestAuth
except ImportError:
    sys.exit("This tool needs the 'requests' package: pip install requests")

ENDPOINTS = [
    # System
    "/ISAPI/System/deviceInfo",
    "/ISAPI/System/capabilities",
    "/ISAPI/System/time",
    "/ISAPI/System/time/capabilities",
    "/ISAPI/System/time/ntpServers",
    "/ISAPI/System/time/ntpServers/capabilities",
    "/ISAPI/System/Video/inputs/channels",
    # Streaming
    "/ISAPI/Streaming/channels",
    "/ISAPI/Streaming/channels/101/capabilities",
    "/ISAPI/Streaming/channels/102",
    "/ISAPI/Streaming/channels/201/capabilities",
    "/ISAPI/Streaming/channels/202",
    # Image
    "/ISAPI/Image/channels",
    # Thermal
    "/ISAPI/Thermal/capabilities",
    "/ISAPI/Thermal/channels",
    "/ISAPI/Thermal/channels/{t}/thermometry",
    "/ISAPI/Thermal/channels/{t}/thermometry/capabilities",
    "/ISAPI/Thermal/channels/{t}/thermometry/basicParam",
    "/ISAPI/Thermal/channels/{t}/thermometry/basicParam/capabilities",
    "/ISAPI/Thermal/channels/{t}/thermometry/1",
    "/ISAPI/Thermal/channels/{t}/thermometry/pixelToPixelParam",
    "/ISAPI/Thermal/channels/{t}/thermometry/pixelToPixelParam/capabilities",
    "/ISAPI/Thermal/channels/{t}/thermometryMode",
    "/ISAPI/Thermal/channels/{t}/thermometryMode/capabilities",
    "/ISAPI/Thermal/channels/{t}/thermometry/jpegPicWithAppendData/capabilities",
    "/ISAPI/Thermal/channels/{t}/bispectralParam",
    "/ISAPI/Thermal/channels/{t}/imageEnhancement",
    "/ISAPI/Thermal/channels/{t}/tempRangeParam",
]
# Read for both video input channels (1 = optical, 2 = thermal).
PER_CHANNEL = [
    "/ISAPI/Streaming/channels/{c}01",
    "/ISAPI/System/Video/inputs/channels/{c}",
    "/ISAPI/System/Video/inputs/channels/{c}/overlays",
    "/ISAPI/System/Video/inputs/channels/{c}/overlays/capabilities",
    "/ISAPI/Image/channels/{c}",
    "/ISAPI/Image/channels/{c}/capabilities",
    "/ISAPI/Image/channels/{c}/Palettes",
    "/ISAPI/Image/channels/{c}/Palettes/capabilities",
    "/ISAPI/Image/channels/{c}/ImageEnhancement",
    "/ISAPI/Image/channels/{c}/imageEnhancement",
    "/ISAPI/Image/channels/{c}/DDE",
    "/ISAPI/Image/channels/{c}/AGC",
    "/ISAPI/Image/channels/{c}/thermalAGC",
    "/ISAPI/Image/channels/{c}/ISPMode",
    "/ISAPI/Image/channels/{c}/imageMode",
    "/ISAPI/Image/channels/{c}/BispectralParam",
    "/ISAPI/Image/channels/{c}/bispectral",
    "/ISAPI/Image/channels/{c}/shutter",
    "/ISAPI/Image/channels/{c}/FFC",
    "/ISAPI/Image/channels/{c}/ManualShutterCorrect/capabilities",
    "/ISAPI/Image/channels/{c}/manualShutterCorrect/capabilities",
    "/ISAPI/Image/channels/{c}/noiseReduce",
    "/ISAPI/Image/channels/{c}/digitalZoom",
]


def safe_name(path):
    return re.sub(r"[^A-Za-z0-9]+", "_", path.strip("/"))[:120]


def main():
    ap = argparse.ArgumentParser(description="Read-only ISAPI settings dump")
    ap.add_argument("ip")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--thermal-channel", default="2")
    ap.add_argument("--out", default="isapi_dumps")
    ap.add_argument("--timeout", type=float, default=6.0)
    a = ap.parse_args()

    folder = os.path.join(a.out, "%s_%s" % (a.ip.replace(".", "_").replace(":", "_"), time.strftime("%Y%m%d_%H%M%S")))
    os.makedirs(folder)
    s = requests.Session()
    s.auth = HTTPDigestAuth(a.user, a.password)

    paths = [p.replace("{t}", a.thermal_channel) for p in ENDPOINTS]
    for c in ("1", "2"):
        paths += [p.replace("{c}", c) for p in PER_CHANNEL]

    lines = []
    ok = 0
    for i, path in enumerate(paths, 1):
        try:
            r = s.get("http://%s%s" % (a.ip, path), timeout=a.timeout)
            status, body = r.status_code, r.content
        except requests.RequestException as e:
            status, body = -1, type(e).__name__.encode()
        if status == 401:
            print("401 Unauthorized - check the user name and password. Stopping.")
            break
        ext = "json" if body.lstrip()[:1] == b"{" else "xml"
        fn = "%03d_%s_%s.%s" % (i, "OK" if status == 200 else "HTTP%s" % status, safe_name(path), ext)
        with open(os.path.join(folder, fn), "wb") as f:
            f.write(body)
        ok += status == 200
        lines.append("%-4s %s" % (status, path))
        print("  %-4s %s" % (status, path))

    with open(os.path.join(folder, "summary.txt"), "w") as f:
        f.write("camera %s, %d of %d endpoints answered, %s\n\n" % (a.ip, ok, len(lines), time.ctime()))
        f.write("\n".join(lines) + "\n")
    archive = shutil.make_archive(folder, "zip", folder)
    print("\n%d of %d endpoints answered." % (ok, len(lines)))
    print("Send this file: %s" % os.path.abspath(archive))


if __name__ == "__main__":
    main()

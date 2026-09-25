#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aid4SME - minimal Keyence IV3 test: trigger over TCP, receive over FTP.

This is the whole Keyence path in one file, with nothing else around it: the
same two things the dashboard does. Use it to prove the camera and the network
work before blaming the dashboard.

    python tools/keyence_mwe.py --ip 192.168.1.40
    python tools/keyence_mwe.py --ip 192.168.1.40 --count 5 --interval 3
    python tools/keyence_mwe.py --ip 192.168.1.40 --no-trigger   # FTP only

Close the IV3 Navigator software first: while it is connected the sensor is in
setup mode and refuses trigger commands. The sensor must be in Run mode, and its
image output must be set to FTP, pointing at this PC on --ftp-port with the same
user and password.

Files are written to ./keyence_test/. Needs: pip install pyftpdlib
"""
from __future__ import print_function

import argparse
import os
import socket
import sys
import threading
import time

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    sys.exit("This test needs pyftpdlib: pip install pyftpdlib")

received = []
lock = threading.Lock()
t0 = time.time()


def stamp():
    return "%7.3fs" % (time.time() - t0)


def local_addresses():
    """Addresses this PC can be reached on, to check against the camera's FTP setting."""
    out = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))            # no packet is sent; this just picks the route
        out.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            out.add(info[4][0])
    except socket.gaierror:
        pass
    return sorted(a for a in out if not a.startswith("127."))


def start_ftp(folder, port, user, password, passive):
    class Handler(FTPHandler):
        def on_connect(self):
            print("%s FTP   camera connected from %s" % (stamp(), self.remote_ip))

        def on_login(self, username):
            print("%s FTP   logged in as '%s'" % (stamp(), username))

        def on_file_received(self, path):
            size = os.path.getsize(path)
            with lock:
                received.append((time.time(), path, size))
            print("%s FILE  %s  (%d bytes)" % (stamp(), os.path.relpath(path, folder), size))

        def on_incomplete_file_received(self, path):
            print("%s FILE  INCOMPLETE transfer: %s" % (stamp(), os.path.relpath(path, folder)))

    auth = DummyAuthorizer()
    auth.add_user(user, password, folder, perm="elradfmw")
    Handler.authorizer = auth
    Handler.banner = "Aid4SME IV3 test"
    Handler.passive_ports = range(passive[0], passive[1] + 1)
    server = FTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=server.serve_forever, kwargs={"timeout": 0.5, "blocking": True})
    t.daemon = True
    t.start()
    return server


def main():
    ap = argparse.ArgumentParser(description="Minimal Keyence IV3 trigger + FTP test")
    ap.add_argument("--ip", required=True, help="IV3 address, e.g. 192.168.1.40")
    ap.add_argument("--port", type=int, default=8500, help="command port (NOT 63000, that is the IV3 software)")
    ap.add_argument("--count", type=int, default=3, help="how many pictures to take")
    ap.add_argument("--interval", type=float, default=3.0, help="seconds between triggers")
    ap.add_argument("--wait", type=float, default=5.0, help="seconds to wait for the last transfer")
    ap.add_argument("--folder", default="keyence_test")
    ap.add_argument("--ftp-port", type=int, default=2121)
    ap.add_argument("--ftp-user", default="ftpuser")
    ap.add_argument("--ftp-pass", default="ftppass")
    ap.add_argument("--passive", default="2130-2140", help="passive port range, must be open in the firewall")
    ap.add_argument("--no-trigger", action="store_true", help="only run the FTP server and wait")
    ap.add_argument("--command", default="T1", help="trigger command to send")
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.passive.split("-"))
    folder = os.path.abspath(args.folder)
    os.makedirs(folder, exist_ok=True)

    print("Receiving into : %s" % folder)
    print("FTP server     : port %d, user '%s', passive %d-%d" % (args.ftp_port, args.ftp_user, lo, hi))
    print("This PC        : %s" % (", ".join(local_addresses()) or "unknown"))
    print("                 the camera's FTP setting must point at one of these addresses")
    print("Camera         : %s:%d\n" % (args.ip, args.port))
    start_ftp(folder, args.ftp_port, args.ftp_user, args.ftp_pass, (lo, hi))

    sock = None
    if not args.no_trigger:
        try:
            sock = socket.create_connection((args.ip, args.port), 5)
            sock.settimeout(5)
            print("%s TCP   connected to the camera" % stamp())
        except OSError as e:
            print("%s TCP   cannot connect: %s" % (stamp(), e))
            print("\nThe command port is not answering. Close the IV3 Navigator software, check that")
            print("command communication is enabled on the sensor, and confirm the port number.")
            return

    triggers = 0
    errors = []
    try:
        for i in range(args.count if not args.no_trigger else 0):
            t_send = time.time()
            sock.sendall((args.command + "\r").encode("ascii"))
            try:
                resp = sock.recv(256).decode("ascii", "replace").strip()
            except socket.timeout:
                resp = "(no answer within 5 s)"
            ms = (time.time() - t_send) * 1000
            triggers += 1
            print("%s TRIG  %s -> %-14s (%.0f ms)" % (stamp(), args.command, resp, ms))
            if resp.startswith("ER"):
                errors.append(resp)
            if i < args.count - 1:
                time.sleep(args.interval)
        deadline = time.time() + args.wait
        while time.time() < deadline:
            time.sleep(0.25)
        if args.no_trigger:
            print("%s Waiting for the camera to push files. Ctrl+C to stop." % stamp())
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if sock:
            sock.close()

    images = [r for r in received if r[1].lower().endswith((".jpg", ".jpeg", ".bmp", ".png"))]
    print("\n---------------- result ----------------")
    print("triggers sent      : %d" % triggers)
    print("camera errors      : %s" % (", ".join(sorted(set(errors))) if errors else "none"))
    print("files received     : %d (%d images)" % (len(received), len(images)))
    if images:
        delays = [r[0] - t0 for r in images]
        print("first image after  : %.1f s" % delays[0])
        print("\nWorking. The dashboard does exactly this; set keyence.mode to \"iv3\".")
    elif errors:
        print("\nThe camera refuses the trigger command (%s)." % errors[0])
        print("Close the IV3 Navigator software, put the sensor in Run mode, and check the error")
        print("code in the IV3 manual. No picture is taken until the command is accepted.")
    elif triggers:
        print("\nThe camera accepts the trigger but no file arrives. Check, in this order:")
        print("  1. the camera's image output is set to FTP, not SD card or off")
        print("  2. its FTP address is this PC and its port is %d" % args.ftp_port)
        print("  3. its FTP user and password are '%s' / '%s'" % (args.ftp_user, args.ftp_pass))
        print("  4. Windows firewall allows incoming TCP on %d and %d-%d" % (args.ftp_port, lo, hi))
        print("  5. the program in the camera actually saves an image on each trigger")
    else:
        print("\nNothing was received.")


if __name__ == "__main__":
    main()

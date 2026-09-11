"""One FFmpeg stream-copy process per video stream.

* Output: segmented Matroska (a crash-truncated MKV stays readable; MP4 does not).
  Timestamps are NOT reset between segments, so segments concatenate cleanly.
* -progress pipe:1: FFmpeg reports frame count and output time every ~0.5 s.
  Each report is stamped with the host master clock and logged to
  <name>_progress.csv. (host_time - out_time) gives a wall-clock anchor for the
  stream's PTS 0 - the Layer-4 estimate for video, used until scene
  cross-correlation (Layer 3) is available.
* Graceful stop: 'q' on stdin, so FFmpeg finalises the open segment.
"""
import collections
import glob
import os
import re
import subprocess
import threading
import time

try:
    from urllib.parse import quote
except ImportError:  # pragma: no cover
    from urllib import quote

from . import winutil

PROGRESS_FIELDS = ["host_time", "frame", "out_time_us", "speed"]


def ffmpeg_version(ffmpeg):
    """Returns (major, first_line) or (-1, error)."""
    try:
        out = subprocess.check_output([ffmpeg, "-hide_banner", "-version"], stderr=subprocess.STDOUT,
                                      creationflags=winutil.CREATE_NO_WINDOW).decode("utf-8", "replace")
        line = out.splitlines()[0] if out else ""
        m = re.search(r"version\s+n?(\d+)", line)
        return (int(m.group(1)) if m else 0), line
    except (OSError, subprocess.CalledProcessError) as e:
        return -1, str(e)


def rtsp_input_args(cam, channel, major, timeout_s):
    url = "rtsp://%s:%s@%s:554/Streaming/Channels/%s" % (
        quote(cam["user"], safe=""), quote(cam["password"], safe=""), cam["ip"], channel)
    timeout_opt = "-timeout" if major >= 5 else "-stimeout"   # renamed in FFmpeg 5
    return ["-rtsp_transport", "tcp", timeout_opt, str(int(timeout_s * 1e6)), "-i", url]


def simulated_input_args(kind, fps):
    size = "320x180" if kind == "optical" else "256x192"
    src = "testsrc2" if kind == "optical" else "mandelbrot"
    return ["-re", "-f", "lavfi", "-i", "%s=size=%s:rate=%g" % (src, size, fps)]


SIM_CODEC = ["-c:v", "libx264", "-preset", "ultrafast", "-g", "25", "-pix_fmt", "yuv420p"]
COPY_CODEC = ["-c", "copy"]


def _parse_out_time_us(block):
    for key in ("out_time_us", "out_time_ms"):          # out_time_ms is microseconds too
        v = block.get(key, "")
        if v.lstrip("-").isdigit():
            return int(v)
    m = re.match(r"(-?)(\d+):(\d+):(\d+(?:\.\d+)?)", block.get("out_time", ""))
    if m:
        us = int((int(m.group(2)) * 3600 + int(m.group(3)) * 60 + float(m.group(4))) * 1e6)
        return -us if m.group(1) else us
    return None


class FfmpegStream(object):
    def __init__(self, name, input_args, codec_args, out_dir, cfg, clock, emit):
        self.name = name
        self.input_args = input_args
        self.codec_args = codec_args
        self.out_dir = out_dir
        self.cfg = cfg
        self.clock = clock
        self.emit = emit                      # emit(event_type, **fields)
        self.proc = None
        self.t_start = None
        self.frames = 0
        self.last_progress = None
        self.last_bytes = 0
        self.last_growth = None
        self.history = collections.deque(maxlen=120)   # (host_time, frame)
        self.stop_requested = False
        self.health = "starting"
        self.died_at = None
        self._reader = None
        self._log = None
        self._csv = None

    @property
    def pattern(self):
        return os.path.join(self.out_dir, self.name + "_%03d.mkv")

    def command(self):
        cfg = self.cfg
        return ([cfg["ffmpeg"], "-hide_banner", "-loglevel", "warning", "-nostats",
                 "-progress", "pipe:1"]
                + self.input_args
                + ["-map", "0:v:0"] + self.codec_args
                + ["-t", str(int(cfg["max_record_seconds"] + 120)),     # hard ceiling
                   "-f", "segment", "-segment_time", str(cfg["segment_seconds"]),
                   "-segment_format", "matroska",
                   # Close a Matroska cluster every second and flush it: a crash or
                   # power cut then loses ~1 s of the open segment, not up to 5 s.
                   "-segment_format_options", "cluster_time_limit=1000:flush_packets=1",
                   "-segment_list", os.path.join(self.out_dir, self.name + "_segments.csv"),
                   "-segment_list_type", "csv",
                   self.pattern])

    def start(self):
        self._log = open(os.path.join(self.out_dir, self.name + "_ffmpeg.log"), "wb")
        self._csv = open(os.path.join(self.out_dir, self.name + "_progress.csv"), "w")
        self._csv.write(",".join(PROGRESS_FIELDS) + "\n")
        self.t_start = self.clock.now()
        self.last_growth = time.time()
        self.proc = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self._log, creationflags=winutil.CREATE_NO_WINDOW)
        winutil.attach_to_kill_job(self.proc)
        self._reader = threading.Thread(target=self._read_progress, name=self.name + "-progress")
        self._reader.daemon = True
        self._reader.start()
        self.emit("stream_started", stream=self.name, pid=self.proc.pid)

    def _read_progress(self):
        block = {}
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            block[k.strip()] = v.strip()
            if k != "progress":
                continue
            t = self.clock.now()
            frame = int(block["frame"]) if block.get("frame", "").isdigit() else None
            out_us = _parse_out_time_us(block)
            if frame is not None:
                self.frames = frame
                self.history.append((t, frame))
            self.last_progress = t
            try:
                self._csv.write("%.6f,%s,%s,%s\n" % (t, "" if frame is None else frame,
                                                    "" if out_us is None else out_us,
                                                    block.get("speed", "")))
                self._csv.flush()
            except ValueError:
                break                                     # file closed during shutdown
            block = {}

    # ------------------------------------------------------------------ #
    def bytes_on_disk(self):
        total = 0
        for f in glob.glob(os.path.join(self.out_dir, self.name + "_*.mkv")):
            try:
                total += os.path.getsize(f)
            except OSError:
                pass
        return total

    def fps(self, window=5.0):
        h = list(self.history)
        if len(h) < 2:
            return 0.0
        t_end, f_end = h[-1]
        for t, f in h:
            if t_end - t <= window:
                return (f_end - f) / (t_end - t) if t_end > t else 0.0
        return 0.0

    def check(self, stall_after=10.0):
        """Called once per second by the watchdog. Returns the current health."""
        now = time.time()
        b = self.bytes_on_disk()
        if b > self.last_bytes:
            self.last_bytes, self.last_growth = b, now
        alive = self.proc is not None and self.proc.poll() is None
        age = self.clock.now() - self.t_start
        if not alive:
            health = "stopped" if self.stop_requested and self.died_at is None else "dead"
            if not self.stop_requested and self.died_at is None:
                self.died_at = self.clock.now()
        elif self.stop_requested:
            health = "stopping"
        elif self.frames == 0 and age < 20:
            health = "starting"
        elif now - self.last_growth > stall_after or (
                self.last_progress and self.clock.now() - self.last_progress > stall_after):
            health = "stalled"
        else:
            health = "ok"
        if health != self.health:
            level = "warning" if health in ("dead", "stalled") else "info"
            self.emit("stream_health", stream=self.name, health=health, previous=self.health,
                      level=level, exit_code=None if alive else self.proc.returncode)
            self.health = health
        return health

    def status(self):
        t_now = self.clock.now()
        samples = list(self.history)[-60:]
        spark = []
        for (t0, f0), (t1, f1) in zip(samples, samples[1:]):
            spark.append(round((f1 - f0) / (t1 - t0), 1) if t1 > t0 else 0.0)
        return {
            "name": self.name, "type": "video", "health": self.health,
            "frames": self.frames, "fps": round(self.fps(), 2),
            "mb": round(self.last_bytes / 1e6, 1),
            "mbps": round(self.last_bytes * 8 / 1e6 / max(t_now - self.t_start, 1), 2) if self.t_start else 0,
            "since_growth_s": round(time.time() - self.last_growth, 1) if self.last_growth else None,
            "fps_history": spark[-40:],
            "pid": self.proc.pid if self.proc else None,
        }

    # ------------------------------------------------------------------ #
    def request_stop(self):
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                pass

    def finish(self, grace):
        """Wait for a graceful exit, escalate if needed. Returns how it ended."""
        how = "graceful"
        if self.died_at is not None:
            how = "died after %.0f s" % (self.died_at - self.t_start)
        try:
            self.proc.wait(grace)
        except subprocess.TimeoutExpired:
            how = "terminated"
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                how = "killed"
                self.proc.kill()
                self.proc.wait()
        if self._reader:
            self._reader.join(3)
        for fh in (self._log, self._csv):
            try:
                fh.close()
            except Exception:  # noqa
                pass
        self.check()
        self.emit("stream_finished", stream=self.name, how=how, exit_code=self.proc.returncode)
        return how

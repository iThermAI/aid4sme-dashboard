"""ISAPI helpers: an HTTP client per camera, multipart parsing, settings
snapshots, comparison, and minimal XML read/modify helpers.

Writing follows the only pattern verified on the HM-TD3028T-2/Q firmware:
GET the full document, change a value, PUT the full document back.
"""
import datetime
import html
import json
import os
import re
import threading
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPDigestAuth

P2P_PATH = "/ISAPI/Thermal/channels/{ch}/thermometry/jpegPicWithAppendData?format=json"


# --------------------------------------------------------------------------- #
# Multipart (behaviour identical to the radiometric bench)
# --------------------------------------------------------------------------- #
def parse_headers(raw):
    headers = {}
    for line in raw.decode("latin-1").split("\r\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def get_boundary(content_type):
    for p in content_type.split(";"):
        p = p.strip()
        if p.lower().startswith("boundary="):
            return p.split("=", 1)[1].strip('"').encode("latin-1")
    return b"boundary"


def parse_multipart(body, boundary):
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
        headers = parse_headers(body[pos:hdr_end])
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


def classify(parts):
    meta, p2p, jpegs = None, None, []
    for headers, data in parts:
        ctype = headers.get("content-type", "").lower()
        if meta is None and ("json" in ctype or data.lstrip()[:1] == b"{"):
            try:
                meta = json.loads(data.decode("utf-8", "replace"))
                continue
            except ValueError:
                pass
        if "octet-stream" in ctype:
            p2p = data
        elif "image" in ctype or data[:2] == b"\xff\xd8":
            jpegs.append(data)
    return meta, p2p, jpegs


def extract_matrix(ctype, body, sensor_w, sensor_h):
    """Returns (width, height, float32 little-endian bytes) or raises ValueError."""
    meta, p2p, _ = classify(parse_multipart(body, get_boundary(ctype)))
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
    return w, h, p2p[:n * 4]


# --------------------------------------------------------------------------- #
# Minimal XML value access that preserves the camera's own document verbatim
# --------------------------------------------------------------------------- #
def xml_get(text, tag):
    m = re.search(r"<%s(?:\s[^>]*)?>([^<]*)</%s>" % (re.escape(tag), re.escape(tag)), text)
    return html.unescape(m.group(1)).strip() if m else None


def xml_set(text, tag, value):
    pattern = re.compile(r"(<%s(?:\s[^>]*)?>)([^<]*)(</%s>)" % (re.escape(tag), re.escape(tag)))
    if not pattern.search(text):
        raise KeyError(tag)
    return pattern.sub(lambda m: m.group(1) + html.escape(value, quote=False) + m.group(3), text, count=1)


def response_status(text):
    """Hikvision ResponseStatus -> (ok, message)."""
    code = xml_get(text or "", "statusCode")
    msg = xml_get(text or "", "statusString") or xml_get(text or "", "subStatusCode") or ""
    return (code in (None, "1")), msg


# --------------------------------------------------------------------------- #
# Camera client
# --------------------------------------------------------------------------- #
class Camera(object):
    def __init__(self, cam_cfg):
        self.id = cam_cfg["id"]
        self.ip = cam_cfg["ip"]
        self.user = cam_cfg["user"]
        self.password = cam_cfg["password"]
        self.thermal_channel = str(cam_cfg.get("thermal_channel", "2"))
        self._lock = threading.Lock()
        self._session = self.new_session()

    def new_session(self):
        s = requests.Session()
        s.auth = HTTPDigestAuth(self.user, self.password)
        return s

    def url(self, path):
        return "http://%s%s" % (self.ip, path)

    def request(self, method, path, data=None, timeout=4.0, content_type="application/xml"):
        """Returns (status, content_type, body_bytes). Network errors raise requests exceptions."""
        headers = {"Content-Type": content_type} if data is not None else None
        with self._lock:
            r = self._session.request(method, self.url(path), data=data, headers=headers, timeout=timeout)
        return r.status_code, r.headers.get("Content-Type", ""), r.content

    def get(self, path, timeout=4.0):
        return self.request("GET", path, timeout=timeout)

    def stream(self, path, timeout=30.0):
        """Streaming GET for large downloads (full configuration backup)."""
        s = self.new_session()
        return s.get(self.url(path), timeout=timeout, stream=True)

    def picture(self, channel, timeout=4.0):
        status, _, body = self.get("/ISAPI/Streaming/channels/%s/picture" % channel, timeout)
        if status != 200 or body[:2] != b"\xff\xd8":
            raise IOError("HTTP %d from %s picture channel %s" % (status, self.id, channel))
        return body, "image/jpeg"

    def p2p(self, timeout=5.0):
        status, ctype, body = self.get(P2P_PATH.format(ch=self.thermal_channel), timeout)
        if status != 200:
            raise IOError("HTTP %d" % status)
        return ctype, body

    def device_time(self, clock, timeout=3.0):
        t_send = clock.now()
        status, _, body = self.get("/ISAPI/System/time", timeout)
        t_recv = clock.now()
        if status != 200:
            raise IOError("HTTP %d" % status)
        value = xml_get(body.decode("utf-8", "replace"), "localTime")
        if not value:
            raise IOError("no <localTime> in response")
        return parse_device_time(value), t_send, t_recv

    def read_sections(self, paths, timeout=4.0):
        """{name: {path, status, text, flat}} for every endpoint; never raises."""
        out = {}
        for name, path in paths.items():
            path = path.replace("{ch}", self.thermal_channel)
            entry = {"path": path}
            try:
                status, _, body = self.get(path, timeout)
                text = body.decode("utf-8", "replace")
                entry.update(status=status, text=text)
                if status == 200:
                    entry["flat"] = flatten_config(body)
            except requests.RequestException as e:
                entry.update(status=-1, error=type(e).__name__)
            out[name] = entry
        return out

    def snapshot(self, paths, dest_dir, timeout=4.0):
        """Read every endpoint and save the responses verbatim into dest_dir."""
        sections = self.read_sections(paths, timeout)
        os.makedirs(dest_dir, exist_ok=True)
        index = {}
        for name, e in sections.items():
            if "text" in e:
                ext = "json" if e["text"].lstrip()[:1] == "{" else "xml"
                fn = "%s.%s" % (name, ext)
                with open(os.path.join(dest_dir, fn), "w", encoding="utf-8") as f:
                    f.write(e["text"])
                e["file"] = fn
            index[name] = {k: v for k, v in e.items() if k in ("path", "status", "file", "error")}
        with open(os.path.join(dest_dir, "_index.json"), "w") as f:
            json.dump(index, f, indent=2)
        return sections


def parse_device_time(text):
    """ISAPI localTime, e.g. 2026-09-10T17:03:05+02:00, ...Z, or without offset (local)."""
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    m = re.match(r"^(.*[T ]\d\d:\d\d:\d\d)(\.\d+)?([+-]\d\d:?\d\d)?$", t)
    if not m:
        raise ValueError("unrecognised time %r" % text)
    base, frac, tz = m.group(1), m.group(2) or "", m.group(3)
    if frac:
        frac = "." + (frac[1:] + "000000")[:6]   # Python 3.8 accepts only 3 or 6 digits
    if tz and ":" not in tz:
        tz = tz[:3] + ":" + tz[3:]
    dt = datetime.datetime.fromisoformat(base.replace(" ", "T") + frac + (tz or ""))
    return dt.timestamp()              # naive datetimes are taken as host local time


# --------------------------------------------------------------------------- #
# Flattening / comparison
# --------------------------------------------------------------------------- #
def _strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def flatten_config(content):
    """XML or JSON -> {"Root/child/leaf": "value"}; repeated siblings get [i]."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    content = content.strip()
    flat = {}
    if content[:1] == b"{":
        def walk_json(obj, prefix):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk_json(v, prefix + "/" + k if prefix else k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk_json(v, "%s[%d]" % (prefix, i))
            else:
                flat[prefix] = str(obj)
        try:
            walk_json(json.loads(content.decode("utf-8", "replace")), "")
        except ValueError:
            flat["_unparsed"] = "json"
        return flat
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return {"_unparsed": "xml"}

    def walk(el, prefix):
        children = list(el)
        if not children:
            flat[prefix] = (el.text or "").strip()
            return
        counts = {}
        for c in children:
            counts[_strip_ns(c.tag)] = counts.get(_strip_ns(c.tag), 0) + 1
        seen = {}
        for c in children:
            tag = _strip_ns(c.tag)
            if counts[tag] > 1:
                seen[tag] = seen.get(tag, 0) + 1
                tag = "%s[%d]" % (tag, seen[tag] - 1)
            walk(c, prefix + "/" + tag)

    walk(root, _strip_ns(root.tag))
    return flat


def diff_flat(old, new, ignore_keys):
    """[{key, old, new}] for every differing leaf."""
    def ignored(key):
        return re.sub(r"\[\d+\]$", "", key.rsplit("/", 1)[-1]) in ignore_keys
    out = []
    for key in sorted(set(old) | set(new)):
        if ignored(key) or old.get(key) == new.get(key):
            continue
        out.append({"key": key, "old": old.get(key), "new": new.get(key)})
    return out


def diff_sections(reference, current, ignore_keys, only=None):
    """reference/current: {section: {status, flat}} -> [{section, key, old, new}]."""
    changes = []
    for name in sorted(set(reference) | set(current)):
        if only and name not in only:
            continue
        r, c = reference.get(name, {}), current.get(name, {})
        if r.get("status") != c.get("status"):
            changes.append({"section": name, "key": "(endpoint)", "old": "HTTP %s" % r.get("status"),
                            "new": "HTTP %s" % c.get("status")})
            continue
        for d in diff_flat(r.get("flat") or {}, c.get("flat") or {}, ignore_keys):
            d["section"] = name
            changes.append(d)
    return changes

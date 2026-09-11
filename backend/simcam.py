"""A simulated HIKMICRO camera for --simulate mode and tests.

It answers the same ISAPI requests as a real camera, from in-memory XML
documents modelled on the HM-TD3028T-2/Q. Writes (PUT) change those
documents, so channel-name edits and profile restores behave end to end.
Field names outside the streaming channel are placeholders until they are
confirmed from a real camera dump.
"""
import datetime
import json
import math
import struct
import threading
import time

from .isapi import Camera, xml_get

STREAM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<StreamingChannel version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>{id}</id>
<channelName>{name}</channelName>
<enabled>true</enabled>
<Transport>
<maxPacketSize>1000</maxPacketSize>
<Unicast>
<enabled>true</enabled>
<rtpTransportType>RTP/TCP</rtpTransportType>
</Unicast>
</Transport>
<Video>
<enabled>true</enabled>
<videoInputChannelID>{input}</videoInputChannelID>
<videoCodecType>H.265</videoCodecType>
<videoScanType>progressive</videoScanType>
<videoResolutionWidth>{w}</videoResolutionWidth>
<videoResolutionHeight>{h}</videoResolutionHeight>
<videoQualityControlType>CBR</videoQualityControlType>
<constantBitRate>{kbps}</constantBitRate>
<fixedQuality>60</fixedQuality>
<maxFrameRate>2500</maxFrameRate>
<keyFrameInterval>1000</keyFrameInterval>
<snapShotImageType>JPEG</snapShotImageType>
<GovLength>25</GovLength>
<SVC>
<enabled>false</enabled>
</SVC>
<smoothing>1</smoothing>
</Video>
</StreamingChannel>
"""


def _docs(cam_id, label):
    return {
        "/ISAPI/System/deviceInfo": """<?xml version="1.0" encoding="UTF-8"?>
<DeviceInfo version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<deviceName>{label}</deviceName>
<model>HM-TD3028T-2/Q</model>
<serialNumber>SIM-{cam}-0001</serialNumber>
<macAddress>00:00:5e:00:53:0{n}</macAddress>
<firmwareVersion>V5.5.80</firmwareVersion>
<firmwareReleasedDate>build 250601</firmwareReleasedDate>
<deviceType>IPCamera</deviceType>
</DeviceInfo>""".format(label=label, cam=cam_id.upper(), n=cam_id[-1]),
        "/ISAPI/System/time/ntpServers": """<?xml version="1.0" encoding="UTF-8"?>
<NTPServerList version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<NTPServer><id>1</id><addressingFormatType>ipaddress</addressingFormatType>
<ipAddress>192.168.1.10</ipAddress><portNo>123</portNo><synchronizeInterval>60</synchronizeInterval></NTPServer>
</NTPServerList>""",
        "/ISAPI/Streaming/channels/101": STREAM_XML.format(id=101, name=label, input=1, w=2688, h=1520, kbps=8192),
        "/ISAPI/Streaming/channels/201": STREAM_XML.format(id=201, name=label, input=2, w=1280, h=960, kbps=3072),
        "/ISAPI/System/Video/inputs/channels/1": """<?xml version="1.0" encoding="UTF-8"?>
<VideoInputChannel version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>1</id><inputPort>1</inputPort><name>{label}</name></VideoInputChannel>""".format(label=label),
        "/ISAPI/System/Video/inputs/channels/2": """<?xml version="1.0" encoding="UTF-8"?>
<VideoInputChannel version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>2</id><inputPort>2</inputPort><name>{label}</name></VideoInputChannel>""".format(label=label),
        "/ISAPI/Image/channels/1": """<?xml version="1.0" encoding="UTF-8"?>
<ImageChannel version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>1</id><Color><brightnessLevel>50</brightnessLevel><contrastLevel>50</contrastLevel></Color>
<WDR><mode>close</mode></WDR></ImageChannel>""",
        "/ISAPI/Image/channels/2": """<?xml version="1.0" encoding="UTF-8"?>
<ImageChannel version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>1</id><enabled>true</enabled><videoInputID>1</videoInputID>
<NoiseReduce><mode>advanced</mode><AdvancedMode><FrameNoiseReduceLevel>10</FrameNoiseReduceLevel>
<InterFrameNoiseReduceLevel>0</InterFrameNoiseReduceLevel></AdvancedMode></NoiseReduce>
<Color><brightnessLevel>50</brightnessLevel><contrastLevel>50</contrastLevel></Color>
<DigitalZoom><ZoomRatio>1x</ZoomRatio></DigitalZoom>
<Palettes><mode>WhiteHot</mode></Palettes>
<AGC><AGCMode>linear</AGCMode></AGC>
<TempRange><mode>manual</mode><temperatureUpperLimit>150.0</temperatureUpperLimit>
<temperatureLowerLimit>20.0</temperatureLowerLimit></TempRange>
</ImageChannel>""",
        "/ISAPI/Image/channels/2/FFC": """<?xml version="1.0" encoding="UTF-8"?>
<FFC version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema"><mode>auto</mode>
<compsentationTime>10</compsentationTime></FFC>""",
        "/ISAPI/System/Video/inputs/channels/1/overlays": """<?xml version="1.0" encoding="UTF-8"?>
<VideoOverlay version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<DateTimeOverlay><enabled>true</enabled><displayWeek>false</displayWeek><displayDate>true</displayDate><displayTime>true</displayTime></DateTimeOverlay>
<channelNameOverlay><enabled>true</enabled><name>{label}</name></channelNameOverlay></VideoOverlay>""".format(label=label),
        "/ISAPI/System/Video/inputs/channels/2/overlays": """<?xml version="1.0" encoding="UTF-8"?>
<VideoOverlay version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<DateTimeOverlay><enabled>true</enabled><displayWeek>false</displayWeek><displayDate>true</displayDate><displayTime>true</displayTime></DateTimeOverlay>
<channelNameOverlay><enabled>true</enabled><name>{label}</name></channelNameOverlay></VideoOverlay>""".format(label=label),
        "/ISAPI/Thermal/channels/2/thermometry/basicParam": """<?xml version="1.0" encoding="UTF-8"?>
<ThermometryBasicParam version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>2</id><enabled>true</enabled><streamOverlay>false</streamOverlay><pictureOverlay>false</pictureOverlay>
<temperatureRange>-20~150</temperatureRange><temperatureUnit>degreeCentigrade</temperatureUnit>
<emissivity>0.96</emissivity><distanceUnit>centimeter</distanceUnit><distance>150</distance>
<reflectiveEnable>false</reflectiveEnable>
<refreshPixelToPixeDataIntervalTime>1</refreshPixelToPixeDataIntervalTime></ThermometryBasicParam>""",
        "/ISAPI/Thermal/channels/2/thermometry/1": """<?xml version="1.0" encoding="UTF-8"?>
<ThermometryScene version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema"><id>1</id>
<ThermometryRegionList><ThermometryRegion><id>1</id><enabled>false</enabled><name>R1</name><type>region</type></ThermometryRegion>
<ThermometryRegion><id>2</id><enabled>false</enabled><name>P2</name><type>point</type></ThermometryRegion></ThermometryRegionList>
</ThermometryScene>""",
        "/ISAPI/Thermal/channels/2/thermometry/pixelToPixelParam": """<?xml version="1.0" encoding="UTF-8"?>
<PixelToPixelParam version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<id>2</id><maxFrameRate>400</maxFrameRate><reflectiveEnable>false</reflectiveEnable>
<reflectiveTemperature>20.0</reflectiveTemperature><emissivity>0.96</emissivity><distance>150</distance>
<refreshInterval>50</refreshInterval><distanceUnit>centimeter</distanceUnit>
<temperatureDataLength>4</temperatureDataLength></PixelToPixelParam>""",
    }


OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<requestURL></requestURL><statusCode>1</statusCode><statusString>OK</statusString></ResponseStatus>"""
NOT_FOUND = b"""<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
<statusCode>4</statusCode><statusString>Invalid Operation</statusString>
<subStatusCode>notSupport</subStatusCode></ResponseStatus>"""


def hot_spot(t):
    """Normalised position of the simulated hot part, shared by image and matrix."""
    return 0.2 + 0.6 * (0.5 + 0.5 * math.sin(t / 4.0)), 0.55


class SimCamera(Camera):
    def __init__(self, cam_cfg):
        Camera.__init__(self, cam_cfg)
        label = "Cam %s" % cam_cfg["id"][-1]
        self.docs = _docs(cam_cfg["id"], label)
        self.docs_lock = threading.Lock()

    def request(self, method, path, data=None, timeout=4.0, content_type="application/xml"):
        time.sleep(0.01)
        with self.docs_lock:
            if path == "/ISAPI/System/time" and method == "GET":
                now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
                return 200, "application/xml", ("""<?xml version="1.0" encoding="UTF-8"?>
<Time version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema"><timeMode>NTP</timeMode>
<localTime>%s</localTime><timeZone>CST-1:00:00</timeZone></Time>""" % now).encode()
            if path not in self.docs:
                return 404, "application/xml", NOT_FOUND
            if method == "GET":
                return 200, "application/xml", self.docs[path].encode()
            if method == "PUT":
                text = data.decode("utf-8") if isinstance(data, bytes) else data
                self.docs[path] = text
                return 200, "application/xml", OK
        return 405, "text/plain", b""

    def stream(self, path, timeout=30.0):
        payload = json.dumps(self.docs, indent=1).encode()

        class R(object):
            status_code = 200
            headers = {"Content-Type": "application/octet-stream"}

            def iter_content(self, n):
                for i in range(0, len(payload), n):
                    yield payload[i:i + n]

            def close(self):
                pass
        return R()

    def channel_label(self, kind):
        path = "/ISAPI/Streaming/channels/%s" % ("101" if kind == "optical" else "201")
        return xml_get(self.docs.get(path, ""), "channelName") or ""

    def picture(self, channel, timeout=4.0):
        kind = "optical" if str(channel).startswith("1") else "thermal"
        w, h = (672, 380) if kind == "optical" else (640, 480)
        x, y = hot_spot(time.time())
        bg, spot = ("#56626c", "#c9ced3") if kind == "optical" else ("#1d2227", "#f4f4f4")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
               '<defs><radialGradient id="g"><stop offset="0" stop-color="%s"/>'
               '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient></defs>'
               '<rect width="100%%" height="100%%" fill="%s"/>'
               '<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#8a949c" stroke-width="3"/>'
               '<circle cx="%d" cy="%d" r="%d" fill="url(#g)"/>'
               '<text x="16" y="30" font-family="Arial" font-size="16" fill="#fff">%s</text>'
               '<text x="%d" y="%d" font-family="Arial" font-size="18" fill="#fff" text-anchor="end">%s</text>'
               '</svg>') % (w, h, w, h, spot, spot, bg, w * 0.35, h * 0.2, w * 0.3, h * 0.6,
                            x * w, y * h, h // 5, stamp, w - 14, h - 14, self.channel_label(kind))
        return svg.encode(), "image/svg+xml"

    def p2p(self, timeout=5.0):
        w, h = 256, 192
        x, y = hot_spot(time.time())
        cx, cy, r2 = x * w, y * h, (h / 7.0) ** 2
        vals = []
        for j in range(h):
            dy = (j - cy) ** 2
            inside_y = 0.2 * h <= j < 0.8 * h
            for i in range(w):
                v = 27.0 + 95.0 * math.exp(-((i - cx) ** 2 + dy) / r2)
                if inside_y and 0.35 * w <= i < 0.65 * w:
                    v += 18.0
                vals.append(v)
        p2p = struct.pack("<%df" % len(vals), *vals)
        meta = {"JpegPictureWithAppendData": {"channel": 2, "jpegPicWidth": w, "jpegPicHeight": h,
                                              "p2pDataLen": len(p2p), "temperatureDataLength": 4,
                                              "isFreezedata": False}}
        b = b"boundary"
        body = (b"--" + b + b"\r\nContent-Type: application/json\r\n\r\n" + json.dumps(meta).encode()
                + b"\r\n--" + b + b"\r\nContent-Type: application/octet-stream\r\nContent-Length: %d\r\n\r\n"
                % len(p2p) + p2p + b"\r\n--" + b + b"--\r\n")
        return "multipart/form-data; boundary=boundary", body

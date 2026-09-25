# Aid4SME Dashboard

Multi-modal data capture for injection moulding, built for machine-learning datasets.

Aid4SME Dashboard records, in one run and without re-encoding:

- two optical video streams and two thermal video streams from HIKMICRO / Hikvision bi-spectrum cameras,
- the radiometric temperature matrix of each thermal sensor (°C per pixel, about once per second),
- process parameters from a Keyence IV3 OCR camera reading the machine's screen (optional),
- the operator's run details, regions of interest, notes and a 3D model of the part.

Everything is started and stopped from a local web dashboard, in English or Slovenian. Each run becomes one self-describing folder that a training pipeline can use directly.

Developed by iThermAI together with ELVEZ d.o.o.

---

## Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Try it without cameras](#try-it-without-cameras)
4. [Install on the capture PC](#install-on-the-capture-pc)
5. [Build the dashboard](#build-the-dashboard)
6. [Configuration](#configuration)
7. [Prepare the cameras](#prepare-the-cameras)
8. [Daily use](#daily-use)
9. [Recorded data](#recorded-data)
10. [Development](#development)
11. [Troubleshooting](#troubleshooting)
12. [Licence and funding](#licence-and-funding)

---

## Features

**Recording**
- Four video streams are copied to disk exactly as the cameras send them (no decoding, no quality loss, low CPU). Files are Matroska segments, so a crash or power cut costs at most one segment.
- Radiometric temperature data is saved as the cameras' raw responses, with request and response times for synchronisation.
- A live health view shows frame rate, data written and a one-minute trace per stream. An alarm sounds if a stream stops.
- The operator can stop at any time. An optional automatic stop can be set per run (for example 2 minutes), with a safety limit behind it.
- Notes typed during a run are stored with their exact time.

**Setting up a run**
- Live previews of all four channels. Zoom with the mouse wheel, drag to move the view, and enlarge any channel. Zooming never changes a region, and recordings are always full frame.
- Several named regions of interest per channel. Each can be moved, resized by its edges and corners, nudged with the arrow keys, or deleted.
- On thermal channels, the temperature under the cursor and the minimum, maximum and mean of each region are shown live.
- Run details (operator, mould, part, material, shot counter and notes) are required before recording can start.
- Part presets load mould, part, material, regions and 3D model in one step.
- Run numbers are counted automatically per mould. Chosen fields, such as the mould ID, can also increase after each run (M-012 becomes M-013).
- A 3D viewer shows the part's `.glb` model so the operator can confirm the part.

**Cameras**
- A details page reads each camera live over ISAPI: model, firmware, time source, the name shown on the video, codec, resolution, frame rate, bitrate, keyframe interval, palette, contrast mode, temperature range, emissivity and distance. It reads again whenever the operator returns to the page, so changes made in the camera's own web page appear immediately.
- A settings check compares each camera with recommended values and flags what differs.
- The name shown on the video can be changed from the dashboard.
- Camera settings profiles save the image, stream and measurement settings of both cameras.
  - **Reference profile:** one profile is compared with the live cameras before every run.
  - **Restore:** shows exactly what will change, then writes the settings back. Network settings and user accounts are never changed.
- The camera's own complete backup file can be downloaded for administrators.

**After a run**
- Every file is verified automatically: frame counts, gaps, start offsets between streams and timing uncertainty.
- The operator marks the run as usable, discard or not sure, with an optional reason. This label is stored with the session.
- A sessions list can be searched by mould, part, material or operator.

---

## Requirements

**Capture PC** (runs the server and records)
- Windows 7 SP1 64-bit or newer, or Linux.
- Python 3.8 or newer. Python 3.8 is the last version that installs on Windows 7.
- FFmpeg with `ffprobe`. We test with `ffmpeg 9.0.1-essentials_build` from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
- Google Chrome 109 or newer. On Windows 7, Chrome 109 is the last version, and the dashboard is built to run on it.
- An SSD for recordings: about 1 GB per 5 minutes of recording, and 20 GB free before a run can start.
- Wired network to the cameras. 100 Mbit/s per camera is enough, but a gigabit switch is recommended.

**Build PC** (only to build the dashboard; can be any modern PC)
- Docker. Node.js is never needed on the capture PC.

**Cameras**
- HIKMICRO HM-TD3028T-2/Q, or a Hikvision / HIKMICRO bi-spectrum camera with ISAPI and the `jpegPicWithAppendData` radiometric endpoint.
- A camera user with administrator rights (settings are read over ISAPI with digest authentication).

---

## Try it without cameras

Simulation mode replaces the cameras with FFmpeg test sources and a simulated ISAPI camera. With Docker on any PC:

```sh
git clone <this repository> aid4sme-dashboard
cd aid4sme-dashboard
cd frontend && ./build.sh && cd ..      # build the dashboard once (Windows: .\build.ps1)
./scripts/sim-backend.sh                # start the simulated backend
```

Open <http://localhost:8000>. The previews move, regions can be drawn, and a full record, stop and verify cycle works.

Without Docker, on a PC with Python and FFmpeg installed:

```sh
pip install -r requirements.txt
cp config.example.json config.local.json   # then set data_dir to a local folder
python run_server.py --simulate
```

---

## Install on the capture PC

1. **Python.** Install Python 3.8 64-bit (or newer where possible) and tick *Add Python to PATH*.
2. **FFmpeg.** Unzip the build, for example to `C:\aid4sme\ffmpeg`, so that `C:\aid4sme\ffmpeg\bin\ffmpeg.exe` exists.
3. **This repository.** Copy it to the capture PC, for example to `C:\aid4sme\aid4sme-dashboard`.
4. **Python packages.** In a command prompt in that folder, run:
   ```bat
   pip install -r requirements.txt
   ```
   The versions are pinned to ones that install on Windows 7. pydantic stays on version 1, because version 2 does not load on Windows 7.
5. **Configuration.** Copy `config.example.json` to `config.local.json` and enter the camera addresses, the camera password, the FFmpeg path and the data folder (see [Configuration](#configuration)).
6. **Dashboard.** Build it (next section) and copy the resulting `frontend\dist` folder into the same place on the capture PC.
7. **Start.** Double-click `run_server.bat`, then open <http://localhost:8000> in Chrome.

Before recording data you intend to keep, also check these on the capture PC:
- **Sleep:** sleep and hibernation are disabled, and Windows Update cannot restart during working hours.
- **Antivirus:** the data folder is excluded from antivirus real-time scanning.
- **Time server:** the PC runs an NTP server (for example the Meinberg NTP package on Windows), and both cameras use it as their time source.

---

## Build the dashboard

The dashboard is a Vue 3 application compiled to static files, which the Python server then serves. It is built inside Docker, so no Node.js installation is needed anywhere.

```sh
cd frontend
./build.sh          # Linux / macOS
.\build.ps1         # Windows PowerShell
```

The output is `frontend/dist/`. Copy that folder to `frontend/dist/` on the capture PC and restart the server.

Opening `dist/index.html` directly from disk shows a blank page. That is expected: the dashboard must be opened through the server at `http://<capture-pc>:8000`.

The build targets Chrome 109, so it runs on Windows 7. The fonts (IBM Plex Sans and Barlow Semi Condensed, both open licence) are bundled into the build, so the capture PC needs no internet access.

---

## Configuration

`config.local.json` holds site-specific settings. It contains camera passwords and is excluded from Git by `.gitignore`. Only the values you set override the defaults in `backend/config.py`.

| Key | Meaning |
|---|---|
| `data_dir` | Folder for sessions, presets and profiles. Use an SSD. |
| `ffmpeg`, `ffprobe` | Full paths to the executables, or just the names if they are on `PATH`. |
| `cameras` | `id`, `ip`, `user`, `password` and `thermal_channel` for each camera. Addresses and passwords can also be changed later on the dashboard's **Settings** page. |
| `port` | Dashboard port (default `8000`). |
| `nominal_fps` | Frame rate the cameras are set to (default `25`). |
| `max_record_seconds` | Safety limit for one run (default `1800`). |
| `radiometric.rate_hz` | Radiometric requests per second per camera (default `1.0`). |
| `required_metadata` | Run-detail fields that must be filled in before recording. |
| `min_free_disk_gb` | Recording is blocked below this free space (default `20`). |
| `keyence` | `mode` is `off`, `iv3` or `tcp`; see the Keyence IV3 section. |
| `ffc_path` | Optional ISAPI path that triggers a shutter calibration. Leave empty to hide the button. |

When camera connections are saved from the dashboard, the previous `config.local.json` is kept as a timestamped `.bak` file next to it.

---

## Prepare the cameras

These camera settings determine whether the thermal video can be compared across frames and runs. The dashboard's settings check flags every one of them.

| Setting | Recommended |
|---|---|
| Frame rate | 25 fps on all four streams |
| Keyframe interval (GOP) | 25, one keyframe per second |
| Bitrate type | Constant (CBR) |
| Codec | H.265 (H.264 works but needs twice the storage) |
| Palette | White Hot |
| Contrast mode (AGC) | Linear or manual, not adaptive or histogram |
| Detail enhancement (DDE) | Off |
| Display mode | Pure thermal, no bi-spectrum fusion |
| Measurement rules and overlays | None drawn on the video |
| Date and time on video | On |
| Time source | NTP, pointing at the capture PC |
| Emissivity and distance | Fixed, documented values. Set the distance to the real distance between camera and part. |

Once both cameras are right, open **Cameras**, choose **Save current settings** and tick **Use as reference**. From then on, any difference from that profile appears before every run, and **Restore** brings the cameras back to it.

Field names for thermal image settings differ between firmware versions. If a value shows as *not identified yet*, run the read-only dump tool and use its output to extend the name patterns in `backend/camerainfo.py`:

```sh
python tools/isapi_dump.py 192.168.1.30 --password <password>
```

The tool only sends read requests and never changes the camera. It writes a `.zip` file with one file per endpoint.

---

## Daily use

1. **Run.** Choose a part preset, or fill in operator, mould ID, part number and material. The run number for that mould is shown automatically.
2. **Check the list above the Start button.**
   - *Red items* block recording, for example a camera not responding or a missing field.
   - *Amber items* are warnings, for example a camera setting that differs from the reference profile. Click it to open the camera's details.
3. **Regions.** Draw or adjust the regions of interest with **Add region**. Zoom in to place them precisely.
4. **Start recording.** Watch the stream table; any problem appears in red and sounds an alarm.
5. **Stop recording.** Click twice, so a stray click cannot end a run. Runs with an automatic stop end on their own.
6. **Check the result.** When the files have been verified, mark the run *Usable*, *Not sure* or *Discard*, then choose **Set up next run**. The run details are kept, and the chosen fields increase automatically.

The **Settings** page controls:
- camera connections,
- which fields increase after each run,
- language (English or Slovenian),
- light or dark appearance,
- full camera backups.

---

## Recorded data

One folder per run, named `<date>_<time>_<mould>_run<NNN>`:

```
20260911_143321_M-012_run004/
├── metadata.json          Run details, regions, camera details and settings check,
│                          differences from the reference profile, operator verdict
├── verification.json      Frame counts, gaps, start offsets, timing uncertainty
├── events.jsonl           Time-stamped event log of the run
├── capture.log            Process log
├── cad_asset.glb          The part model, if one was loaded
└── raw/
    ├── cam1_optical_000.mkv …   Video segments, stream-copied (H.265 / H.264)
    ├── cam1_optical_segments.csv, _progress.csv, _ffmpeg.log
    ├── … the same for cam1_thermal, cam2_optical, cam2_thermal
    ├── radiometric_cam1/        000001.bin … raw camera responses + index.csv
    ├── radiometric_cam2/
    ├── camera_config/cam1/      Every ISAPI settings document at the start of the run
    ├── camera_config/cam2/
    └── keyence/                 IV3 images, result files and index.csv
```

- **Regions** are stored in `metadata.json` in three coordinate systems:
  - normalised (0–1),
  - pixels of the full video frame,
  - pixels of the 256 × 192 radiometric matrix, for thermal channels.

  They are applied by the training pipeline and never cut into the recording.
- **Radiometric files** are saved exactly as the camera sent them. Each contains the matrix as float32 °C, after a JSON header and a JPEG.
- **Timing:** video files carry stream-relative timestamps only. `verification.json` gives each stream's measured start offset and its uncertainty, which is the basis for aligning the streams later.

---

## Keyence IV3 images

The IV3 is used as a camera, not as an OCR reader: it photographs the moulding
machine's screen, and the pictures are read later. Set `keyence.mode` to `"iv3"` in
`config.local.json`:

```json
"keyence": {
  "mode": "iv3",
  "host": "192.168.1.40",
  "port": 8500,
  "trigger": true,
  "trigger_interval_s": 5.0,
  "ftp_port": 2121,
  "ftp_user": "ftpuser",
  "ftp_pass": "ftppass",
  "ftp_passive_ports": [2130, 2140]
}
```

The FTP server runs for as long as the dashboard runs, so the camera is never refused a
connection. Between runs the pictures it pushes go to a scratch folder that keeps only the
newest few, for the live view; during a run they are moved into the session as they arrive
and listed in `index.csv`.

When `"trigger": true`, the dashboard also triggers the camera over TCP every
`trigger_interval_s` seconds, and the operator can change that interval in **Settings**.
Triggering happens while a run is recording or while somebody is watching the live view,
never in between, so the camera is not photographed all day for nothing.

Set `"trigger": false` (or **Settings → Keyence → Trigger → The camera triggers itself**)
when the IV3 program uses an internal trigger. If the camera answers a trigger command with
`ER,T1,03` it is refusing it — usually because it is in setup mode, IV3 Navigator is
connected, or the program does not use an external trigger. After three refusals the
dashboard stops asking and simply records what the camera sends, and says so on the
Cameras page.

Before switching it on, `python tools/keyence_mwe.py --ip 192.168.1.40` tests the whole
Keyence path on its own: it triggers the camera, runs a temporary FTP server, and says which
of the two halves is failing. Close the IV3 Navigator software first; while it holds the
sensor, trigger commands are refused. Note that Navigator connects on port 63000, which is
its own channel; triggering uses port 8500.

**On the camera**, in the IV3 software, set image output to FTP, pointing at the capture
PC's address and `ftp_port`, with the same user and password. **On the capture PC**, allow
incoming TCP on `ftp_port` and on the passive range in the Windows firewall.

In the **Run** tab the IV3 appears as a fifth live view, below the four camera views, so the
operator can check framing and focus and zoom in on the screen before recording. Regions drawn
on it mark the fields to be read later; like all regions they change nothing in the recording.
The **Cameras** page has an IV3 card with the latest picture, the camera's own result values
and a "Take a picture now" button, and the **Settings** page holds its address, ports and
interval. The camera is only triggered while somebody is watching it or while a run is
recording.

Files land in `raw/keyence/` exactly as the camera sent them, and `raw/keyence/index.csv`
records, for every image: the time the trigger was sent, the time the camera answered, the
time the file finished transferring, the file name and size, and the camera's own trigger
number, timestamp and result status.

**OCR is a later step and needs no re-recording.** The dataset builder writes
`derived/keyence.csv`, one row per trigger, with the image path, the host time of the
photograph, its uncertainty and an empty `ocr_text` column. An OCR script fills that column
by reading the images the file points at, and can be re-run whenever it improves.

The photograph's time is taken as the midpoint between the trigger leaving and the camera
answering, so the FTP transfer afterwards doesn't affect it. Expect a few milliseconds of
uncertainty, which is far better than the temperature data.

---

## Building the dataset from a run

`tools/build_dataset.py` turns raw sessions into aligned data. It runs on the capture PC
(Python 3.8, numpy, the same FFmpeg), reads only `raw/`, and writes to `<session>/derived/`.

```bat
python tools\build_dataset.py D:\aid4sme_data\sessions\20260918_134047_1834_run023
python tools\build_dataset.py D:\aid4sme_data\sessions --all
```

| Output | Contents |
|---|---|
| `<stream>_frames.csv` | Every frame with its position in the file and its host time |
| `<stream>_motion.csv` | Per-frame motion signal used for alignment |
| `radiometric_<cam>.npy` | float32 array `[matrices, 192, 256]` in °C |
| `radiometric_<cam>.csv` | Capture time and timing uncertainty of every matrix |
| `keyence.csv` | One row per IV3 trigger: image path, host time, trigger number, empty `ocr_text` |
| `sync.json` | Measured offset of each stream, with correlation quality |
| `telemetry.jsonl` | Events, operator notes and matrices in one time-ordered file |
| `dataset.json` | What was produced |

**How alignment works.** The optical and thermal channels of one camera share a housing and
a field of view, so their frame-to-frame motion signals can be cross-correlated to measure the
offset between them. That measurement comes from the pictures themselves, so it includes the
camera's own encoding delay, which arrival times cannot see.

**Between cameras it is an estimate, not a measurement.** Where the two cameras look at
different things — at Elvez one watches the machine and one the finished parts — there is no
shared event to correlate. Two views of the same production rhythm can correlate strongly and
still be meaningless, so the tool does not try: offsets between cameras come from when the
data reached the capture PC, roughly ±100 ms. Every stream in `sync.json` says which method
produced its number, and `trust` reflects it.

Closing that gap needs something both cameras can see at one instant: a light flash in the
cell at the start of a run, a status lamp visible to both, or a hardware trigger from the
machine. Without one, ±100 ms between cameras is the honest figure to quote.

`offset_ms` is how much later a stream's content is than the reference stream; subtract it
from that stream's host times to put the streams on one timeline. Where `correlation` is
present it says how much to trust the measurement: above 0.6 is good, below 0.3 means the run
had too little movement in view.

Useful options: `--skip-motion` skips alignment and is much faster, `--keep-joined` keeps the
joined video files (doubling disk use; the raw segments are always kept), and `--all`
processes every session in a folder.

---

## Development

```
backend/        FastAPI server, recorder, ISAPI client, simulated camera
frontend/       Vue 3 dashboard (Vite), built in Docker
scripts/        sim-backend.sh (simulated backend), dev-ui.sh (live-reload dashboard)
tools/          isapi_dump.py (camera settings dump), build_dataset.py (offline dataset builder),
                keyence_mwe.py (standalone IV3 trigger + FTP test)
```

For live reload while working on the dashboard, run the backend (simulated, or a real capture PC) and then the Vite dev server:

```sh
./scripts/sim-backend.sh                                   # terminal 1
./scripts/dev-ui.sh                                        # terminal 2, open http://localhost:5173
BACKEND=http://192.168.1.10:8000 ./scripts/dev-ui.sh       # or against a real capture PC
```

The HTTP API is documented at `http://<server>:8000/api/docs`. All recording rules are enforced by the server, not the browser. API errors return short codes, which the dashboard translates; the translations are in `frontend/src/i18n.js`.

---

## Troubleshooting

| Symptom | Cause and remedy |
|---|---|
| Blank page when opening `index.html` | The dashboard must be opened through the server: `http://<capture-pc>:8000`. |
| "The dashboard server is not answering" on port 5173 | The dev server cannot reach the backend. Start one, and set `BACKEND` to its address (`http://localhost:8000` for the simulated backend). |
| A camera shows *Not responding* | Check the address on the **Settings** page with **Test**. Also check that the camera's web page opens from the capture PC. |
| *Wrong user or password* | The camera may lock the account after repeated failures. Wait, then correct the password on the **Settings** page. |
| A stream stops during a run | Check cables and the switch. A consumer router carrying four video streams is a common cause; a plain gigabit switch between cameras and PC usually fixes it. |
| Clock warning | The camera is not synchronised with the capture PC. Check the NTP server settings in the camera's web page. |
| A thermal setting shows *not identified yet* | Run `tools/isapi_dump.py` and extend the patterns in `backend/camerainfo.py`. |
| 3D model does not display | Only uncompressed binary glTF (`.glb`) is supported. Export without Draco or Meshopt compression. |

---

## Licence and funding

Copyright © 2026 iThermAI and ELVEZ d.o.o. All rights reserved. This is proprietary software; see [LICENSE](LICENSE). Third-party components remain under their own licences.

This work was supported by the AID4SME project, funded by the European Union's Horizon Europe research and innovation programme under grant agreement No 101189562.

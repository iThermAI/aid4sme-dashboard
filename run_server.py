#!/usr/bin/env python
"""Start the Aid4SME Dashboard server.

    python run_server.py                 # uses config.local.json
    python run_server.py --simulate      # no cameras needed: FFmpeg test sources
    python run_server.py --config other.json
"""
import argparse
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--simulate", action="store_true", help="run without cameras")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    from backend import config
    cfg = config.load(args.config)
    if args.simulate:
        cfg["simulate"] = True
    if args.port:
        cfg["port"] = args.port

    os.makedirs(cfg["data_dir"], exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(os.path.join(cfg["data_dir"], "server.log"),
                                                      encoding="utf-8")])
    log = logging.getLogger("aid4sme")
    log.info("Config: %s | data: %s | simulate: %s", cfg["_path"], cfg["data_dir"], cfg["simulate"])

    import uvicorn
    from backend.app import create_app
    app = create_app(cfg)
    log.info("FFmpeg: %s", app.state.ctl.ffmpeg_line)
    log.info("Dashboard: http://localhost:%d", cfg["port"])
    uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_level="warning", access_log=False)


if __name__ == "__main__":
    main()

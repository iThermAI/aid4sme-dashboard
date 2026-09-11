"""HTTP layer. Deliberately thin: every rule lives in controller.py.

Errors are returned as {"detail": "<code>"}; the dashboard translates codes.
"""
import logging
import mimetypes
import os

# Windows can map .js to text/plain in the registry; browsers then refuse to run the dashboard.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config as config_mod
from .controller import Controller, StateError

log = logging.getLogger("aid4sme")


def create_app(cfg):
    ctl = Controller(cfg)
    app = FastAPI(title=config_mod.APP_NAME, version=config_mod.APP_VERSION, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)
    app.state.ctl = ctl

    @app.exception_handler(StateError)
    def _state_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    def _value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    def _key_error(request, exc):
        return JSONResponse({"detail": "not_found"}, status_code=404)

    @app.exception_handler(FileNotFoundError)
    def _missing(request, exc):
        return JSONResponse({"detail": "not_found"}, status_code=404)

    @app.on_event("shutdown")
    def _shutdown():
        ctl.shutdown()

    async def body(request):
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, "invalid_json")
        return data if isinstance(data, dict) else {}

    # ---- status, config, preferences ------------------------------------- #
    @app.get("/api/status")
    def status():
        return ctl.status()

    @app.get("/api/config")
    def public_config():
        return config_mod.public(cfg)

    @app.put("/api/preferences")
    async def put_prefs(request: Request):
        return ctl.set_prefs(await body(request))

    # ---- connection settings --------------------------------------------- #
    @app.get("/api/settings/connections")
    def get_connections():
        return ctl.connection_settings()

    @app.post("/api/settings/connections/test")
    async def test_connection(request: Request):
        return ctl.test_connection(await body(request))

    @app.put("/api/settings/connections")
    async def put_connections(request: Request):
        return ctl.update_connections((await body(request)).get("cameras") or [])

    # ---- cameras ---------------------------------------------------------- #
    @app.get("/api/cameras/{cid}")
    def camera_details(cid: str):
        if ctl.state in ("starting", "recording", "stopping", "verifying"):
            raise StateError("busy_recording")
        return ctl.camera_details(cid)

    @app.post("/api/cameras/check")
    def check_cameras():
        return ctl.check_cameras()

    @app.put("/api/cameras/{cid}/channel-name")
    async def channel_name(cid: str, request: Request):
        data = await body(request)
        if data.get("kind") not in cfg["streams"]:
            raise HTTPException(400, "invalid_stream")
        return ctl.set_channel_name(cid, data["kind"], data.get("name"))

    @app.post("/api/cameras/{cid}/ffc")
    def ffc(cid: str):
        return ctl.trigger_ffc(cid)

    @app.get("/api/cameras/{cid}/backup")
    def backup(cid: str):
        r = ctl.backup_stream(cid)
        if r.status_code != 200:
            r.close()
            raise HTTPException(502, "camera_http_%d" % r.status_code)
        name = "%s_configuration_backup.bin" % cid
        return StreamingResponse(r.iter_content(65536), media_type="application/octet-stream",
                                 headers={"Content-Disposition": 'attachment; filename="%s"' % name})

    @app.get("/api/thermal/{cid}")
    def thermal(cid: str):
        try:
            w, h, data, tmin, tmax = ctl.thermal_matrix(cid)
        except (StateError, KeyError):
            raise
        except Exception as e:  # noqa
            raise HTTPException(502, "matrix_unavailable: %s" % e)
        return Response(data, media_type="application/octet-stream",
                        headers={"X-Width": str(w), "X-Height": str(h), "X-Tmin": "%.2f" % tmin,
                                 "X-Tmax": "%.2f" % tmax, "Cache-Control": "no-store",
                                 "Access-Control-Expose-Headers": "X-Width, X-Height, X-Tmin, X-Tmax"})

    # ---- camera settings profiles ------------------------------------------ #
    @app.get("/api/profiles")
    def profiles():
        return ctl.list_profiles()

    @app.post("/api/profiles")
    async def save_profile(request: Request):
        data = await body(request)
        return {"slug": ctl.save_profile(data.get("name"), data.get("note", ""), bool(data.get("reference")))}

    @app.get("/api/profiles/{slug}/preview")
    def profile_preview(slug: str):
        return ctl.profile_preview(slug)

    @app.post("/api/profiles/{slug}/restore")
    async def restore_profile(slug: str, request: Request):
        data = await body(request)
        return ctl.restore_profile(slug, data.get("cameras") or list(ctl.cameras))

    @app.delete("/api/profiles/{slug}")
    def delete_profile(slug: str):
        ctl.delete_profile(slug)
        return {"ok": True}

    # ---- part presets ------------------------------------------------------ #
    @app.get("/api/parts")
    def parts():
        return ctl.list_parts()

    @app.post("/api/parts")
    async def save_part(request: Request):
        return {"slug": ctl.save_part((await body(request)).get("name")), "draft": ctl.draft}

    @app.post("/api/parts/{slug}/apply")
    def apply_part(slug: str):
        return ctl.apply_part(slug)

    @app.delete("/api/parts/{slug}")
    def delete_part(slug: str):
        ctl.delete_part(slug)
        return {"ok": True}

    # ---- draft -------------------------------------------------------------- #
    @app.get("/api/draft")
    def get_draft():
        return ctl.draft

    @app.put("/api/draft/metadata")
    async def put_metadata(request: Request):
        return ctl.set_metadata(await body(request))

    @app.put("/api/draft/options")
    async def put_options(request: Request):
        return ctl.set_options(await body(request))

    @app.put("/api/draft/regions/{stream}")
    async def put_regions(stream: str, request: Request):
        return ctl.set_regions(stream, (await body(request)).get("regions") or [])

    @app.put("/api/draft/cad")
    async def put_cad(request: Request, filename: str = "model.glb"):
        if ctl.state in ("starting", "recording", "stopping", "verifying"):
            raise StateError("busy_recording")
        chunks = []
        async for chunk in request.stream():
            chunks.append(chunk)
        return ctl.save_cad(filename, chunks)

    @app.get("/api/draft/cad")
    def get_cad():
        if not ctl.draft.get("cad") or not os.path.isfile(ctl.draft_cad_path):
            raise HTTPException(404, "not_found")
        return FileResponse(ctl.draft_cad_path, media_type="model/gltf-binary",
                            headers={"Cache-Control": "no-store"})

    @app.delete("/api/draft/cad")
    def delete_cad():
        return ctl.clear_cad()

    # ---- previews ------------------------------------------------------------ #
    @app.get("/api/preview/{stream}")
    def preview(stream: str):
        try:
            data, ctype = ctl.preview(stream)
        except (StateError, KeyError):
            raise
        except Exception as e:  # noqa - camera unreachable etc.
            raise HTTPException(502, "no_image: %s" % e)
        return Response(data, media_type=ctype, headers={"Cache-Control": "no-store"})

    # ---- recording ------------------------------------------------------------ #
    @app.post("/api/record/start")
    def record_start():
        return {"session_id": ctl.start()}

    @app.post("/api/record/stop")
    def record_stop():
        ctl.stop("operator")
        return {"ok": True}

    @app.post("/api/record/note")
    async def record_note(request: Request):
        return ctl.mark((await body(request)).get("note", ""))

    @app.post("/api/result/acknowledge")
    def acknowledge():
        return ctl.acknowledge()

    # ---- sessions ------------------------------------------------------------- #
    @app.get("/api/sessions")
    def sessions():
        return ctl.list_sessions()

    @app.get("/api/sessions/{sid}")
    def session_detail(sid: str):
        try:
            return ctl.session_detail(sid)
        except (OSError, ValueError):
            raise HTTPException(404, "not_found")

    @app.put("/api/sessions/{sid}/verdict")
    async def verdict(sid: str, request: Request):
        data = await body(request)
        return ctl.set_verdict(sid, data.get("verdict", ""), data.get("reason", ""))

    # ---- dashboard (compiled Vue app) ------------------------------------------ #
    dist = os.path.join(config_mod.ROOT, "frontend", "dist")
    if os.path.isdir(dist):
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:
        @app.get("/")
        def no_ui():
            return Response("<p>The dashboard has not been built yet. See README, section "
                            "'Build the dashboard'. The API is available at /api/docs.</p>",
                            media_type="text/html")
    return app

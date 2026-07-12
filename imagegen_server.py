# imagegen_server.py — minimal Automatic1111-compatible HTTP API.
#
# Lets SillyTavern's built-in Image Generation extension (source="auto",
# pointed at auto_url) generate through this backend the same way it would
# point at a real Automatic1111/Forge instance. SillyTavern's own Node
# backend proxies the browser's request server-to-server to whatever
# auto_url + /sdapi/v1/txt2img is configured — no CORS concerns, no browser
# involved.
#
# Only implements what ST's extension actually needs: POST /sdapi/v1/txt2img
# (required to generate) and GET /sdapi/v1/sd-models (so its model dropdown
# isn't empty). Everything else ST might optionally query (samplers,
# schedulers, upscalers) degrades gracefully to empty lists on ST's side, so
# it's left unimplemented for now.
#
# By default, ignores most of the fine-grained params ST sends (sampler_name,
# steps, cfg_scale, width/height, enable_hr, hr_scale, hr_upscaler, seed) and
# always uses this app's own baked-in generation settings (config.json's sdxl
# block) instead — this backend is a one-button, pre-tuned story-illustration
# generator, not a general SD API surface. Only prompt/negative_prompt are
# honored from the incoming request. Set config.json's sdxl.allow_st_override
# to true to let ST's steps/cfg_scale/width/height/seed/enable_hr/hr_scale/
# denoising_strength take over instead — including ST being able to disable
# the hires-fix pass entirely via enable_hr:false.

import base64
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import imagegen_engine
from constants import SDXL_ALLOW_ST_OVERRIDE, SDXL_API_PORT, SDXL_MODEL_PATH

_OVERRIDE_KEYS = (
    "steps", "cfg_scale", "width", "height", "seed",
    "enable_hr", "hr_scale", "denoising_strength",
)

_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1MB — generous for a JSON prompt payload,
                                    # rejects an oversized/malformed Content-Length
                                    # before buffering it into memory

log = logging.getLogger(__name__)

_server = None
_thread = None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet — avoid spamming stdout for every request

    def _send_json(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/sdapi/v1/sd-models":
            self._send_json(200, [{
                "title": "sdxl-local",
                "model_name": "sdxl-local",
                "hash": None,
                "sha256": None,
                "filename": SDXL_MODEL_PATH,
                "config": None,
            }])
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/sdapi/v1/txt2img":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > _MAX_BODY_BYTES:
                self._send_json(413, {"error": "request body too large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
            prompt = body.get("prompt", "")
            extra_negative = body.get("negative_prompt", "") or ""

            overrides = {}
            if SDXL_ALLOW_ST_OVERRIDE:
                overrides = {
                    k: body[k] for k in _OVERRIDE_KEYS
                    if k in body and body[k] is not None
                }

            out_path = imagegen_engine.with_pipeline(
                lambda pipe, img2img, upscaler, device: imagegen_engine.generate_image(
                    pipe, img2img, upscaler, device, prompt,
                    extra_negative_prompt=extra_negative,
                    **overrides,
                )
            )
            with open(out_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            self._send_json(200, {"images": [b64], "parameters": {}, "info": ""})
        except Exception as e:
            log.error(f"txt2img request failed: {e}")
            self._send_json(500, {"error": str(e)})


def start(port: int = None):
    global _server, _thread
    if _server is not None:
        return
    port = port or SDXL_API_PORT
    _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    log.info(f"Image Gen API listening on http://127.0.0.1:{port}")


def stop():
    global _server, _thread
    if _server is None:
        return
    _server.shutdown()
    _server.server_close()
    _server = None
    _thread = None

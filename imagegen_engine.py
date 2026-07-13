# imagegen_engine.py — shared SDXL pipeline loading/caching.
#
# Used by both ui.py's Start/Stop warm-up (MainWindow) and imagegen_dialog.py's
# Generate button, so the checkpoint/LoRA/TI only ever load once per process
# regardless of which one triggers the load first.
#
# _lock guards every read/write of _pipe_cache. A generation holds the lock
# for its ENTIRE run via with_pipeline() — not just while fetching the
# cached objects — so Stop can never unload out from under an in-flight
# generation, and two callers racing to load can't both do it at once.
# Stop uses a non-blocking acquire (try_unload_pipeline) so it never freezes
# the GUI thread waiting on a long-running generation; it just reports busy.

import datetime
import gc
import logging
import os
import threading

import numpy as np
import torch
from PIL import Image

from constants import (
    SDXL_BASE_HEIGHT, SDXL_BASE_WIDTH, SDXL_CFG_SCALE, SDXL_GENERATION_DEFAULTS,
    SDXL_HIRES_DENOISE, SDXL_HIRES_SCALE, SDXL_LORAS, SDXL_MODEL_PATH,
    SDXL_OUTPUT_DIR, SDXL_SCHEDULER, SDXL_SCHEDULER_CHOICES, SDXL_STEPS,
    SDXL_TEXTUAL_INVERSIONS, SDXL_UPSCALER_PATH,
)

log = logging.getLogger(__name__)

_lock = threading.Lock()
_pipe_cache = {}

# Same ranges the Settings UI's spinboxes enforce (settings_dialog.py's Image
# Gen tab) — applied here too so an untrusted caller (the HTTP server, when
# sdxl.allow_st_override is on) can't bypass them just by not going through
# the widgets. An unbounded `steps` value in particular would hold the global
# pipeline lock for its whole duration, blocking every other caller.
_STEPS_RANGE = (1, 150)
_CFG_SCALE_RANGE = (1.0, 30.0)
_DIMENSION_RANGE = (64, 2048)
_HIRES_SCALE_RANGE = (1.0, 4.0)
_DENOISE_RANGE = (0.0, 1.0)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _to_bool(value, default: bool = True) -> bool:
    """bool() alone treats any non-empty string as True, so a JSON string
    "false" from an HTTP request would otherwise silently mean the opposite
    of what the caller intended."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "no", "0", "")
    return bool(value)


def is_busy() -> bool:
    """True while _lock is held — i.e. a pipeline load or an in-flight
    generation is running. Non-blocking, safe to call from the GUI thread
    (e.g. to warn before quitting mid-generation)."""
    got = _lock.acquire(blocking=False)
    if got:
        _lock.release()
        return False
    return True


# Data-only registry (no diffusers import needed) mapping each scheduler
# preset key to the diffusers class name + from_config() kwargs that build
# it. DPM++ SDE Karras reuses DPMSolverMultistepScheduler's native
# sde-dpmsolver++ algorithm_type rather than DPMSolverSDEScheduler, which
# requires the optional torchsde package we don't otherwise depend on.
#
# This is the single source of truth for valid scheduler keys — validated
# below against SDXL_SCHEDULER_CHOICES (settings_dialog.py's dropdown) at
# import time, so an entry added to one list and forgotten in the other
# fails loudly at startup instead of silently falling back for a real user
# who happens to pick the mismatched key.
_SCHEDULER_REGISTRY = {
    "dpmpp_2m_karras": (
        "DPMSolverMultistepScheduler",
        {"algorithm_type": "dpmsolver++", "use_karras_sigmas": True},
    ),
    "euler_a": ("EulerAncestralDiscreteScheduler", {}),
    "dpmpp_sde_karras": (
        "DPMSolverMultistepScheduler",
        {"algorithm_type": "sde-dpmsolver++", "use_karras_sigmas": True},
    ),
    "unipc": ("UniPCMultistepScheduler", {}),
}

_missing_registry_entries = [
    key for key, _ in SDXL_SCHEDULER_CHOICES if key not in _SCHEDULER_REGISTRY
]
if _missing_registry_entries:
    raise RuntimeError(
        f"SDXL_SCHEDULER_CHOICES references scheduler key(s) with no "
        f"_SCHEDULER_REGISTRY entry in imagegen_engine.py: {_missing_registry_entries}"
    )


def _build_scheduler(config, key: str):
    """Swaps in one of the curated scheduler presets (settings_dialog.py's
    Image Gen tab dropdown). A key not in _SCHEDULER_REGISTRY can only reach
    here from a hand-edited or legacy config.json (every UI-selectable key is
    guaranteed present by the import-time check above), so this falls back
    gracefully rather than raising."""
    default_key = SDXL_GENERATION_DEFAULTS["scheduler"]
    if key not in _SCHEDULER_REGISTRY:
        log.warning(f"Unknown scheduler '{key}', falling back to '{default_key}'")
        key = default_key
    import diffusers
    class_name, kwargs = _SCHEDULER_REGISTRY[key]
    scheduler_cls = getattr(diffusers, class_name)
    return scheduler_cls.from_config(config, **kwargs)


def _load_locked():
    """Populates _pipe_cache. Caller must already hold _lock."""
    from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLPipeline
    from safetensors.torch import load_file
    from spandrel import ModelLoader

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        log.warning(
            "No CUDA GPU detected by torch — SDXL will run on CPU, which is "
            "dramatically slower (minutes instead of seconds per image). If "
            "you have an NVIDIA GPU, torch was likely installed from plain "
            "PyPI instead of the CUDA build: pip install torch --index-url "
            "https://download.pytorch.org/whl/cu130 --force-reinstall"
        )

    pipe = StableDiffusionXLPipeline.from_single_file(
        SDXL_MODEL_PATH, torch_dtype=torch.float16, use_safetensors=True,
    ).to(device)
    pipe.scheduler = _build_scheduler(pipe.scheduler.config, SDXL_SCHEDULER)

    # Only one image is ever generated at a time (the global _lock enforces
    # this), so slicing/tiling the VAE decode costs no real speed but caps
    # its peak VRAM — worth it unconditionally, especially for the
    # hires-fix pass's larger image. channels_last is a free-ish conv
    # speedup on Ada/Ampere GPUs; skip it on the CPU fallback path where it
    # doesn't apply. img2img shares this same unet/vae by reference (built
    # from `unet=pipe.unet, vae=pipe.vae` below), so both settings apply to
    # it automatically without a second call.
    pipe.vae.enable_slicing()
    pipe.vae.enable_tiling()
    if device == "cuda":
        pipe.unet.to(memory_format=torch.channels_last)

    adapter_names = []
    adapter_weights = []
    seen_lora_paths = set()
    for i, lora in enumerate(SDXL_LORAS):
        path = lora.get("path", "")
        if not path or not lora.get("enabled", True):
            continue
        if path in seen_lora_paths:
            log.warning(f"LoRA path is used by more than one row, skipping duplicate: {path}")
            continue
        seen_lora_paths.add(path)
        if os.path.isfile(path):
            name = f"lora_{i}"
            pipe.load_lora_weights(path, adapter_name=name)
            adapter_names.append(name)
            adapter_weights.append(float(lora.get("weight", 1.0)))
        else:
            log.warning(f"LoRA path configured but not found, skipping: {path}")
    if adapter_names:
        pipe.set_adapters(adapter_names, adapter_weights=adapter_weights)

    loaded_ti_tokens_negative = []
    loaded_ti_tokens_positive = []
    seen_tokens = set()
    for ti in SDXL_TEXTUAL_INVERSIONS:
        path = ti.get("path", "")
        token = ti.get("token", "")
        if not path or not token or not ti.get("enabled", True):
            continue
        if token in seen_tokens:
            log.warning(f"Textual inversion token '{token}' is used by more than one row, skipping duplicate: {path}")
            continue
        seen_tokens.add(token)
        if not os.path.isfile(path):
            log.warning(f"Textual inversion path configured but not found, skipping: {path}")
            continue
        try:
            ti_state_dict = load_file(path)
            pipe.load_textual_inversion(
                ti_state_dict["clip_l"], token=token,
                text_encoder=pipe.text_encoder, tokenizer=pipe.tokenizer,
            )
            pipe.load_textual_inversion(
                ti_state_dict["clip_g"], token=token,
                text_encoder=pipe.text_encoder_2, tokenizer=pipe.tokenizer_2,
            )
            if ti.get("target", "negative") == "positive":
                loaded_ti_tokens_positive.append(token)
            else:
                loaded_ti_tokens_negative.append(token)
        except Exception as e:
            log.warning(f"Failed to load textual inversion '{token}' from {path}, skipping: {e}")

    img2img = StableDiffusionXLImg2ImgPipeline(
        vae=pipe.vae, text_encoder=pipe.text_encoder, text_encoder_2=pipe.text_encoder_2,
        tokenizer=pipe.tokenizer, tokenizer_2=pipe.tokenizer_2,
        unet=pipe.unet, scheduler=pipe.scheduler,
    ).to(device)

    upscaler = None
    if SDXL_UPSCALER_PATH:
        if os.path.isfile(SDXL_UPSCALER_PATH):
            upscaler = ModelLoader().load_from_file(SDXL_UPSCALER_PATH).eval().to(device)
        else:
            log.warning(f"Upscaler path configured but not found, skipping: {SDXL_UPSCALER_PATH}")

    _pipe_cache["pipe"] = pipe
    _pipe_cache["img2img"] = img2img
    _pipe_cache["upscaler"] = upscaler
    _pipe_cache["device"] = device
    _pipe_cache["ti_tokens_negative"] = loaded_ti_tokens_negative
    _pipe_cache["ti_tokens_positive"] = loaded_ti_tokens_positive


_OOM_MESSAGE = (
    "Out of GPU memory. Try a smaller resolution, fewer steps, or a lower "
    "hires-fix scale, and close other GPU-heavy apps (e.g. KoboldCpp) if one "
    "is loaded alongside this."
)


def _reclaim_gpu_memory():
    """Clears the fragmented-but-unused memory a failed CUDA allocation
    leaves behind — without this, every generation after an OOM (even at
    sizes that normally fit) would also OOM until this is run. Shared by
    every OOM-recovery path and by the explicit Unload button."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _load_locked_with_reclaim():
    """Wraps _load_locked() so ANY load failure (OOM, or a corrupt/incompatible
    LoRA/upscaler file — the LoRA/upscaler loads aren't try/except-guarded
    inside _load_locked() itself) reclaims GPU memory from the partially-built
    pipeline before propagating. Without this, a bad LoRA file leaks/fragments
    memory on every single retry even though no individual attempt is itself
    an OOM."""
    try:
        _load_locked()
    except torch.cuda.OutOfMemoryError:
        _reclaim_gpu_memory()
        raise RuntimeError(_OOM_MESSAGE) from None
    except Exception:
        _reclaim_gpu_memory()
        raise


def load_pipeline():
    """Blocking load — safe to call from multiple threads; only the first
    actually loads, the rest just wait and then see it already cached."""
    with _lock:
        if "pipe" not in _pipe_cache:
            _load_locked_with_reclaim()


def with_pipeline(fn):
    """Runs fn(pipe, img2img, upscaler, device) while holding _lock for the
    whole call, loading the pipeline first if needed. Use this for anything
    that touches the pipeline objects — never read _pipe_cache directly —
    so a generation can't be unloaded out from under itself mid-run."""
    with _lock:
        if "pipe" not in _pipe_cache:
            _load_locked_with_reclaim()
        try:
            return fn(
                _pipe_cache["pipe"], _pipe_cache["img2img"],
                _pipe_cache["upscaler"], _pipe_cache["device"],
            )
        except torch.cuda.OutOfMemoryError:
            _reclaim_gpu_memory()
            raise RuntimeError(_OOM_MESSAGE) from None


def try_unload_pipeline() -> bool:
    """Non-blocking unload. Returns False without waiting if the lock is
    currently held (e.g. a generation is in progress) instead of freezing
    the caller — intended to be called directly from the GUI thread."""
    if not _lock.acquire(blocking=False):
        return False
    try:
        _pipe_cache.pop("pipe", None)
        _pipe_cache.pop("img2img", None)
        _pipe_cache.pop("upscaler", None)
        _pipe_cache.pop("device", None)
        _pipe_cache.pop("ti_tokens_negative", None)
        _pipe_cache.pop("ti_tokens_positive", None)
        _reclaim_gpu_memory()
        return True
    finally:
        _lock.release()


def esrgan_upscale(image: Image.Image, upscaler, device: str) -> Image.Image:
    arr = np.array(image.convert("RGB")).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        output = upscaler(tensor)
    output = output.squeeze(0).clamp(0, 1).permute(1, 2, 0).cpu().numpy()
    return Image.fromarray((output * 255.0).round().astype("uint8"))


def generate_image(
    pipe, img2img, upscaler, device, prompt: str,
    extra_negative_prompt: str = "", progress_cb=None, step_callback=None,
    cancel_check=None,
    steps=None, cfg_scale=None, width=None, height=None, seed=None,
    enable_hr=None, hr_scale=None, denoising_strength=None,
) -> str:
    """Core txt2img -> ESRGAN upscale -> img2img hires-fix pipeline, shared by
    the dialog's Generate button and the HTTP server. Must be called from
    inside with_pipeline() (or already holding _lock) since it uses the
    pipeline objects directly. Returns the saved output file path.

    step_callback, if given, is passed straight through to diffusers as
    callback_on_step_end (used for cooperative cancellation — see
    imagegen_dialog.py's _ImageGenWorker). cancel_check, if given, is called
    directly (not via diffusers) between the base pass and the hires-fix
    pass — the ESRGAN upscale in between has no per-step hook of its own,
    so without this a cancel requested during upscaling silently waits
    until the entire subsequent hires-fix pass ALSO finishes before it's
    even noticed.

    steps/cfg_scale/width/height/seed/enable_hr/hr_scale/denoising_strength
    default to this app's own config.json settings when left as None — the
    HTTP server only passes real values through when SDXL_ALLOW_ST_OVERRIDE
    is on, so SillyTavern can't affect generation unless that's explicitly
    enabled. enable_hr=False skips the hires-fix pass entirely."""
    def _progress(msg):
        if progress_cb:
            progress_cb(msg)

    steps = SDXL_STEPS if steps is None else _clamp(int(steps), *_STEPS_RANGE)
    cfg_scale = SDXL_CFG_SCALE if cfg_scale is None else _clamp(float(cfg_scale), *_CFG_SCALE_RANGE)
    width = SDXL_BASE_WIDTH if width is None else _clamp(int(width), *_DIMENSION_RANGE) // 8 * 8
    height = SDXL_BASE_HEIGHT if height is None else _clamp(int(height), *_DIMENSION_RANGE) // 8 * 8
    hr_scale = SDXL_HIRES_SCALE if hr_scale is None else _clamp(float(hr_scale), *_HIRES_SCALE_RANGE)
    denoise = SDXL_HIRES_DENOISE if denoising_strength is None else _clamp(float(denoising_strength), *_DENOISE_RANGE)
    run_hires = _to_bool(enable_hr, default=True)

    negative_prompt = "blurry, low quality"
    negative_ti_tokens = _pipe_cache.get("ti_tokens_negative", [])
    if negative_ti_tokens:
        negative_prompt = f"{', '.join(negative_ti_tokens)}, {negative_prompt}"
    if extra_negative_prompt:
        negative_prompt = f"{extra_negative_prompt}, {negative_prompt}"

    positive_ti_tokens = _pipe_cache.get("ti_tokens_positive", [])
    if positive_ti_tokens:
        prompt = f"{', '.join(positive_ti_tokens)}, {prompt}"

    if seed is not None and int(seed) >= 0:
        generator = torch.Generator(device=device).manual_seed(int(seed))
    else:
        generator = torch.Generator(device=device).manual_seed(torch.seed() & 0xFFFFFFFF)

    _progress("Generating...")
    base_image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=cfg_scale,
        generator=generator,
        callback_on_step_end=step_callback,
    ).images[0]

    if not run_hires:
        os.makedirs(SDXL_OUTPUT_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(SDXL_OUTPUT_DIR, f"{stamp}.png")
        base_image.save(out_path)
        return out_path

    if cancel_check:
        cancel_check()

    hires_width = int(width * hr_scale) // 8 * 8
    hires_height = int(height * hr_scale) // 8 * 8

    if upscaler is not None:
        _progress("Upscaling...")
        upscaled = esrgan_upscale(base_image, upscaler, device)
        upscaled = upscaled.resize((hires_width, hires_height), Image.LANCZOS)
    else:
        upscaled = base_image.resize((hires_width, hires_height))

    if cancel_check:
        cancel_check()

    _progress("Hires-fix pass...")
    hires_image = img2img(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=upscaled,
        strength=denoise,
        num_inference_steps=steps,
        guidance_scale=cfg_scale,
        generator=generator,
        callback_on_step_end=step_callback,
    ).images[0]

    os.makedirs(SDXL_OUTPUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(SDXL_OUTPUT_DIR, f"{stamp}.png")
    hires_image.save(out_path)
    return out_path

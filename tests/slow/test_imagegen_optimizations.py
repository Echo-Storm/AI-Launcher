# tests/slow/test_imagegen_optimizations.py — the VAE slicing/tiling and
# channels_last perf settings _load_locked() applies once per real pipeline
# load. cudnn.benchmark was deliberately removed in v1.9.0 (its learned
# per-shape cache never persists across restarts) -- that removal has its
# own fast regression guard in test_imagegen_cancel.py; not re-asserted here.

import pytest
import torch

import imagegen_engine as ie

pytestmark = pytest.mark.slow


def test_vae_slicing_tiling_and_channels_last_apply_to_real_pipeline():
    ie.load_pipeline()
    try:
        pipe = ie._pipe_cache["pipe"]
        img2img = ie._pipe_cache["img2img"]
        device = ie._pipe_cache["device"]

        assert getattr(pipe.vae, "use_slicing", False) is True
        assert getattr(pipe.vae, "use_tiling", False) is True

        assert img2img.vae is pipe.vae, "img2img.vae is not the same object as pipe.vae"
        assert getattr(img2img.vae, "use_slicing", False) is True
        assert getattr(img2img.vae, "use_tiling", False) is True

        if device == "cuda":
            conv_weight = pipe.unet.conv_in.weight
            assert conv_weight.is_contiguous(memory_format=torch.channels_last), \
                "unet conv weights are not in channels_last memory format"
            assert img2img.unet is pipe.unet, "img2img.unet is not the same object as pipe.unet"
    finally:
        assert ie.try_unload_pipeline()
        assert "pipe" not in ie._pipe_cache

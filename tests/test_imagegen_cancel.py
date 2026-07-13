# tests/test_imagegen_cancel.py — negative-prompt wiring, and the Cancel
# gap fix: the ESRGAN upscale step (between the base pass and the
# hires-fix pass) had zero cancellation checkpoint at all, so a cancel
# requested during/around it used to silently wait for the entire
# subsequent hires-fix pass to also finish before it was even noticed.

from PIL import Image as PILImage

import imagegen_dialog as igd
import imagegen_engine as ie


class _FakeResult:
    def __init__(self, img):
        self.images = [img]


def test_cudnn_benchmark_not_set():
    """Regression guard: cudnn.benchmark (added 1.6.0) was deliberately
    removed in 1.9.0 -- its learned per-shape algorithm cache never
    persists across a fresh app launch, so every restart re-pays the
    first-run cost, and worse, that cost lands unpredictably right when a
    user might be trying to cancel. Don't re-add it."""
    src = open("imagegen_engine.py", encoding="utf-8").read()
    assert "cudnn.benchmark" not in src


def test_cancel_check_called_after_base_pass_and_after_upscale(monkeypatch):
    """cancel_check (a plain callable, not a diffusers-signature callback)
    must fire right after the base pass and right after the upscale --
    the two phases generate_image() runs OUTSIDE a diffusers step loop,
    which otherwise has no hook of its own to check cancellation during."""
    calls = []
    real_image = PILImage.new("RGB", (64, 64))

    def fake_pipe(**kwargs):
        calls.append("base_pass")
        return _FakeResult(real_image)

    def fake_img2img(**kwargs):
        calls.append("hires_pass")
        return _FakeResult(real_image)

    def fake_esrgan_upscale(image, upscaler, device):
        calls.append("upscale")
        return image

    def cancel_after_base_and_upscale():
        calls.append("cancel_check")
        if calls.count("cancel_check") == 2:
            raise igd._Cancelled()

    monkeypatch.setattr(ie, "esrgan_upscale", fake_esrgan_upscale)

    raised = False
    try:
        ie.generate_image(
            pipe=fake_pipe, img2img=fake_img2img, upscaler=object(), device="cpu",
            prompt="test", cancel_check=cancel_after_base_and_upscale,
            steps=1, width=64, height=64, hr_scale=1.0,
        )
    except igd._Cancelled:
        raised = True

    assert raised, "cancel_check after upscale did not stop generation before the hires-fix pass"
    assert calls == ["base_pass", "cancel_check", "upscale", "cancel_check"]
    assert "hires_pass" not in calls, "hires-fix pass ran despite a cancel raised right after upscale"


def test_worker_raise_if_cancelled_wired_to_generate_image(qapp, monkeypatch):
    worker = igd.ImageGenWorker("a cat", "blurry")
    captured = {}

    def fake_generate_image(pipe, img2img, upscaler, device, prompt, **kwargs):
        captured.update(kwargs)
        return "fake.png"

    monkeypatch.setattr(ie, "generate_image", fake_generate_image)
    worker._generate(None, None, None, "cpu")

    assert captured.get("cancel_check") == worker._raise_if_cancelled


def test_raise_if_cancelled_raises_after_request_cancel(qapp):
    worker = igd.ImageGenWorker("a cat")
    worker._raise_if_cancelled()  # no-op before cancellation is requested

    worker.request_cancel()
    raised = False
    try:
        worker._raise_if_cancelled()
    except igd._Cancelled:
        raised = True
    assert raised


# --- Negative prompt box (imagegen_dialog.py's manual Generate dialog) ---

def test_negative_prompt_widget_exists(qapp):
    dlg = igd.ImageGenDialog()
    assert hasattr(dlg, "negative_prompt_edit")


def test_on_generate_passes_negative_prompt_to_worker(qapp, monkeypatch):
    dlg = igd.ImageGenDialog()
    dlg.prompt_edit.setPlainText("a cat")
    dlg.negative_prompt_edit.setPlainText("blurry, extra limbs")

    captured = {}

    def fake_start(self):
        captured["prompt"] = self.prompt
        captured["negative_prompt"] = self.negative_prompt

    monkeypatch.setattr(igd.ImageGenWorker, "start", fake_start)
    dlg._on_generate()

    assert captured["prompt"] == "a cat"
    assert captured["negative_prompt"] == "blurry, extra limbs"


def test_busy_state_disables_negative_prompt_box(qapp):
    dlg = igd.ImageGenDialog()
    dlg._set_busy(True)
    assert not dlg.negative_prompt_edit.isEnabled()
    dlg._set_busy(False)
    assert dlg.negative_prompt_edit.isEnabled()


def test_worker_forwards_negative_prompt_as_extra_negative_prompt(qapp, monkeypatch):
    captured = {}

    def fake_generate_image(pipe, img2img, upscaler, device, prompt, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return "fake_path.png"

    monkeypatch.setattr(ie, "generate_image", fake_generate_image)
    worker = igd.ImageGenWorker("a cat", "blurry, extra limbs")
    worker._generate(None, None, None, "cpu")

    assert captured["extra_negative_prompt"] == "blurry, extra limbs"
    assert captured["prompt"] == "a cat"


# --- Progress indicator: _check_cancel also reports per-step progress ---

class _FakePipeWithTimesteps:
    def __init__(self, num_timesteps):
        self.num_timesteps = num_timesteps


def test_check_cancel_emits_step_progress_from_pipe_num_timesteps(qapp):
    worker = igd.ImageGenWorker("a cat")
    seen = []
    worker.step_progress.connect(lambda step, total: seen.append((step, total)))

    worker._check_cancel(_FakePipeWithTimesteps(30), 0, None, {})
    worker._check_cancel(_FakePipeWithTimesteps(30), 5, None, {})

    assert seen == [(1, 30), (6, 30)], "step_progress should report 1-indexed step / real pipe.num_timesteps"


def test_check_cancel_skips_step_progress_when_pipe_has_no_num_timesteps(qapp):
    worker = igd.ImageGenWorker("a cat")
    seen = []
    worker.step_progress.connect(lambda step, total: seen.append((step, total)))

    worker._check_cancel(object(), 0, None, {})  # bare object, no num_timesteps attr

    assert seen == []


def test_check_cancel_still_raises_after_emitting_step_progress(qapp):
    worker = igd.ImageGenWorker("a cat")
    worker.request_cancel()
    raised = False
    try:
        worker._check_cancel(_FakePipeWithTimesteps(30), 0, None, {})
    except igd._Cancelled:
        raised = True
    assert raised, "step_progress emission must not swallow the existing cancel check"


# --- Progress indicator: ImageGenDialog's progress bar ------------------

def test_progress_bar_hidden_until_generation_starts(qapp):
    dlg = igd.ImageGenDialog()
    assert dlg.progress_bar.isVisible() is False


def test_progress_bar_goes_indeterminate_on_each_phase_change(qapp):
    dlg = igd.ImageGenDialog()
    dlg._on_step_progress(15, 30)
    assert dlg.progress_bar.maximum() == 30

    dlg._on_progress("Upscaling...")  # new phase -- no per-step hook of its own
    assert dlg.progress_bar.maximum() == 0, "should go indeterminate until the new phase's steps report in"


def test_progress_bar_becomes_determinate_on_step_progress(qapp):
    dlg = igd.ImageGenDialog()
    dlg._on_step_progress(7, 20)
    assert dlg.progress_bar.minimum() == 0
    assert dlg.progress_bar.maximum() == 20
    assert dlg.progress_bar.value() == 7


def test_progress_bar_hidden_after_done_error_and_cancelled(qapp):
    dlg = igd.ImageGenDialog()

    dlg.progress_bar.setVisible(True)
    dlg._on_done("fake.png")
    assert dlg.progress_bar.isVisible() is False

    dlg.progress_bar.setVisible(True)
    dlg._on_error("boom")
    assert dlg.progress_bar.isVisible() is False

    dlg.progress_bar.setVisible(True)
    dlg._on_cancelled()
    assert dlg.progress_bar.isVisible() is False

# tests/test_settings_gpu_layers_auto.py — regression test for the
# gpu_layers=-1 (auto-detect) round-trip through the Settings dialog.
#
# Real-world bug: the GPU layers QSpinBox originally had range (0, 200) --
# no way to represent KoboldCpp's -1 ("auto-fit layers to available VRAM")
# sentinel. Opening Settings with an auto config populated the spinbox via
# setValue(-1), which Qt silently clamps to the range minimum (0) rather
# than raising or rejecting it. Hitting Save then wrote that clamped 0 back
# to config.json, silently turning "auto-detect" into "offload zero layers
# to GPU" -- a full-CPU-inference regression far worse than the mismatched
# fixed-layer-count bug auto-detect was introduced to fix in the first
# place. Caught live when a real load showed ~2.2GB VRAM used and
# unusably slow generation for a model that should have used ~10GB.

import settings_dialog as sd
from test_settings_lora_ti import _bypass_dialog


def test_gpu_layers_auto_value_survives_populate_unclamped(qapp):
    """The spinbox must actually hold -1 after _populate(), not silently
    clamp it to 0 -- this is the exact failure Qt's default QSpinBox
    range behavior produces when -1 falls below the configured minimum."""
    dlg = _bypass_dialog({"koboldcpp": {"gpu_layers": -1}})
    assert dlg._kob_gpu.value() == -1


def test_gpu_layers_auto_round_trips_through_collect(qapp):
    """The real end-to-end regression: populate with -1, then run the same
    _collect() path _on_save() uses, and confirm -1 comes back -- not 0."""
    dlg = _bypass_dialog({"koboldcpp": {"gpu_layers": -1}})
    dlg._collect()
    assert dlg._cfg["koboldcpp"]["gpu_layers"] == -1


def test_gpu_layers_positive_values_still_work(qapp):
    """Guard against a fix that only special-cases -1 and breaks the
    normal fixed-layer-count path everyone was already relying on."""
    dlg = _bypass_dialog({"koboldcpp": {"gpu_layers": 40}})
    assert dlg._kob_gpu.value() == 40
    dlg._collect()
    assert dlg._cfg["koboldcpp"]["gpu_layers"] == 40


def test_gpu_layers_spinbox_minimum_is_negative_one(qapp):
    """Direct assertion on the widget config itself, so this test fails
    loudly and immediately if the range ever regresses back to (0, 200)
    -- rather than only failing indirectly through the round-trip tests
    above, which a future refactor could accidentally route around."""
    dlg = _bypass_dialog({"koboldcpp": {}})
    assert dlg._kob_gpu.minimum() == -1

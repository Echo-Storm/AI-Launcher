# tests/slow/test_real_cancel_e2e.py — a real generation (base + upscale +
# hires-fix, matching the user's real config) must actually stop within a
# few seconds of request_cancel(), not run to completion or hang. Uses the
# real SDXL pipeline; no mocking, since the thing under test IS the
# cancel_check hook firing during a real pipeline run.

import time

import pytest
from PyQt6.QtCore import QTimer

import imagegen_dialog as igd
import imagegen_engine as ie

pytestmark = pytest.mark.slow


def test_real_generation_actually_stops_on_cancel(qapp):
    ie.load_pipeline()
    try:
        worker = igd.ImageGenWorker("a red apple on a wooden table")

        result = {"done": False, "outcome": None, "elapsed": None}
        start = time.perf_counter()

        def finish(outcome):
            result["done"] = True
            result["outcome"] = outcome
            result["elapsed"] = time.perf_counter() - start
            qapp.quit()

        worker.finished.connect(lambda path: finish("finished"))
        worker.cancelled.connect(lambda: finish("cancelled"))
        worker.error.connect(lambda msg: finish(f"error: {msg}"))

        # Cancel shortly after starting -- well before a full base+upscale+
        # hires-fix run would naturally finish, so this proves cancellation
        # actually interrupts mid-run rather than just returning quickly.
        QTimer.singleShot(2000, worker.request_cancel)
        QTimer.singleShot(30000, lambda: finish("TIMEOUT") if not result["done"] else None)

        worker.start()
        qapp.exec()

        assert result["outcome"] == "cancelled", f"expected 'cancelled', got {result['outcome']}"
        assert result["elapsed"] < 15, f"cancellation took {result['elapsed']:.1f}s, expected well under 15s"
    finally:
        ie.try_unload_pipeline()

# tests/slow/test_ti_target_engine.py — TI target routing ("negative" vs
# "positive") is decided inline inside _load_locked() right next to the
# real pipe.load_textual_inversion() call, so proving it end-to-end means
# actually loading the real SDXL pipeline against the user's real
# config.json / real embedding files on disk (~1 real pipeline load).
#
# Reads whatever textual_inversions are already configured rather than
# mutating config.json -- skips if the fixture this test wants (both a
# negative-target and a positive-target row enabled) isn't present.

import pytest

import constants
import imagegen_engine as ie

pytestmark = pytest.mark.slow


def test_negative_and_positive_ti_tokens_route_to_correct_prompt_slot():
    tis = [t for t in constants.SDXL_TEXTUAL_INVERSIONS if t.get("enabled")]
    neg_row = next((t for t in tis if t.get("target", "negative") == "negative"), None)
    pos_row = next((t for t in tis if t.get("target") == "positive"), None)
    if not neg_row or not pos_row:
        pytest.skip("real config.json needs one enabled negative-target and one enabled positive-target TI row")

    ie.load_pipeline()
    try:
        neg = ie._pipe_cache.get("ti_tokens_negative", [])
        pos = ie._pipe_cache.get("ti_tokens_positive", [])
        assert neg_row["token"] in neg, f"{neg_row['token']!r} not in negative bucket: {neg}"
        assert pos_row["token"] in pos, f"{pos_row['token']!r} not in positive bucket: {pos}"
        assert pos_row["token"] not in neg, f"{pos_row['token']!r} leaked into negative bucket: {neg}"
    finally:
        ie.try_unload_pipeline()

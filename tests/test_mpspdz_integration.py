"""Real three-party SPDZ2k execution of the robust program (opt-in).

Runs only when FL_RUN_MPSPDZ_TESTS=1 and FL_MPSPDZ_HOME points to a built
MP-SPDZ v0.4.3 tree with spdz2k-party.x. Each scenario takes about 15 s.
"""
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FL_RUN_MPSPDZ_TESTS") != "1"
    or not sys.platform.startswith("linux")
    or not (Path(os.environ.get("FL_MPSPDZ_HOME", "/nonexistent")) / "spdz2k-party.x").exists(),
    reason="set FL_RUN_MPSPDZ_TESTS=1 and FL_MPSPDZ_HOME to run real SPDZ2k tests",
)


def test_robust_program_matches_reference_in_real_spdz2k(tmp_path):
    from fl_security.smpc.validation import build_scenarios, run_scenarios

    wanted = {"scaled_replacement_static_clip", "adaptive_clip_screen", "wrap_single_attacker"}
    scenarios = [s for s in build_scenarios(dimension=64) if s.name in wanted]
    results = run_scenarios(scenarios, tmp_path, party_count=3, progress=lambda _: None)
    assert len(results) == 3
    for item in results:
        assert item["mpc_matches_reference_exactly"], item["scenario"]
        assert item["output_check_as_expected"] is not False, item["scenario"]
    by_name = {item["scenario"]: item for item in results}
    assert by_name["adaptive_clip_screen"]["accepted"] == [1, 1, 1, 0]
    assert by_name["wrap_single_attacker"]["output_check_passed"] is False
    assert all(item["party_statistics"][0].get("protocol_seconds") for item in results)

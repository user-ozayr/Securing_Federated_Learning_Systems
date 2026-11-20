"""Mechanical verdicts of the attack/defence matrix."""
from __future__ import annotations

import pandas as pd

from fl_security.experiments.report import matrix


def _runs(study, condition, attack, accuracy, asr=None, seeds=(101, 102, 103)):
    return [{"run_id": f"{study}__{condition}__{attack}__s{seed}", "study": study,
             "condition": condition, "attack": attack, "seed": seed,
             "final_accuracy": accuracy, "last3_mean_accuracy": accuracy,
             **({"final_backdoor_asr": asr} if asr is not None else {})} for seed in seeds]


def _rows(runs):
    return {(r.study, r.condition, r.attack): r for r in matrix(pd.DataFrame(runs)).itertuples()}


E1_REFERENCES = (_runs("e1", "baseline", "none", 0.82, 0.02)
                 + _runs("e1", "baseline", "backdoor", 0.71, 0.92))


def test_low_asr_of_a_ruined_model_is_not_mitigation():
    rows = _rows(E1_REFERENCES + _runs("e1", "mtd_only", "none", 0.83, 0.02)
                 + _runs("e1", "mtd_only", "backdoor", 0.32, 0.30))
    assert rows[("e1", "mtd_only", "backdoor")].verdict == "not mitigated"


def test_halved_asr_without_extra_accuracy_loss_is_partial_mitigation():
    rows = _rows(E1_REFERENCES + _runs("e1", "smpc_clip", "none", 0.83, 0.02)
                 + _runs("e1", "smpc_clip", "backdoor", 0.80, 0.40))
    assert rows[("e1", "smpc_clip", "backdoor")].verdict == "partially mitigated"


def test_destroyed_models_are_marked():
    rows = _rows(E1_REFERENCES + _runs("e1", "baseline", "sign_flip", 0.11, None))
    assert rows[("e1", "baseline", "sign_flip")].model_destroyed == 1
    assert rows[("e1", "baseline", "backdoor")].model_destroyed == 0


def test_missing_references_come_from_the_study_sharing_the_setting_over_the_same_seeds():
    runs = (_runs("e1", "baseline", "none", 0.82, 0.02)
            + _runs("e1x", "smpc_defence", "none", 0.824, 0.02)
            + _runs("e4", "baseline", "backdoor__boost8", 0.10, 0.50, seeds=(101, 102))
            + _runs("e4", "reference_defence", "backdoor__boost8", 0.817, 0.024, seeds=(101, 102)))
    result = _rows(runs)[("e4", "reference_defence", "backdoor__boost8")]
    assert result.verdict == "mitigated"
    assert result.clean_reference == "e1x/smpc_defence/none (seeds 101,102)"
    assert result.baseline_reference == "e4/baseline/backdoor__boost8 (seeds 101,102)"
    assert result.baseline_clean_reference == "e1/baseline/none (seeds 101,102)"


def test_default_setting_of_a_sweep_uses_the_unmodified_attack_as_reference():
    runs = (E1_REFERENCES + _runs("e1x", "smpc_defence", "none", 0.824, 0.02)
            + _runs("e4", "reference_defence", "backdoor__default", 0.817, 0.024, seeds=(101, 102)))
    result = _rows(runs)[("e4", "reference_defence", "backdoor__default")]
    assert result.baseline_reference == "e1/baseline/backdoor (seeds 101,102)"
    assert result.verdict == "mitigated"


def test_clean_runs_with_a_setting_suffix_are_recognised():
    seeds = (101, 102)
    runs = (_runs("e5", "baseline", "none__dir05", 0.78, 0.02, seeds)
            + _runs("e5", "baseline", "backdoor__dir05", 0.51, 0.49, seeds)
            + _runs("e5", "smpc_defence_mtd", "none__dir05", 0.79, 0.016, seeds)
            + _runs("e5", "smpc_defence_mtd", "backdoor__dir05", 0.763, 0.003, seeds))
    rows = _rows(runs)
    assert rows[("e5", "smpc_defence_mtd", "none__dir05")].verdict == "not applicable"
    result = rows[("e5", "smpc_defence_mtd", "backdoor__dir05")]
    assert result.clean_reference == "e5/smpc_defence_mtd/none__dir05 (seeds 101,102)"
    assert result.verdict == "partially mitigated"

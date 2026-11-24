"""Scenario validation of the robust SPDZ2k program against exact references.

Every scenario runs the real MP-SPDZ SPDZ2k program on local party services
with synthetic client inputs and checks that:

* every revealed value equals :func:`robust_reference` bit for bit;
* the decoded aggregate is close to an ideal floating-point clipping reference
  (the difference is fixed-point rounding plus floor-rounded clip coefficients);
* the plaintext output check behaves as analysed for malformed inputs.

Adversarial scenarios use raw ring elements, which the normal float encoder
refuses, to emulate a client that deviates from the encoding.
"""
from __future__ import annotations

import json
import math
import os
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from fl_security.smpc import mp_spdz
from fl_security.smpc.robust import (
    RING_MODULUS,
    SecureDefenceConfig,
    chunked_wire_values,
    decode_robust_output,
    robust_reference,
    to_signed,
)


@dataclass
class Scenario:
    name: str
    description: str
    config: SecureDefenceConfig
    counts: list[int]
    # integer inputs at scale 2^f, one row per client (sorted client order)
    inputs: list[list[int]]
    expect_output_check: bool = True
    weights_override: list[int] | None = None
    notes: dict = field(default_factory=dict)
    # direction screen: {"min_agree": int, "indices": [...]} or None
    direction: dict | None = None
    expected_direction_failed: list[int] | None = None


def _vector(norm: float, dimension: int, scale: int, rng: random.Random, sign: float = 1.0) -> list[int]:
    raw = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
    length = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [int(round(sign * norm * v / length * scale)) for v in raw]


def _ideal_reference(scenario: Scenario, weights: list[int], threshold_norm: float,
                     direction_failed: list[int] | None = None) -> list[float]:
    """Floating-point clipping/screening on the decoded honest-format inputs."""
    cfg = scenario.config
    scale = float(cfg.scale)
    rows = [[to_signed(v) / scale for v in row] for row in scenario.inputs]
    norms = [math.sqrt(sum(v * v for v in row)) for row in rows]
    rho = math.sqrt(cfg.screen_multiplier_squared)
    total = [0.0] * len(rows[0])
    accepted_weight = 0
    failed = direction_failed or [0] * len(rows)
    for row, norm, weight, dropped in zip(rows, norms, weights, failed):
        if norm > cfg.max_valid_norm or dropped:
            continue
        if cfg.screen_enabled and norm > rho * threshold_norm:
            continue
        factor = min(1.0, threshold_norm / norm) if (cfg.clip_enabled and norm > 0) else 1.0
        accepted_weight += weight
        for j, value in enumerate(row):
            total[j] += weight * factor * value
    if accepted_weight == 0:
        return [0.0] * len(total)
    return [value / accepted_weight for value in total]


def build_scenarios(dimension: int = 300, seed: int = 7) -> list[Scenario]:
    rng = random.Random(seed)
    static_clip = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0)
    adaptive = SecureDefenceConfig(
        mode="clip_screen", threshold="adaptive", median_multiplier_squared=1,
        screen_multiplier_squared=4, min_norm=0.05, max_norm=4.0,
    )
    screen = SecureDefenceConfig(
        mode="screen", threshold="adaptive", median_multiplier_squared=1,
        screen_multiplier_squared=4, min_norm=0.05, max_norm=4.0,
    )
    weighted = SecureDefenceConfig(
        mode="clip", threshold="static", static_norm=1.0, weighting="sample", weight_bits=3,
    )
    s = static_clip.scale
    honest = lambda *norms: [_vector(n, dimension, s, rng) for n in norms]  # noqa: E731
    scenarios = [
        Scenario("clean_static_clip", "four honest updates below the static bound",
                 static_clip, [500] * 4, honest(0.3, 0.5, 0.7, 0.9)),
        Scenario("scaled_replacement_static_clip",
                 "three honest updates and one update boosted to norm 25",
                 static_clip, [500] * 4, honest(0.5, 0.6, 0.7) + [_vector(25.0, dimension, s, rng)]),
        Scenario("boundary_static_clip", "norm exactly at the bound, zero, tiny and 1.5x bound",
                 static_clip, [500] * 4,
                 [_vector(1.0, dimension, s, rng), [0] * dimension,
                  _vector(1e-4, dimension, s, rng), _vector(1.5, dimension, s, rng)]),
        Scenario("adaptive_clip_screen",
                 "median-based threshold; norm-10 attacker rejected, honest above median clipped",
                 adaptive, [500] * 4, honest(0.4, 0.5, 0.6) + [_vector(10.0, dimension, s, rng)]),
        Scenario("adaptive_screen_only", "median screening without clipping",
                 screen, [500] * 4, honest(0.4, 0.5, 0.6) + [_vector(10.0, dimension, s, rng)]),
        Scenario("sample_weighted_clip", "quantized sample weights with one boosted update",
                 weighted, [1000, 2000, 3000, 6000],
                 honest(0.5, 0.5, 0.5) + [_vector(8.0, dimension, s, rng)]),
    ]

    out_of_range = honest(0.5, 0.6, 0.7) + [_vector(0.5, dimension, s, rng)]
    out_of_range[3][0] = 1 << 27  # square 2^54 > r_max, no wrap: input invalid
    scenarios.append(Scenario(
        "malformed_out_of_range", "one coordinate 2^27 (norm > max_valid_norm): input invalid",
        static_clip, [500] * 4, out_of_range))

    wrap40 = honest(0.5, 0.6, 0.7) + [_vector(0.5, dimension, s, rng)]
    wrap40[3][0] = 1 << 40  # square 2^80 = 0 mod 2^64: looks valid inside MPC
    scenarios.append(Scenario(
        "wrap_large_coordinate", "coordinate 2^40 squares to 0 mod 2^64; caught by output check",
        static_clip, [500] * 4, wrap40, expect_output_check=False))

    negative = honest(0.5, 0.6, 0.7) + [[0] * dimension]
    negative[3][0] = 3 << 30  # (3*2^30)^2 = 2^63 + 2^60 -> negative squared norm
    scenarios.append(Scenario(
        "malformed_negative_square", "squared norm wraps to a negative value: input invalid",
        static_clip, [500] * 4, negative))

    wrap = honest(0.5, 0.6, 0.7) + [_vector(0.2, dimension, s, rng)]
    wrap[3][0] = 1 << 32  # (2^32)^2 = 0 mod 2^64: the norm check sees ~0.2
    scenarios.append(Scenario(
        "wrap_single_attacker",
        "coordinate 2^32 squares to 0 mod 2^64; accepted in MPC, caught by output check",
        static_clip, [500] * 4, wrap, expect_output_check=False))

    # Inverse-weight attack: with an odd public weight w the attacker submits
    # x = D * w^-1 so that the visible contribution w*x equals a chosen D.
    counts = [3000, 3000, 3000, 1000]
    target_norm = 5.0
    weights = weighted.quantized_weights(counts)
    odd = weights[3]
    inverse = pow(odd, -1, RING_MODULUS)
    target = _vector(target_norm, dimension, s, rng)
    crafted = [(value * inverse) % RING_MODULUS for value in target]
    naive = sum(v * v for v in crafted) % RING_MODULUS
    scenarios.append(Scenario(
        "inverse_weight_trick",
        "odd weight; visible contribution D=w*x has norm 5; decisions use ||w*x||",
        weighted, counts, honest(0.5, 0.5, 0.5) + [crafted],
        notes={"attacker_weight": odd, "naive_unweighted_squared_norm_signed": to_signed(naive),
               "visible_target_norm": target_norm}))

    # Two colluders cancel a 2^32-multiple component: B = 2^32 * b, x_A = B,
    # x_B = delta - B. Both squared norms are small modulo 2^64.
    for clients in (4, 8):
        cfg = SecureDefenceConfig(mode="clip", threshold="static", static_norm=1.0)
        honest_rows = [_vector(0.5, dimension, s, rng) for _ in range(clients - 2)]
        delta, b_coefficient = _colluding_delta(dimension, s, rng)
        big = [0] * dimension
        big[0] = (b_coefficient << 32) % RING_MODULUS
        x_a = big
        x_b = [(d - v) % RING_MODULUS for d, v in zip(delta, big)]
        delta_norm = math.sqrt(sum(v * v for v in delta)) / s
        scenarios.append(Scenario(
            f"colluding_cancellation_k{clients}",
            f"two colluders inject a norm-{delta_norm:.2f} update (bound 1.0) via cancelling 2^32 multiples",
            cfg, [500] * clients, honest_rows + [x_a, x_b],
            expect_output_check=None, notes={"injected_norm": delta_norm}))
    scenarios.extend(build_direction_scenarios(dimension, rng))
    return scenarios


def build_direction_scenarios(dimension: int, rng: random.Random) -> list[Scenario]:
    """Scenarios for the direction screen (sign agreement on a coordinate subset)."""
    cfg = SecureDefenceConfig(
        mode="clip_screen", threshold="adaptive", median_multiplier_squared=1,
        screen_multiplier_squared=4, min_norm=0.05, max_norm=4.0,
        direction_check=True, direction_subset="secret", direction_fraction=0.25,
        direction_min_agreement=0.5,
    )
    s = cfg.scale
    subset = sorted(rng.sample(range(dimension), max(1, dimension // 4)))
    spec = {"min_agree": cfg.min_agreement_count(len(subset)), "indices": subset}
    common = [rng.gauss(0.0, 1.0) for _ in range(dimension)]

    def aligned(norm: float, noise: float = 0.6, sign: float = 1.0) -> list[int]:
        """An update along a shared direction plus individual noise (honest-like)."""
        raw = [c + noise * rng.gauss(0.0, 1.0) for c in common]
        length = math.sqrt(sum(v * v for v in raw)) or 1.0
        return [int(round(sign * norm * v / length * s)) for v in raw]

    malformed = aligned(0.5, sign=-1.0)
    for position, j in enumerate(subset[:12]):
        # values beyond the 32-bit sign test: 2^31, 2^40 (+/-), ring negatives
        malformed[j] = [1 << 31, (1 << 40) + 5, -(1 << 40), RING_MODULUS - 7][position % 4]
    whole = {"min_agree": cfg.min_agreement_count(dimension), "indices": list(range(dimension))}
    k3 = {"min_agree": spec["min_agree"], "indices": subset}
    eight = [aligned(0.5) for _ in range(6)] + [aligned(0.5, sign=-1.0) for _ in range(2)]
    return [
        Scenario("direction_honest", "four aligned honest updates: none rejected by direction",
                 cfg, [500] * 4, [aligned(n) for n in (0.4, 0.5, 0.6, 0.55)],
                 direction=spec, expected_direction_failed=[0, 0, 0, 0]),
        Scenario("direction_sign_flip",
                 "three aligned honest updates and one sign-flipped update of honest norm",
                 cfg, [500] * 4, [aligned(n) for n in (0.4, 0.5, 0.6)] + [aligned(0.5, sign=-1.0)],
                 direction=spec, expected_direction_failed=[0, 0, 0, 1]),
        Scenario("direction_and_norm",
                 "one boosted update (norm screen) and one flipped update (direction screen)",
                 cfg, [500] * 5,
                 [aligned(n) for n in (0.4, 0.5, 0.6)] + [aligned(10.0), aligned(0.5, sign=-1.0)],
                 direction=spec, expected_direction_failed=[0, 0, 0, 0, 1]),
        Scenario("direction_malformed_signs",
                 "flipped update with ring values beyond 32 bits on checked coordinates",
                 cfg, [500] * 4, [aligned(n) for n in (0.4, 0.5, 0.6)] + [malformed],
                 direction=spec, expect_output_check=None),
        Scenario("direction_all_coordinates", "every coordinate checked",
                 cfg, [500] * 4, [aligned(n) for n in (0.4, 0.5, 0.6)] + [aligned(0.5, sign=-1.0)],
                 direction=whole, expected_direction_failed=[0, 0, 0, 1]),
        Scenario("direction_three_clients_ties",
                 "K = 3: two others, ties resolve to non-negative",
                 cfg, [500] * 3, [aligned(0.5), aligned(0.5), aligned(0.5, sign=-1.0)],
                 direction=k3),
        Scenario("direction_k8_two_flipped",
                 "K = 8 with two flipped updates: both are a minority and rejected",
                 cfg, [500] * 8, eight, direction=spec,
                 expected_direction_failed=[0] * 6 + [1, 1]),
    ]


def _colluding_delta(dimension: int, scale: int, rng: random.Random) -> tuple[list[int], int]:
    """Find delta and b with ||delta||^2 - 2^33*b*delta_0 small modulo 2^64.

    With B = 2^32*b*e_0 we have ||B||^2 = 0 and ||delta - B||^2 =
    ||delta||^2 - 2^33*b*delta_0 (mod 2^64). Choosing ||delta||^2 = m*2^33 + r
    with small r and b = m * delta_0^-1 (mod 2^31) makes both inputs pass a
    per-client bound r <= T, although delta itself is far larger than the bound.
    """
    window = min((1 << 27), int(1.0 * scale) ** 2 // 2)
    target = (1 << 33) + window // 2
    direction = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
    length = math.sqrt(sum(v * v for v in direction))
    base = [int(round(v / length * math.sqrt(target))) for v in direction]
    for tweak in range(0, 1_000_000):
        for sign in (1, -1):
            candidate = list(base)
            candidate[0] += sign * tweak
            if candidate[0] % 2 == 0:
                continue
            norm2 = sum(v * v for v in candidate)
            residue = norm2 % (1 << 33)
            if norm2 >= (1 << 33) and residue <= window:
                m = (norm2 - residue) >> 33
                b = (m * pow(candidate[0], -1, 1 << 31)) % (1 << 31)
                return candidate, b
    raise RuntimeError("could not construct a colluding input")


def run_scenarios(
    scenarios: list[Scenario],
    output_dir: Path,
    *,
    party_count: int = 3,
    progress: Callable[[str], None] = print,
) -> list[dict]:
    from fl_security.smpc.local_demo import local_spdz2k_environment

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    max_clients = max(len(s.inputs) for s in scenarios)
    with local_spdz2k_environment(party_count, max_clients, keep_logs_in=output_dir / "party_logs"):
        parties = mp_spdz.load_party_configuration(party_count)
        hosts = [party.client_host for party in parties]
        port = mp_spdz.client_port_base()
        credentials = os.environ["FL_MPSPDZ_CLIENT_CREDENTIALS_DIR"]
        home = os.environ["FL_MPSPDZ_HOME"]
        for scenario in scenarios:
            progress(f"[validation] {scenario.name}")
            results.append(_run_one(scenario, parties, hosts, port, credentials, home, max_clients))
            (output_dir / "scenario_results.json").write_text(
                json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    return results


def _run_one(scenario, parties, hosts, port, credentials, home, output_client_id) -> dict:
    cfg = scenario.config
    client_count = len(scenario.inputs)
    dimension = len(scenario.inputs[0])
    client_ids = list(range(client_count))
    weights = scenario.weights_override or cfg.quantized_weights(scenario.counts)
    spec = cfg.round_spec(weights)
    direction = scenario.direction
    if direction is not None:
        reference = robust_reference(scenario.inputs, weights, spec,
                                     direction_indices=direction["indices"],
                                     min_agree=direction["min_agree"])
    else:
        reference = robust_reference(scenario.inputs, weights, spec)
    round_id = f"validate-{scenario.name}-{uuid.uuid4().hex[:16]}"
    started = time.perf_counter()
    mp_spdz.start_round(
        parties, round_id, client_ids, dimension + 1, scenario.counts, output_client_id, port,
        program="robust_aggregate", weights=weights, robust_spec=spec, chunk_size=cfg.chunk_size,
        direction=direction,
    )
    try:
        for cid, row, count in zip(client_ids, scenario.inputs, scenario.counts):
            wire = chunked_wire_values(count, [to_signed(v) for v in row], cfg.chunk_size)
            mp_spdz.submit_wire_values(
                wire, cid, hosts=hosts, port_base=port, credentials_dir=credentials,
                mp_spdz_home=home, chunk_size=cfg.chunk_size,
            )
        mpc = mp_spdz.receive_robust_result(
            hosts=hosts, port_base=port, credentials_dir=credentials, mp_spdz_home=home,
            output_client_id=output_client_id, client_count=client_count, dimension=dimension,
            direction=direction is not None,
        )
        statistics = mp_spdz.finish_round(parties, round_id)
    except BaseException:
        try:
            mp_spdz.abort_round(parties, round_id)
        except Exception:
            pass
        raise
    elapsed = time.perf_counter() - started
    decoded = decode_robust_output(mpc, weights, cfg)
    reference_decoded = decode_robust_output(reference, weights, cfg)
    exact = (
        mpc.threshold_squared == reference.threshold_squared
        and mpc.clipped_count == reference.clipped_count
        and mpc.accepted == reference.accepted
        and mpc.clip_flags == reference.clip_flags
        and mpc.totals == reference.totals
        and mpc.direction_failed == reference.direction_failed
    )
    ideal = _ideal_reference(scenario, weights, decoded.threshold_norm,
                             reference.direction_failed or None)
    ideal_error = max(abs(a - b) for a, b in zip(decoded.delta.tolist(), ideal))
    expected_check = scenario.expect_output_check
    expected_direction = scenario.expected_direction_failed
    return {
        "direction_subset_size": len(direction["indices"]) if direction else 0,
        "direction_min_agree": direction["min_agree"] if direction else None,
        "direction_failed": mpc.direction_failed,
        "reference_agreement": reference.agreement,
        "direction_as_expected": (
            None if expected_direction is None else mpc.direction_failed == expected_direction),
        "scenario": scenario.name,
        "description": scenario.description,
        "config": asdict(cfg),
        "clients": client_count,
        "dimension": dimension,
        "weights": weights,
        "spec": spec,
        "mpc_matches_reference_exactly": bool(exact),
        "threshold_norm": decoded.threshold_norm,
        "accepted": mpc.accepted,
        "clip_flags": mpc.clip_flags,
        "clipped_count": mpc.clipped_count,
        "reference_coefficients": reference.coefficients,
        "aggregate_norm": decoded.aggregate_norm,
        "output_check_passed": decoded.output_check_passed,
        "expected_output_check": expected_check,
        "output_check_as_expected": (
            None if expected_check is None else decoded.output_check_passed == expected_check
        ),
        "reference_output_check_passed": reference_decoded.output_check_passed,
        "max_abs_error_vs_ideal_float_clipping": ideal_error,
        "end_to_end_seconds": elapsed,
        "party_statistics": statistics,
        "notes": scenario.notes,
    }

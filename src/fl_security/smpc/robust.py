"""Configuration, encoding and exact reference for robust SPDZ2k aggregation.

The secure computation is implemented in ``programs/spdz2k_robust_aggregate.mpc``.
This module holds everything the coordinator and the clients need around it:

* :class:`SecureDefenceConfig` turns real-valued defence settings into the
  integer round specification and validates the 2^62 bit budget;
* :func:`encode_delta` encodes a client's model update at scale ``2^f``;
* :func:`robust_reference` is an exact integer re-implementation of the MPC
  program (modulo 2^64, 63-bit comparisons) used to verify SPDZ2k results;
* :func:`decode_robust_output` decodes the revealed vector and performs the
  plaintext aggregate-norm check that bounds the effect of malformed inputs.

All decisions inside MPC are made on the squared norm of the contribution that
actually enters the sum. See docs/secure_robust_aggregation.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import torch

RING_BITS = 64
RING_MODULUS = 1 << RING_BITS
BIT_BUDGET = 1 << 62
WRAP_NORM = 1 << 31  # sqrt(2^62): smallest visible norm whose square may be misjudged
SPEC_LENGTH = 13
VALID_MODES = ("clip", "screen", "clip_screen")
VALID_THRESHOLDS = ("static", "adaptive")
VALID_WEIGHTING = ("uniform", "sample")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def to_signed(value: int) -> int:
    """Signed representative of a ring element in [-2^63, 2^63)."""
    value %= RING_MODULUS
    return value - RING_MODULUS if value >= RING_MODULUS // 2 else value


def _lt(left: int, right: int) -> int:
    """Emulate MP-SPDZ's ``sint < sint`` with the default bit length (63 + 1).

    MP-SPDZ computes LessThanZero(left - right, 64), i.e. the sign bit of the
    64-bit ring difference. For honest values (|values| < 2^62) this equals the
    integer comparison; for malformed inputs it is still this exact function.
    """
    return 1 if (left - right) % RING_MODULUS >= RING_MODULUS // 2 else 0


def _le(left: int, right: int) -> int:
    return 1 - _lt(right, left)


@dataclass(frozen=True)
class SecureDefenceConfig:
    """Real-valued settings of the in-MPC norm defence.

    Norms are L2 norms of model updates (``w_local - w_global``) in model units.
    """

    mode: str = "clip"
    threshold: str = "static"
    static_norm: float = 1.0
    min_norm: float = 0.05
    max_norm: float = 4.0
    median_multiplier_squared: int = 1
    screen_multiplier_squared: int = 4
    max_valid_norm: float = 64.0
    fractional_bits: int = 14
    clip_bits: int = 6
    weighting: str = "uniform"
    weight_bits: int = 3
    reveal_client_flags: bool = True
    chunk_size: int = 256
    output_margin: float = 4.0
    use_edabits: bool = False

    def __post_init__(self) -> None:
        if self.mode not in VALID_MODES:
            raise ValueError(f"secure defence mode must be one of {VALID_MODES}")
        if self.threshold not in VALID_THRESHOLDS:
            raise ValueError(f"secure defence threshold must be one of {VALID_THRESHOLDS}")
        if self.weighting not in VALID_WEIGHTING:
            raise ValueError(f"secure defence weighting must be one of {VALID_WEIGHTING}")
        for name in ("static_norm", "min_norm", "max_norm", "max_valid_norm", "output_margin"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not self.min_norm <= self.max_norm <= self.max_valid_norm:
            raise ValueError("require min_norm <= max_norm <= max_valid_norm")
        if not self.min_norm <= self.static_norm <= self.max_valid_norm:
            raise ValueError("static_norm must lie in [min_norm, max_valid_norm]")
        for name, low, high in (
            ("median_multiplier_squared", 1, 64),
            ("screen_multiplier_squared", 1, 1024),
            ("fractional_bits", 4, 20),
            ("clip_bits", 1, 16),
            ("weight_bits", 0, 8),
            ("chunk_size", 16, 4096),
        ):
            value = getattr(self, name)
            if not _is_int(value) or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")
        if not isinstance(self.reveal_client_flags, bool):
            raise ValueError("reveal_client_flags must be a boolean")
        if not isinstance(self.use_edabits, bool):
            raise ValueError("use_edabits must be a boolean")
        if self.output_margin < 2:
            raise ValueError("output_margin must be at least 2")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object] | None) -> "SecureDefenceConfig":
        raw = dict(raw or {})
        raw.pop("enabled", None)
        allowed = set(cls.__dataclass_fields__)
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown secure defence settings: {sorted(unknown)}")
        return cls(**raw)

    # ---- integer parameters -------------------------------------------------
    @property
    def scale(self) -> int:
        return 1 << self.fractional_bits

    @property
    def clip_enabled(self) -> bool:
        return self.mode in ("clip", "clip_screen")

    @property
    def screen_enabled(self) -> bool:
        return self.mode in ("screen", "clip_screen")

    def squared(self, norm: float) -> int:
        return int(round(float(norm) ** 2 * self.scale * self.scale))

    def quantized_weights(self, sample_counts: Sequence[int]) -> list[int]:
        if not sample_counts or any(not _is_int(c) or c <= 0 for c in sample_counts):
            raise ValueError("sample counts must be positive integers")
        if self.weighting == "uniform" or self.weight_bits == 0:
            return [1] * len(sample_counts)
        top = 1 << self.weight_bits
        largest = max(sample_counts)
        weights = [max(1, min(top, int(round(top * c / largest)))) for c in sample_counts]
        divisor = 0
        for weight in weights:
            divisor = math.gcd(divisor, weight)
        return [weight // divisor for weight in weights]

    def round_spec(self, weights: Sequence[int]) -> list[int]:
        """Integer specification passed to the MPC program, after validation."""
        if not weights or any(not _is_int(w) or w <= 0 for w in weights):
            raise ValueError("weights must be positive integers")
        max_weight_bits = max(0, max(weights).bit_length() if max(weights) > 1 else 0)
        if max(weights) > (1 << max(self.weight_bits, max_weight_bits)):
            raise ValueError("weights exceed the configured weight bits")
        spec = [
            int(self.clip_enabled),
            int(self.screen_enabled),
            int(self.threshold == "adaptive"),
            self.squared(self.static_norm),
            self.squared(self.min_norm),
            self.squared(self.max_norm),
            int(self.median_multiplier_squared),
            int(self.screen_multiplier_squared),
            int(self.clip_bits),
            self.squared(self.max_valid_norm),
            int(self.reveal_client_flags),
            max(self.weight_bits, max_weight_bits),
            int(self.use_edabits),
        ]
        validate_spec(spec, weights)
        self.validate_output_margin(weights)
        return spec

    def output_bound(self, threshold_squared: int) -> int:
        """Squared decoded-norm bound (units 2^(2f)) that every aggregate must meet."""
        if self.clip_enabled:
            return int(threshold_squared)
        return int(threshold_squared) * int(self.screen_multiplier_squared)

    def validate_output_margin(self, weights: Sequence[int]) -> None:
        """Ensure a single malformed (wrapping) contribution is detectably absurd."""
        total_weight = sum(int(w) for w in weights)
        bound_norm = math.sqrt(self.output_bound(self.squared(self.max_norm))) / self.scale
        if self.threshold == "static":
            bound_norm = math.sqrt(self.output_bound(self.squared(self.static_norm))) / self.scale
        wrap_decoded = WRAP_NORM / ((1 << self.clip_bits) * self.scale * total_weight)
        if wrap_decoded < self.output_margin * 2 * bound_norm:
            raise ValueError(
                "secure defence parameters leave too little margin between honest "
                "aggregates and malformed wrapping inputs; lower fractional_bits, "
                "clip_bits, weight_bits or max_norm"
            )


def validate_spec(spec: Sequence[int], weights: Sequence[int]) -> None:
    """Mirror of the program's argument and bit-budget checks."""
    if len(spec) != SPEC_LENGTH or any(not _is_int(value) for value in spec):
        raise ValueError("robust specification must contain 13 integers")
    (
        clip, screen, adaptive, static_t, t_min, t_max, lambda2, rho2,
        clip_bits, r_max, reveal, max_weight_bits, options,
    ) = spec
    if clip not in (0, 1) or screen not in (0, 1) or adaptive not in (0, 1) or reveal not in (0, 1):
        raise ValueError("robust specification flags must be 0 or 1")
    if clip + screen == 0:
        raise ValueError("at least one of clipping and screening must be enabled")
    if not 1 <= clip_bits <= 16 or options not in (0, 1):
        raise ValueError("invalid clip bits or options field")
    if not 0 < t_min <= t_max <= r_max or not 0 < static_t <= r_max:
        raise ValueError("thresholds must satisfy 0 < t_min <= t_max <= r_max")
    if lambda2 <= 0 or rho2 <= 0 or r_max >= BIT_BUDGET:
        raise ValueError("invalid multipliers or validity bound")
    if any(not _is_int(w) or w <= 0 or w > (1 << max_weight_bits) for w in weights):
        raise ValueError("weights exceed the declared weight bits")
    one_g = 1 << clip_bits
    w2 = max(weights) ** 2
    if (
        r_max * w2 * one_g * one_g >= BIT_BUDGET
        or r_max * lambda2 >= BIT_BUDGET
        or t_max * w2 * one_g * one_g >= BIT_BUDGET
        or t_max * w2 * rho2 >= BIT_BUDGET
        or static_t * w2 * rho2 >= BIT_BUDGET
    ):
        raise ValueError("robust specification exceeds the 2^62 bit budget")


def round_arguments(
    client_ids: Sequence[int],
    expected_counts: Sequence[int],
    weights: Sequence[int],
    input_count: int,
    output_client_id: int,
    port_base: int,
    chunk_size: int,
    spec: Sequence[int],
) -> list[str]:
    """The eight string arguments of the robust MPC program (sorted by client ID)."""
    order = sorted(range(len(client_ids)), key=lambda index: client_ids[index])
    return [
        ",".join(str(int(client_ids[i])) for i in order),
        ",".join(str(int(expected_counts[i])) for i in order),
        ",".join(str(int(weights[i])) for i in order),
        str(int(input_count)),
        str(int(output_client_id)),
        str(int(port_base)),
        str(int(chunk_size)),
        ",".join(str(int(value)) for value in spec),
    ]


# ---- client encoding ------------------------------------------------------------
def flatten_delta(
    local_state: Mapping[str, torch.Tensor],
    global_state: Mapping[str, torch.Tensor],
) -> torch.Tensor:
    parts = []
    for key, base in global_state.items():
        if not torch.is_floating_point(base):
            continue
        local = local_state[key].detach().cpu().to(torch.float64)
        if local.shape != base.shape:
            raise ValueError(f"tensor shape mismatch for {key!r}")
        parts.append((local - base.detach().cpu().to(torch.float64)).reshape(-1))
    if not parts:
        raise ValueError("model state contains no floating-point parameters")
    return torch.cat(parts)


def encode_delta(
    local_state: Mapping[str, torch.Tensor],
    global_state: Mapping[str, torch.Tensor],
    fractional_bits: int,
) -> list[int]:
    """Encode ``local - global`` as signed integers at scale 2^f."""
    delta = flatten_delta(local_state, global_state)
    if not torch.isfinite(delta).all():
        raise ValueError("model update contains NaN or infinite values")
    scaled = torch.round(delta * float(1 << fractional_bits))
    if torch.any(torch.abs(scaled) >= float(1 << 62)):
        raise OverflowError("model update exceeds the encodable fixed-point range")
    return [int(value) for value in scaled.to(torch.int64).tolist()]


def chunked_wire_values(sample_count: int, encoded: Sequence[int], chunk_size: int) -> list[int]:
    if not _is_int(sample_count) or sample_count <= 0:
        raise ValueError("sample count must be a positive integer")
    values = [int(sample_count), *[int(v) for v in encoded]]
    values.extend([0] * (-len(values) % chunk_size))
    return values


# ---- exact reference ---------------------------------------------------------------
@dataclass
class RobustResult:
    threshold_squared: int
    clipped_count: int
    accepted: list[int]
    clip_flags: list[int]
    totals: list[int]
    coefficients: list[int] = field(default_factory=list)
    squared_norms: list[int] = field(default_factory=list)


def robust_reference(
    inputs: Sequence[Sequence[int]],
    weights: Sequence[int],
    spec: Sequence[int],
) -> RobustResult:
    """Exact integer emulation of spdz2k_robust_aggregate.mpc.

    ``inputs`` holds each client's encoded delta (without the sample count), in
    the order of the sorted selected client IDs; values are reduced mod 2^64.
    """
    validate_spec(spec, weights)
    (
        clip, screen, adaptive, static_t, t_min, t_max, lambda2, rho2,
        clip_bits, r_max, reveal, _, _,
    ) = spec
    if len(inputs) != len(weights) or len(inputs) < 2:
        raise ValueError("inputs and weights must align and cover at least two clients")
    dimension = len(inputs[0])
    if dimension == 0 or any(len(row) != dimension for row in inputs):
        raise ValueError("all client inputs must have the same positive dimension")
    mod = RING_MODULUS
    one_g = 1 << clip_bits

    squared, visible, valid = [], [], []
    for row, weight in zip(inputs, weights):
        r_k = sum((int(v) % mod) * (int(v) % mod) for v in row) % mod
        s_k = (r_k * weight * weight) % mod
        ok = _le(0, s_k) * _le(s_k, (r_max * weight * weight) % mod)
        squared.append(r_k)
        visible.append(s_k)
        valid.append(ok)

    if adaptive:
        keyed = [((v * ((r - r_max) % mod)) + r_max) % mod for r, v in zip(squared, valid)]
        count = len(keyed)
        for phase in range(count):
            for first in range(phase % 2, count - 1, 2):
                low, high = keyed[first], keyed[first + 1]
                swap = _lt(high, low)
                delta = (swap * ((high - low) % mod)) % mod
                keyed[first] = (low + delta) % mod
                keyed[first + 1] = (high - delta) % mod
        median = keyed[(count - 1) // 2]
        raw = (median * lambda2) % mod
        below = _lt(raw, t_min)
        raw = (below * ((t_min - raw) % mod) + raw) % mod
        above = _lt(t_max, raw)
        threshold = (above * ((t_max - raw) % mod) + raw) % mod
    else:
        threshold = static_t % mod

    accepted, coefficients, clipped = [], [], []
    for k, weight in enumerate(weights):
        w2 = weight * weight
        s_k = visible[k]
        bound = (threshold * w2) % mod
        if screen:
            a_k = valid[k] * _le(s_k, (bound * rho2) % mod)
        else:
            a_k = valid[k]
        if clip:
            not_clipped = _le(s_k, bound)
            low = 0
            for bit in reversed(range(clip_bits)):
                candidate = low + (1 << bit)
                fits = _le((candidate * candidate * s_k) % mod, (bound * one_g * one_g) % mod)
                low += fits * (1 << bit)
            c_k = not_clipped * one_g + (1 - not_clipped) * low
            clipped.append(valid[k] * (1 - not_clipped))
        else:
            c_k = one_g
            clipped.append(0)
        accepted.append(a_k)
        coefficients.append(c_k)

    totals = [0] * dimension
    for k, weight in enumerate(weights):
        if not accepted[k]:
            continue
        factor = (coefficients[k] * weight) % mod
        row = inputs[k]
        for j in range(dimension):
            totals[j] = (totals[j] + factor * (int(row[j]) % mod)) % mod

    clip_flags = [c * a for c, a in zip(clipped, accepted)]
    return RobustResult(
        threshold_squared=to_signed(threshold),
        clipped_count=sum(clip_flags),
        accepted=accepted,
        clip_flags=clip_flags if reveal else [0] * len(weights),
        totals=[to_signed(value) for value in totals],
        coefficients=coefficients,
        squared_norms=[to_signed(value) for value in squared],
    )


def result_from_outputs(outputs: Sequence[int], client_count: int, dimension: int) -> RobustResult:
    header = 2 + 2 * client_count
    if len(outputs) != header + dimension:
        raise RuntimeError("robust SPDZ2k output length did not match the round schema")
    accepted = [int(v) for v in outputs[2 : 2 + client_count]]
    flags = [int(v) for v in outputs[2 + client_count : header]]
    if any(v not in (0, 1) for v in accepted + flags):
        raise RuntimeError("robust SPDZ2k output contained non-binary decision values")
    return RobustResult(
        threshold_squared=int(outputs[0]),
        clipped_count=int(outputs[1]),
        accepted=accepted,
        clip_flags=flags,
        totals=[int(v) for v in outputs[header:]],
    )


@dataclass
class DecodedAggregate:
    delta: torch.Tensor
    accepted_weight: int
    threshold_norm: float
    aggregate_norm: float
    output_check_passed: bool
    result: RobustResult


def decode_robust_output(
    result: RobustResult,
    weights: Sequence[int],
    config: SecureDefenceConfig,
) -> DecodedAggregate:
    """Decode the weighted sum of clipped updates and verify the output bound.

    The aggregate norm check is exact integer arithmetic:
    ``||A||^2 <= (2^g * W_acc)^2 * bound`` where ``bound`` is the clipping (or
    screening) threshold. Honest-format inputs always satisfy it; a failure
    means at least one accepted input was malformed (wrapped modulo 2^64).
    """
    accepted_weight = sum(int(w) for w, a in zip(weights, result.accepted) if a)
    threshold = int(result.threshold_squared)
    if threshold <= 0:
        raise RuntimeError("robust SPDZ2k returned a non-positive threshold")
    one_g = 1 << config.clip_bits
    norm_squared = sum(value * value for value in result.totals)
    if accepted_weight == 0:
        passed = norm_squared == 0
        delta = torch.zeros(len(result.totals), dtype=torch.float64)
    else:
        limit = (one_g * accepted_weight) ** 2 * config.output_bound(threshold)
        passed = norm_squared <= limit
        delta = torch.tensor(result.totals, dtype=torch.float64) / float(
            one_g * config.scale * accepted_weight
        )
    aggregate_norm = (
        math.sqrt(norm_squared) / float(one_g * config.scale * accepted_weight)
        if accepted_weight
        else 0.0
    )
    return DecodedAggregate(
        delta=delta,
        accepted_weight=accepted_weight,
        threshold_norm=math.sqrt(threshold) / config.scale,
        aggregate_norm=aggregate_norm,
        output_check_passed=bool(passed),
        result=result,
    )


def apply_delta(
    global_state: Mapping[str, torch.Tensor], delta: torch.Tensor
) -> dict[str, torch.Tensor]:
    """Add a flat float64 update to the floating-point tensors of a state dict."""
    result: dict[str, torch.Tensor] = {}
    offset = 0
    for key, base in global_state.items():
        if not torch.is_floating_point(base):
            result[key] = base.detach().clone()
            continue
        count = base.numel()
        update = delta[offset : offset + count].reshape(base.shape)
        result[key] = (base.detach().cpu().to(torch.float64) + update).to(
            device=base.device, dtype=base.dtype
        )
        offset += count
    if offset != delta.numel():
        raise RuntimeError("aggregate update length did not match the model schema")
    return result

# Secure robust aggregation inside SPDZ2k

This document specifies the in-MPC integrity defence implemented in
`src/fl_security/smpc/programs/spdz2k_robust_aggregate.mpc` and its coordinator
side in `src/fl_security/smpc/robust.py`, and states exactly what it does and
does not guarantee.

## 1. Problem

The original SPDZ2k program computes only `Σ nᵢ·wᵢ` and `Σ nᵢ`. It keeps
individual updates confidential but accepts any input, so it adds no protection
against poisoning. Plaintext robust aggregators (median, Krum, norm screening,
the repository's `RobustUpdateDetector`) need to inspect individual updates and
therefore cannot run after a sum-only secure aggregation without breaking the
confidentiality that SMPC provides.

Requirement: bound each client's influence on the aggregate **inside** the
secure computation, revealing no individual update to the coordinator.

## 2. Cost constraints that shaped the design

Measured on the project host (3 local parties, ARM Neoverse-N1, 3 cores):

| Operation in MP-SPDZ SPDZ2k (`-R 64`) | Cost |
|---|---|
| secret × secret multiplication | 1 triple; ≈3,100 triples/s for 3 parties |
| client input (Damgård et al. protocol) | 1 triple per value |
| reveal to output client | 1 triple + 1 random per value |
| comparison (`LTZ`, bit length 63+1) | ≈126 triples + ≈63 random bits |
| `sfix` multiplication with truncation | ≈86 triples per coordinate in the earlier prototype |

A per-coordinate comparison (coordinate clipping, coordinate median) costs
≈126 triples per coordinate and client – about 130× an input – and is not
affordable even for small models. The design therefore uses **integer
arithmetic only** (no fixed-point truncation inside MPC), **one or two
multiplications per coordinate**, and a **constant number of comparisons per
client**, independent of the model size.

## 3. Algorithm

Encoding (client): `x = round((w_local − w_global) · 2^f)` as signed 64-bit ring
elements (default `f = 14`). The client sends `[n, x₁, …, x_d]` in chunks;
`n` is checked against the server-known sample count as in the sum-only
program. Each client k has a public integer weight `w_k` (uniform `1`, or
sample counts quantised to `weight_bits` bits and reduced by their GCD).

Inside SPDZ2k, for every client k:

1. `R_k = Σⱼ x_kj²` – one dot product (`d` triples).
2. `S_k = w_k² · R_k` – squared norm of the **visible contribution** `w_k·x_k` (free).
3. `valid_k = [0 ≤ S_k ≤ w_k² · r_max]` – two comparisons; invalid inputs are
   excluded (`r_max` = squared `max_valid_norm`).

Threshold `T` (a squared norm in units `2^(2f)`):

* static: a public constant `τ²·2^(2f)`;
* adaptive: `T = clamp(λ² · lowermedian(R'), t_min, t_max)`, with
  `R'_k = R_k` if valid else `r_max`; the lower median of K values is obtained
  with an odd–even transposition network (`K(K−1)/2` compare-exchange steps).
  `λ² = 1` reproduces FLAME-style median-norm clipping. With `K = 4` the lower
  median is honest whenever at most two submitted norms are inflated.

Per client:

4. screening (optional): `a_k = valid_k · [S_k ≤ ρ² · w_k² · T]`, revealed.
5. clipping (optional): `C_k = 2^g` if `S_k ≤ w_k²·T`; otherwise the largest
   integer `c < 2^g` with `c² · S_k ≤ 2^(2g) · w_k² · T`, found by a `g`-step
   binary search (2 multiplications + 1 comparison per step). `C_k` stays
   secret. `C_k = ⌊2^g · min(1, √(T/R_k))⌋`: the clipped norm never exceeds the
   bound (conservative rounding).
6. aggregate: `A_j = Σ_k a_k · C_k · w_k · x_kj` (`d` triples per accepted
   client); with clipping disabled `C_k = 2^g` and the products are free.

Revealed to the output client only: `T`, the number of clipped clients, the
accept bits `a_k`, the clip flags (only if `reveal_client_flags`), and `A`.
The coordinator decodes `Δ̄ = A / (2^(g+f) · Σ_k a_k w_k)` and sets
`w_global ← w_global + Δ̄`. Rejected clients are excluded from the denominator;
clipped clients are not re-normalised (otherwise clipping would be undone).

## 4. Why every decision uses the visible contribution

All arithmetic is modulo 2⁶⁴. A malicious client may submit any ring element,
including values whose squares wrap around:

| Input | `x²` mod 2⁶⁴ | Consequence for a naive check on `R = Σx²` |
|---|---|---|
| `x = 2³²` | `0` | huge coordinate looks like a zero update |
| `x = 2⁴⁰` | `0` | same |
| `x = 3·2³⁰` | `2⁶³+2⁶⁰` (negative) | input looks invalid (safe) |
| `x = D·w⁻¹` (odd `w`) | pseudo-random | **weight-inverse attack**: the visible contribution `w·x ≡ D` is chosen freely while `R` is pseudo-random; a brute-force search over small tweaks of `D` finds `R ≤ T` in ≈`2⁶⁴/T` tries (≈2³⁰ for typical bounds) |

The defence therefore never decides on `R_k` alone:

* screening and validity use `S_k = w_k² R_k ≡ ‖w_k x_k‖²` (mod 2⁶⁴), the
  squared norm of what actually enters the sum;
* clipping accepts candidate `c` only if `c² S_k ≡ ‖c·w_k·x_k‖²` (mod 2⁶⁴) is
  within `2^(2g)·w_k²·T`; the final `C_k` satisfies this inequality, so the
  clipped visible contribution is checked directly. Squaring commutes with the
  scalar factors in the ring, so hidden components that vanish after
  multiplication by `C_k w_k` also vanish from the checked value.

**Lemma (per-client bound).** If the true squared norm of an accepted visible
contribution `V_k = a_k C_k w_k x_k` is below `2⁶²`, then
`‖V_k‖ ≤ 2^g · w_k · τ · 2^f` (clipping) or `≤ ρ · w_k · τ · 2^f` (screen-only).
*Reason:* below `2⁶²` the ring value of the checked expression equals the true
squared norm, and the comparison (sign of the 64-bit difference) is exact for
operands of that size; the inequality is enforced in step 4 or 5.

**Bit budget.** `SecureDefenceConfig.round_spec` and the program reject
parameters unless every compared product stays below `2⁶²` for valid inputs:
`r_max·w²·4^g`, `r_max·λ²`, `t_max·w²·4^g`, `t_max·w²·ρ²`, `static·w²·ρ²` < 2⁶².
Honest inputs therefore never wrap and are always processed exactly.

## 5. Plaintext output check and what it adds

A contribution whose true squared norm is ≥ `2⁶²` (norm ≥ `2³¹` ring units) can
pass the checks modulo 2⁶⁴. Such a contribution is enormous: after decoding it is
at least `2³¹ / (2^(g+f) · Σw)` in model units. The coordinator therefore
verifies, in exact integer arithmetic,

```text
‖A‖² ≤ (2^g · Σ_k a_k w_k)² · B,   B = T (clipping) or ρ²·T (screen-only),
```

which every honest-format round satisfies by the triangle inequality. If the
check fails the round's update is **not applied** (the global model is kept)
and the event is logged (`defence_output_check_passed = 0`). The configuration
is rejected unless `2³¹/(2^(g+f)·Σw) ≥ 2·output_margin·√B_max`, so a single
wrapping contribution cannot hide inside the honest range.

**Guarantee (single malicious client).** With at most one client deviating from
the encoding, every applied round satisfies: each accepted contribution obeys
the per-client bound of the lemma, or the round is rejected.

**Limitation (colluding clients).** Two or more colluding clients can submit
inputs whose huge components cancel in the sum (e.g. `x_A = B`,
`x_B = δ − B` with `‖B‖²` and `‖δ−B‖²` small modulo 2⁶⁴). Each input passes
its own check while their sum injects an arbitrary `δ`. The output check still
bounds the applied update by `B`, but within that ball colluders can exceed
their per-client allowance. Closing this gap needs per-coordinate range proofs
(as in RoFL, ACORN or EIFFeL); in MP-SPDZ this costs a comparison per
coordinate (≈126 triples), which is infeasible on this host at model scale.
The validation suite demonstrates both outcomes (detected with 4 clients,
undetected with 8; see `research_output/completion/experiments/mpc_validation`).

## 6. Numerical behaviour

* Fixed-point resolution `2^-f` per coordinate (`f = 14`: 6.1·10⁻⁵),
  round-to-nearest at the client; no rounding inside MPC.
* Clip coefficient resolution `2^-g` (`g = 8`), always rounded down; updates
  larger than `2^g·τ` receive `C_k = 0` (dropped).
* Weights: exact when uniform or when sample counts are equal; otherwise
  quantised to `weight_bits` (relative error ≤ `2^-(weight_bits+1)` for the
  largest clients).
* The reference implementation (`robust_reference`) reproduces the program
  exactly, including MP-SPDZ's comparison semantics (sign of the 64-bit
  difference). Agreement is bit-for-bit in all validation scenarios and is
  re-checked inside every instrumented FL run.

## 7. Leakage

Revealed per round, in addition to the aggregate: the threshold `T` (adaptive
mode: a clamped multiple of the lower-median squared norm), the number of
clipped clients, which clients were rejected by screening (screen modes), and –
only when `reveal_client_flags` is enabled for evaluation – which clients were
clipped. Clip coefficients, norms of accepted clients and individual updates
stay secret. Malformed inputs are revealed as rejected, which discloses nothing
about honest clients.

## 8. Cost

For K clients, dimension d and `g`-bit coefficients (compile-time counts for
K = 4, d = 2,202, adaptive clip+screen, `g = 8`): 36,056 triples, 3,836 random
bits, 4,424 randoms (sum-only program: ≈5·d triples). Roughly
`(3K+1)·d + K·(g+3)·126 + K(K−1)/2·126` triples. Measured wall-clock costs are
reported in `research_output/completion/benchmarks`.

edaBits (`use_edabits`) reduce integer triples by 19 % but doubled the measured
round time on this host (binary preprocessing dominates); they are disabled by
default.

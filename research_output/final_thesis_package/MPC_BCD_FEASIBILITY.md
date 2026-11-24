# MPC Bounded-Contribution Defense: feasibility assessment

## Status

MPC-Enforced Bounded-Contribution Defense (MPC-BCD) is **not implemented**. Secure comparison and conditional selection are available in the pinned MP-SPDZ v0.4.3 compiler, so coordinate clipping is expressible. The measured circuit cost makes coordinate-wise clipping impractical to claim for this project's full CIFAR model without substantial additional infrastructure and a real runtime/communication benchmark. Implementation is paused at the prompt's feasibility gate.

## Required operation

The requested defense clips each client coordinate inside MPC:

`clip_B(u) = max(-B, min(B, u))`

and then computes `sum_i(n_i * clip_B(u_i)) / sum_i(n_i)`. A client-side clamp would not enforce the rule against a malicious client and is not an acceptable substitute.

## Evidence collected

Using the project's pinned MP-SPDZ v0.4.3 checkout and SPDZ2k ring setting (`-R 64`), generated comparison circuits using `sint` comparison and `if_else`:

| Coordinates | Compiler wall time | Integer triples | Simple multiplications | VM rounds |
|---:|---:|---:|---:|---:|
| 1,000 | 0.17 s | 120,000 | 120,000 | 12 |
| 10,000 | 0.16 s | 1,200,000 | 1,200,000 | 12 |

The observed compiler resource estimate is approximately 120,000 triples per coordinate. The project model has 2,122,187 floating-point parameters, implying approximately **254,662,440 triples per aggregation** if the measured cost scales linearly. This is an extrapolation from compiler resource counts, not a runtime or network measurement. The circuit also creates approximately 4.24 million integer opens at that model size according to the compiler's 2,000 opens per 1,000 coordinates estimate.

The existing full-model aggregation compile attempt exceeded 300 seconds and reached approximately 11.3 GB resident memory before it was stopped. It did not include the additional clipping comparisons. The successful integrated same-host smoke test substituted a tiny 8-parameter model and therefore does not demonstrate full-CIFAR performance.

Probe commands:

- `python3 compile.py -R 64 mpc_bcd_cost_1000 1000`
- `python3 compile.py -R 64 mpc_bcd_cost_10000 10000`

The probe source used `sint.get_input_from(0, size=size)`, secret comparison against a public bound, `if_else`, then reveal. Compiler output was saved in the interactive execution record; no inference is made about online latency, preprocessing volume on disk, or communication bytes.

## Recommendation for further research

A mathematically sound alternative to coordinate clipping is **per-tensor L2 norm clipping inside MPC**. For each client and parameter tensor, compute the squared norm `s = sum_j(u_j^2)`, compare `s` with public `B^2`, and apply a secret scale factor `min(1, B/sqrt(s))` to every coordinate before weighted aggregation. This reduces comparisons from one per coordinate to one per tensor, but still requires secure squaring, a secure square root or a sound bounded approximation, and secret scalar multiplication across every coordinate. It changes the defense from coordinate-wise bounds to a tensor-level norm bound and requires numerical-error and cost analysis. It must not be described as equivalent to the requested coordinate-wise rule.

Before implementation, benchmark a complete per-tensor clipping circuit at representative tensor sizes, validate its fixed-point error and ring bounds against a Python reference, and measure preprocessing, online time, and bytes on the actual three-party service. If that remains too costly, use a smaller research model or a separately justified block partition; do not silently substitute client-side clipping.

## Security and evaluation implications

No clipping claim, clipping activation metric, or MPC-BCD experimental result is supported by this repository state. The proposed design would limit contribution magnitude only; it would not establish differential privacy or prevent within-bound sign-flipping, label-flipping, backdoor, or colluding-client attacks. Existing tests and smoke runs do not test MPC-BCD.

## Compiler references

The compiler probes confirmed syntax support for secure `sint` comparison and `if_else`; this establishes expressibility only. See the pinned [MP-SPDZ v0.4.3 high-level interface](https://mp-spdz.readthedocs.io/en/v0.4.3/Compiler.html) and [runtime options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html) for compiler/runtime behavior and ring configuration.

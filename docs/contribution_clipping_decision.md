> **Superseded (2026-11-20).** This document records an earlier decision and is kept unchanged below for traceability. An integer-only in-MPC norm defence (clipping and screening with a constant number of comparisons per client) is now implemented in `src/fl_security/smpc/programs/spdz2k_robust_aggregate.mpc`; see `docs/secure_robust_aggregation.md` and `research_output/completion/`. Coordinate-wise clipping remains unimplemented for the cost reasons given below.

# Contribution-clipping feasibility decision

**Decision: Option C ? leave clipping unimplemented; keep MTD plus SPDZ2k aggregation as the implemented core.**

## Why no clipping is being integrated now

The active circuit sums sample-weighted vectors but has no mechanism that enforces a per-client contribution bound. Client-side clipping would be bypassable by a malicious client and is rejected as a substitute.

The existing compiler probe for secure coordinate clipping measured about 120,000 triples per coordinate at 1k and 10k coordinates. Linear scaling to the 2,122,187-parameter CNN gives approximately 254,662,440 triples and approximately 4.24 million opens per aggregation; these are compiler-count extrapolations, not runtime/communication results.

The separate per-tensor L2 clipping prototype was functionally exercised only on two-coordinate client vectors. Its 250-coordinate compile used 67,147 triples and 338 VM rounds; the ~570 million full-model triple number is an extrapolation. The approximation's malicious-input range/overflow guarantee is not established. Neither clipping alternative has a full-model runtime, comprehensive boundary/overflow tests, or integration with the production Flower path. By comparison, aggregation without clipping already takes 246.236 s at 100k parameters in the measured three-party setup.

## Security/claim boundary

Do not add client-side clamps, trust client-reported norms, or claim enforceable contribution protection. The active contribution protection is **none**. SPDZ2k hides inputs during the secure sum; it does not bound their magnitude or prove honest training. MTD selects a cohort but does not establish client honesty.

Reconsider clipping only after a rigorously specified MPC algorithm establishes fixed-point/ring bounds, handles zero and overflow cases, verifies maliciously oversized inputs, and completes end-to-end runtime/communication tests at representative model dimensions. Consider a smaller research model or separately justified tensor/block partition only as a new research study; do not imply equivalence to global L2 clipping.

Evidence sources retained unchanged: `docs/mpc_bounded_contribution.md`, `research_output/final_thesis_package/MPC_DEFENSE_FEASIBILITY.md`, `research_output/scalability_phase/NORM_CLIP_*`, and `research_output/MPC_BCD_COMPILE_*.log`.

# Final research audit

## Decision: B ? direct MPC works up to a measured parameter point

This audit separates compiler scaling, direct MPC execution, and Flower integration. The production circuit compiles at full model size, but neither a current full-model direct run nor a full-model Flower round returned an aggregate. The largest completed progressive direct run was 100,000 parameters on the tested host/configuration.

## Repository safety

- Thesis worktree: `/home/ubuntu/gemini/fl-security-research-spdz2k-thesis`, branch `research/spdz2k-thesis`, HEAD `ab2de22da9e2e4d707295b9414bbe843f375ea39`. Research changes remain uncommitted.
- Original checkout: `/home/ubuntu/gemini/fl-security-research`, branch `main`, same HEAD. Its eight pre-existing modified files were identical at start and final status; it was not edited.
- No commit or push. No benchmark or test process remained at final inspection.

## Verified evidence

- Full suite on the isolated source: 71 passed, two Typer/Click deprecation warnings, 5.50 s. Python 3.11 compileall and `git diff --check` passed. A wheel built with setuptools and contained the production circuit; the removed additive-sharing modules were absent.
- Production circuit source hash `1e26719b74fb35cb8c0aff5a2a12a23e21ad1d760a08070a91a8209e2e6ef333` compiled at 250k, 500k and 2,122,187 parameters in 1.780/1.775/1.751 s; ~62.2 MiB compiler RSS; 1,003,706/2,003,130/8,491,194 triples; 29 VM rounds. This is compiler evidence, not execution.
- Direct production circuit with three same-host parties and deterministic counts [1,2,3] passed at 8, 1k, corrected 10k, 50k and 100k. Outputs matched the Python reference exactly for the tested vectors. At 100k: 246.236 s including cleanup, ~197 s preprocessing/offline, ~17 s online, 401,594 triples, 29 rounds, 42,999.4 MB global party traffic, ~388?391 MiB peak RSS. The profile used fixed-point scale 100,000; this differs from the default scale 1,000,000 in `configs/smpc.yaml`.
- The 250k direct run reached its 300 s watchdog after client connections, produced no aggregate, and cleaned up. Host loopback counters recorded 59,290,526,761 bytes; MP-SPDZ did not emit a completed global protocol-traffic total. Peak party RSS was ~384?388 MiB. 500k and full shape were not attempted in this phase. An earlier 2,122,187-parameter direct attempt also aborted at 300 s without an aggregate and before the output framing correction.
- The chunked tiny Flower/SPDZ2k run passed one synthetic 8-parameter round with 3 clients/3 parties in 16.32 s; logged aggregation 0.807365 s, metric 73,728 bytes, zero fit failures. A distinct earlier tiny Flower run logged 0.160333 s and 648 bytes; these are not merged. There is no full-model Flower result.
- Party service compile now uses MP-SPDZ `-M`. An 8-parameter A/B removed the warning with `-M`; both outputs/counts matched exactly and used 4,282 triples, 29 rounds, 487.03 MB global party traffic. Compile time was ~3.638 s with `-M` and ~1.379 s without; the latter is a tiny archival comparison only.
- A 10k output read initially failed with `unexpected data length`; the receiver was corrected to read the full contiguous `Array.reveal_to_clients` vector in one message. Corrected 10k/50k/100k runs passed.
- The party service command includes `-e`, and the local demo provisions MP-SPDZ SSL material. This requests encrypted party links in the tested same-host setup. Cross-host TLS/certificate identity, renewal, firewall and independent-party deployment have not been validated.

## Security and research limitations

The pinned MP-SPDZ v0.4.3 documentation classifies SPDZ2k as malicious security with dishonest majority; the protocol provides abort, not availability. At least one aggregation party must remain honest for confidentiality, under MP-SPDZ setup and protocol assumptions. The coordinator receives aggregate/count and sees participant metadata; repeated/differenced cohorts can leak information. MAC-failure injection, malicious-party behavior, network partitions, dropout recovery, cross-host operation, a private robust detector, production norm clipping, MPC-BCD, multi-seed poisoning evaluation and independent cryptographic review remain unvalidated or unimplemented. MTD uses a secret-derived schedule only when `FL_MTD_SECRET` is set; the included secure config disables MTD.

The compiler warning `Order of memory instructions not preserved, errors possible` was relevant because the circuit uses indirect `Array` accesses. The project now compiles with documented option `-M`, which preserves memory instruction ordering. Do not characterize the earlier warning as harmless.

## Thesis claim boundary

The defensible evidence is an engineering prototype, tiny same-host Flower integration, deterministic weighted aggregation through 100k direct parameters, and a measured preprocessing bottleneck. Do not claim full-model runtime, full-model Flower support, cross-host security, private poisoning detection, production defense efficacy, dropout recovery, differential privacy, or universal scalability. Full claim and limitation details are in `THESIS_CLAIM_EVIDENCE_MATRIX.md`, `FINAL_EXPERIMENTAL_RESULTS.md`, `FINAL_SECURITY_AUDIT.md`, and `THESIS_READINESS_REPORT.md`.


## Engineering integration update ? 2026-11-18

Pre-refactor findings are recorded in `docs/engineering_baseline_audit.md`; clipping decision is in `docs/contribution_clipping_decision.md` (Option C: not implemented). The active secure data path was already singular, so this phase did not move/delete source modules or historical configurations. README, architecture and methodology were aligned; the existing `configs/benchmark_lr001/hybrid_verified.yaml` is designated as intended primary, not claimed as a completed full-model run. `run_benchmark.py` exists, although its paired matrix remains unrun.

Added MTD different-secret cohort separation and unset-secret public determinism tests, round/cohort bytecode identity, missing selected-client abort, reused-round rejection, truncated output and nonzero padding rejection. Focused tests: 30 passed. Full suite: 77 passed, two Typer/Click deprecation warnings in 5.50 s. Compileall and diff check pass. `docs/reverse_validation.md` traces claims to code/tests/evidence and lists untested failure modes. No production aggregation code, security parameter, benchmark data, or original checkout was changed in this phase.

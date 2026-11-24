# Continuation log ? 2026-11-18

## Recovered state
- Worktree: /home/ubuntu/gemini/fl-security-research-spdz2k-thesis
- Branch: research/spdz2k-thesis
- HEAD: ab2de22da9e2e4d707295b9414bbe843f375ea39
- Original checkout remains /home/ubuntu/gemini/fl-security-research on main with its existing eight modifications; it was not edited. No commit/push.
- No benchmark was active at recovery.
- Production circuit: src/fl_security/smpc/programs/spdz2k_weighted_sum.mpc; chunk size 1,024; array reveal present.
- Separate clipping prototype: /home/ubuntu/gemini/MP-SPDZ-v0.4.3/Programs/Source/norm_clip_prototype.mpc; not integrated in production.

## Prior stopping point
The old whole-vector array-reveal 250,000-parameter compile log ends during progress output, with no bytecode hash/circuit counts. Its saved benchmark row marks TIMEOUT_120S at 3,938.4 MiB RSS. It did not successfully compile and no process remained. This is preserved in array_reveal_250001.log.

The chunked scratch circuit had already compiled 250k (1.808s, 62.3MiB, 1,003,706 triples), 500k (1.757s, 61.8MiB, 2,003,130 triples), 1M, and full shape. Those scratch results are supporting evidence, but not used alone as production evidence.

## Exact production-source compilation
Compiled the checked-in production source copied byte-for-byte (SHA-256 1e26719b74fb35cb8c0aff5a2a12a23e21ad1d760a08070a91a8209e2e6ef333), MP-SPDZ v0.4.3, -R 64, 3 clients/parties, chunk size 1,024. Each process capped at 6 GiB RSS and 120s:
- 250,000 parameters: pass, 1.780s, 62.2MiB, 1,003,706 triples, 29 VM rounds.
- 500,000 parameters: pass, 1.775s, 62.2MiB, 2,003,130 triples, 29 VM rounds.
- 2,122,187 parameters: pass, 1.751s, 62.2MiB, 8,491,194 triples, 29 VM rounds.
See PRODUCTION_CIRCUIT_SCALING_FINAL.csv and production_capped_*.log. Each finished; metrics were parsed from complete compiler output.

## Full-shape execution attempt
A guarded direct production client-I/O run used actual CIFAR10CNN-shaped tensors, 3 local parties, sample counts [1,2,3], weighted client updates, sample-count binding and aggregate-only output. It did not finish in 300 seconds. The guard interrupted it; local_demo cleanup removed all parties and temporary credentials. No aggregate correctness, protocol traffic, or completed runtime was recorded. Party RSS was about 0.8GiB each during the run; host memory/disk remained above guard thresholds. Log: FULL_SHAPE_MPC_INTEGRATION.log. This was not a full Flower round; the only Flower integration success remains the prior 8-parameter synthetic round.

## Norm-clipping review
The prototype uses sfix(16 fractional bits, 31-bit total), nearest rounding, squared norm, exact-zero substitution to 1, and MP-SPDZ InvertSqrt. InvertSqrt source cites Lu et al. and implements bit decomposition plus an approximation polynomial; its local docstring gives no input-range guarantee. sfix docs state a default signed magnitude around 2^14 and step 2^-16; default multiplication truncation is probabilistic, while round_nearest avoids that mode at extra cost. The prototype has no secure malicious-input range check; overflow/negative wrapped norm and approximation limits are unresolved. It avoids secret division by returning a weighted sum and dividing by public total count outside MPC. Two-dimensional reference scenarios passed, but full-model clipping is not practical evidence.

## Decision
B ? core MPC works at tiny integrated scale, while full-model protocol execution needs optimization/measurement. Do not proceed to the multi-seed matrix. Cross-host execution is unavailable on this single host. No production defense is implemented.

## Audit trail note
Two provisional compile summaries with regex parse defects were retained under REJECTED_PRODUCTION_CIRCUIT_SCALING_PARSER*.csv and are not used as evidence. The complete capped measurements are in PRODUCTION_CIRCUIT_SCALING_FINAL.csv with raw logs. Temporary harness setup failures ended before client inputs (or were aborted during startup); the final 300s run was safely interrupted and party cleanup verified.

## Runtime optimization and correctness continuation — 2026-11-18

- Corrected production client output framing after the 10k probe showed unexpected data length: MP-SPDZ array reveal sends one full contiguous vector, so eceive_weighted_average() now receives the exact padded output length in one message. Corrected direct runs at 10k, 50k and 100k passed exact deterministic reference checks.
- Enabled MP-SPDZ compiler -M in the party service to preserve memory instruction ordering for production indirect Array accesses. The 8-parameter A/B removed the warning with no observed output, count, triple, round, or traffic difference; compile time rose from ~1.379s to ~3.638s per party.
- Actual production direct MPC passed at 8, 1k, 10k, 50k and 100k. At 100k: 246.236s total, ~197s offline/preprocessing, ~17s online, 401,594 triples, 29 rounds, 42,999.4 MB global traffic, ~407–410 MiB peak RSS.
- The 250k run hit the 300s watchdog after all clients connected; no aggregate was returned. Host loopback traffic was ~59.3GB and party RSS ~403–407MB. Cleanup completed; no benchmark processes remained. 500k and full shape were not attempted due insufficient runtime headroom. Full-model Flower remains gated and unverified.
- Added esearch_output/runtime_optimization/ reports, preserving raw logs and the initial failed 10k run. Updated esearch_output/final_thesis_package/FINAL_RESEARCH_AUDIT.md with verified evidence. Final decision B, measured for this host/configuration; no cross-host claim, no independent segmented protocol, no preprocessing reuse, and no production defense claim.
- Previous latest suite result remains 71 passed, two dependency deprecation warnings; compileall passed. No new test run in this continuation.

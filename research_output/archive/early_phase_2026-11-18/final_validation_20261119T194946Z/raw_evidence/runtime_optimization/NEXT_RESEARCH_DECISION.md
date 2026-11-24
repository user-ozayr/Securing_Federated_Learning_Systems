# Next research decision

## Selected outcome: B ? direct MPC works up to a measured parameter limit

The largest completed deterministic production-circuit direct run was 100,000 parameters: exact reference output, validated sample count, 246.236 s including cleanup, about 43.0 GB global protocol traffic and 407?410 MiB peak party RSS. The 250,000-parameter run was safely aborted at the 300-second cap after all clients connected and party setup; it returned no aggregate. The full 2,122,187-parameter run remains unverified and had previously timed out. Thus the measured validation limit is 100k under this host/configuration/cap, not a universal protocol limit.

Preprocessing/offline dominates: ~197 s at 100k versus ~17 s online. Continue performance work on supported preprocessing/runtime/network implementation and optimize transfers only where measurements justify it. Keep `-M`, MAC verification, authentication, sample-count binding, and the security parameters unchanged. Do not reuse preprocessing across rounds without a protocol-specific security review.

Do not launch 500k or full-shape under the same 300s policy: the 100k pass already uses 246s and the 250k run reaches the cap. Reconsider only after an evidenced optimization materially reduces offline cost and a safe resource budget is available. Do not run full-model Flower until full-shape direct MPC passes. MPC-BCD and production norm clipping remain deferred; next defense work begins after a reliable full-model secure aggregation baseline exists.

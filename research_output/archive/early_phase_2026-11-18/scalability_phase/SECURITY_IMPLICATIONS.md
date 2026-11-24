# Security implications
Evidence: secure mode requires MP-SPDZ SPDZ2k and no plaintext/additive fallback; circuit compares sample counts to server-known values and reveals only validity to parties; party control has authentication/replay protection; tests cover controls; tiny same-host integrated path passed.

Limits: full-model runtime/traffic unknown. Compiler emitted ?Order of memory instructions not preserved, errors possible?; investigate before relying on full-shape execution. Same-host does not establish independent operators or network security. Sum-only aggregation reveals to designated output client; private update scoring, MPC-BCD and clipping are absent from production. Clipping prototype lacks secure extreme-input range enforcement; sfix can overflow, and clipping does not prevent within-bound sign flips.

Do not claim full-model execution, cross-host deployment, poisoning robustness, practical full-model clipping, MPC-BCD, or full CIFAR learning.

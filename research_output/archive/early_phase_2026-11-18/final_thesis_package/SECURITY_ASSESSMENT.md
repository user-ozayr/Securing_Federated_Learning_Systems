# Security assessment

This branch selects MP-SPDZ v0.4.3 SPDZ2k modulo 2^64. Three-party execution is designed for the selected protocol's malicious-security-with-abort model and preprocessing assumptions; this is not an independent audit or cross-host validation.

Party control uses HMAC, timestamps, unique request IDs, replay journaling and unique round IDs. Flower proxy IDs bind logical client identities. Only selected clients are accepted. Sample counts are compared to server-known partition counts and circuit expectations, exposing only a mismatch bit to parties. Secure mode rejects plaintext parameter payloads. The output client receives the aggregate and total count, not individual updates.

The exact production circuit compiles at full model shape, but a guarded direct full-shape run did not return an aggregate within 300s. Full-size execution correctness/performance is unproven. Compiler output warns ?Order of memory instructions not preserved, errors possible?; investigate. Same-host testing does not establish network boundaries or independent operators. Review party-to-party channel protections before deployment.

MPC-BCD and norm clipping are absent from production. The norm prototype uses sfix with 16 fractional/31 total bits and lacks secure malicious-input range checks; overflow and approximation limits are unresolved. No general poisoning resistance or differential privacy is claimed.

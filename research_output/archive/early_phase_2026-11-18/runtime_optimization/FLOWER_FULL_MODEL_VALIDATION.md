# Full-model Flower validation status

No full-model Flower round was run. The direct production MPC path passed through 100,000 parameters, but the 250,000-parameter direct probe did not finish within the 300-second cap. The full 2,122,187-parameter direct run from the earlier phase also timed out without an aggregate. The requested gate therefore remains closed.

The previously verified Flower result is only a tiny same-host, three-client/three-party, 8-parameter synthetic round (16.32 s total, 0.807 s recorded aggregation, zero fit failures). It does not establish full CNN Flower integration. No claim is made here about full-model plaintext-update isolation, end-to-end global-model correctness, or full-round overhead. Cross-host testing is unavailable.

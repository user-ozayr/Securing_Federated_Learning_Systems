# Security gap analysis

## High priority

1. **Malicious clients can poison the global model.** SPDZ2k protects the computation, not whether inputs were honestly trained. The live tiny run accepted selected sign-flip contributions. No robust screening is available inside the current MPC circuit.
2. **Cross-host security is unverified.** All integrated evidence is same-host/loopback. Party and control endpoint identity, TLS, firewalling, independent administration, key provisioning, and operational isolation require deployment validation.
3. **Full-model runtime is unverified.** Vector benchmarks completed through 100k elements; 250k exceeded the 300-second cap. Compile-only scaling to 2.12M is not a protocol execution or Flower full-model result.

## Other limitations

- No contribution clipping, range proofs for arbitrary client inputs, differential privacy, robust MPC aggregation, or dropout recovery.
- MTD obscures/changes client selection but does not classify honest clients or prevent malicious selection.
- Cohort differencing/inference and output-client compromise remain in the threat model.
- Control replay checks were unit tested; adversarial concurrent load and process-crash journal consistency were not stress-tested.
- Packaging build and exhaustive dependency/secret/static analysis were unavailable in the current environment.
- Evaluation evidence lacks statistical repetitions, comprehensive clean baselines, ASR, and broad numerical-error distributions.

## Required before stronger claims

Run independent-host parties with documented certificates and network policy; test full model under fixed resource caps; compare MPC outputs against plaintext references across seeded shapes/ranges; measure poisoning/backdoor ASR and clean accuracy over repeated seeds; and implement/validate any claimed clipping or robust aggregation inside the secure computation.

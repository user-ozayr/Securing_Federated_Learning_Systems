# Thesis claim verification

| Claim | Evidence | Demonstrated | Not demonstrated | Confidence | Thesis use |
|---|---|---|---|---|---|
| SPDZ2k secure weighted sum | Runtime vector CSV/raw logs; fresh tiny Flower run; encoding/output tests | Three local parties completed 8 through 100k vector cases and tiny Flower rounds | Broad plaintext equivalence, adversarial parties, full model, independent hosts | Medium for bounded local execution | Include with same-host and size limits |
| Malicious security with abort | MP-SPDZ v0.4.3 protocol matrix classifies SPDZ2k malicious/dishonest-majority; runtime docs give default SPDZ2k statistical parameter 64 (~2^-58); abort/cleanup tests | Implementation is configured for SPDZ2k; implementation failures abort | Independent protocol audit or malicious-party experiment | Medium for protocol choice, low for deployment | Describe assumptions and cite MP-SPDZ docs |
| MTD client selection | Unit tests and fresh two-round changing cohorts | Secret-seeded selection changed selected clients | Honest-client identification or poisoning defense | High for selection behavior | Include narrowly |
| Secret-derived schedule | Secret-length/seed behavior tests; fresh run uses ephemeral secret | Keyed behavior exercised locally | Secret management in production | Medium | Include as implementation behavior, caveat operations |
| Authentication/replay protection | HTTP tests, journal restart test, integrated local services | Valid request accepted; tampered/stale/replayed/reused inputs rejected in tests | Remote TLS and high-concurrency/crash analysis | Medium-high for tested endpoint cases | Include exact cases |
| Malformed protocol messages | Mocked tests for overflow/count/truncation/padding and error aborts | Several malformed output cases rejected | Live network tampering across parties | Medium for parser checks | State test boundary explicitly |
| Model-poisoning resistance | Sign-flip integrated run; no detector in SMPC | Secure sum accepts a selected malicious contribution | Attack mitigation, ASR, baseline performance | High confidence that resistance claim is unsupported | Do not claim resistance |
| Scalability | Same-host runtime through 100k; 250k capped; compile-only 2.12M | Bounded vector runtime data | Full-model runtime or larger successful execution | Medium | Include exact runs and cap |
| Integrated Flower/MPC | Fresh 2-round tiny simulation with actual local services | Small synthetic model integrated with MTD and 3 parties | Full-size model, cross-host deployment | Medium for tiny local integration | Describe as tiny same-host proof of integration |
| Reproducibility | Raw logs, CSVs, driver, test command retained | Local rerun commands and artifacts exist | Independent clean-machine replication and package build | Medium-low | Include environment/run instructions |
| MPC clipping | No clipping/range proof inside sum circuit | Not demonstrated | Secure per-client norm clipping | High | Explicitly state absent |
| Differential privacy | No DP mechanism/evaluation identified | Not demonstrated | Privacy guarantee or inference resistance | High | Do not claim |
| Robust aggregation inside MPC | Runtime rejects combination | Not implemented | Secure client scoring/filtering | High | Explicitly state absent |
| Cross-host deployment | Same-host evidence only | Not demonstrated | Independent parties and remote transport hardening | High | Do not claim |
| Dropout recovery | Strategy aborts on missing party/client | Fail-closed abort behavior | Recovery/threshold completion | High | State no recovery |
| Production readiness | No operational cross-host audit | Not demonstrated | Secure deployment, monitoring, key lifecycle, performance | High | Do not claim |


## MP-SPDZ source references

- [MP-SPDZ v0.4.3 protocol matrix](https://mp-spdz.readthedocs.io/en/v0.4.3/readme.html): SPDZ2k is classified as malicious-security under dishonest majority; MP-SPDZ says it has not undergone the security review expected for critical production code.
- [MP-SPDZ v0.4.3 runtime options](https://mp-spdz.readthedocs.io/en/v0.4.3/runtime-options.html): default SPDZ2k statistical security parameter is 64, with approximate cheating probability 2^-58. This run did not independently attest the effective binary flags.
- [MP-SPDZ v0.4.3 security fixes](https://mp-spdz.readthedocs.io/en/v0.4.3/security-fixes.html): documents historical issues, including an SPDZ2k issue; patch status for the running binary was not independently verified here.

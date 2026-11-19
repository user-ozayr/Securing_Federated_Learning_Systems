# Security limitations

Implemented and tested: HMAC-authenticated party control requests with timestamps and request IDs; persistent replay rejection; round reuse protections; TLS policy for control endpoints; client/proxy identity checks; server-side partition-count validation; an MPC equality check binding private count input to the public expected count; no plaintext-update fallback in secure mode; party failure cleanup; bytecode hash agreement. Unit tests cover these controls, and a tiny same-host run exercised the normal secure path.

Protocol assumptions: MP-SPDZ v0.4.3 SPDZ2k provides malicious security in the dishonest-majority model with abort. It does not ensure availability. The party service explicitly launches parties with `-e` and the local demo provisions SSL material, so the tested same-host runtime requests encrypted party links. Cross-host certificate provisioning, endpoint identity policy, renewal, firewalling, and independent trust-domain operation remain unvalidated.

Not established: full CIFAR-scale integrated execution, cross-host deployment, production key lifecycle, independent party isolation, resistance to denial of service, or independent cryptographic certification. The successful same-host run used one machine and therefore does not test independent trust domains.

MPC-BCD is not implemented. No differential privacy, universal Byzantine resilience, backdoor protection, or protection against within-bound poisoning is claimed. Robust individual-update screening is explicitly incompatible with the sum-only MPC path in the current configuration.

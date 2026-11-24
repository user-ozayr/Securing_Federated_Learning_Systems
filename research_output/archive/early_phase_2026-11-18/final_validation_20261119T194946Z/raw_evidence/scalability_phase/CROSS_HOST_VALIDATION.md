# Cross-host validation
Status: NOT VALIDATED (2026-11-18).

Only one host (oracle-vnic-3, 3 CPUs, private interface 10.0.0.163) was available. Clients and all three parties ran on that host over loopback; local demo binds parties to 127.0.0.1. This does not establish remote reachability, cross-host TLS/credentials, independent operators, WAN behavior, or remote failure cleanup.

Evidence: same-host tiny integration, 3 clients/parties, 8 parameters, one round, 16.32s, zero failures. No independent second host was provisioned.

Next: provision separate party hosts with authenticated routable endpoints/certificates. Start with a small synthetic round. Record placement, versions, RTT/bandwidth, per-party preprocessing/online time, traffic, logs, abort behavior and cleanup.

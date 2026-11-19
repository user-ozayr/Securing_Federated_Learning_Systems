# Experimental methodology and evidence status

## Integrated Flower run

The verified integrated Flower run is a same-host, one-round smoke test with three Flower clients, three SPDZ2k parties, and a synthetic 8-parameter model. It exercises client selection, local fit, private input submission, sample-count binding, aggregate reveal, and Flower model update. It is not CIFAR-10 training and cannot support model-accuracy or attack-mitigation claims. The Flower strategy test separately mocks the MPC helper calls to exercise mismatch/abort paths.

## Direct production-circuit profiling

The production weighted-sum circuit compiled at the full 2,122,187-parameter size. Actual deterministic three-party production client-I/O runs passed through 100,000 parameters. At 100k the run took 246.236 s including cleanup, with approximately 197 s offline preprocessing, 17 s online, and 42,999.4 MB global party traffic. A 250k run reached the 300 s watchdog without producing an aggregate. An earlier full-shape direct run likewise timed out without output. These are secure-aggregation microbenchmarks, not full model-training runs. See `research_output/runtime_optimization/` for raw logs, resource samples, and phase records.

The progressive harness used fixed-point scale 100,000 and three parties, while the documented hybrid YAML requests scale 1,000,000 and four parties. Do not conflate the two settings. The compiler-only full-size result is not protocol-runtime success.

## Clipping and attack evaluation

Coordinate clipping has compiler-count probes only; per-tensor norm clipping has a two-coordinate prototype and a 250-coordinate compile probe. Neither is integrated or validated at model scale. No clipping or poisoning defense result is claimed. The project has no completed five-seed comparison, no full attack matrix, and no cross-host result. The benchmark runner exists, but the paired matrix has not been executed.

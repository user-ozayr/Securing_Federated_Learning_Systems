# Sum-only SPDZ2k vs plaintext FedAvg: why the trajectories diverge

`FINAL_VALIDATION_REPORT.md` §4 notes that sum-only SPDZ2k runs and plaintext
FedAvg runs with the same seed drift apart over ten rounds (max |Δ accuracy| up to
0.51 under attacks that make training chaotic). This diagnostic locates the cause.

## Method

* `tools/sum_only_divergence.py` reads the packed instrumentation of every run,
  rebuilds the models the clients submitted (exact in float32 in all rounds) and
  aggregates them twice: with the integer arithmetic of the sum-only SPDZ2k path
  (`round(w · n · S)`, integer sum, `/ S / N`, cast to float32) and with the
  float64 arithmetic of plaintext FedAvg.
* `run_replays.sh` re-runs E1 baseline configurations in plaintext and changes
  only the aggregation arithmetic (`tools/sum_only_replay.py`): `fp1e6` uses the
  scale of the SPDZ2k runs, S = 10⁶; `fp2p40` is a control with S = 2⁴⁰.

## Results (`summary.txt`)

1. **The SPDZ2k output equals its fixed-point specification exactly.** In all
   324 sum-only rounds (36 runs), the applied model equals the fixed-point
   emulation in every one of the 2,202 coordinates.
2. **The difference to FedAvg is rounding at S = 10⁶.** Before the float32 cast
   the two aggregates differ by at most 10⁻¹⁰ (the quantisation bound). After the
   cast, 0–240 coordinates per round differ by one or a few ulps; 97 % of those
   are coordinates where the FedAvg value lies exactly halfway between two
   float32 values.
3. **The replays settle it.**

   | Replay | vs SPDZ2k sum-only | vs plaintext FedAvg |
   |---|---|---|
   | fp1e6 (15 runs: 5 attacks × 3 seeds) | identical global model in 10/10 rounds, identical metrics | differs from round 1 |
   | fp2p40 (6 runs) | differs from round 1 | identical global model in 10/10 rounds, identical metrics |

4. **The robust program has no such effect.** Its recorded models equal an exact
   plaintext replication in 700/700 SPDZ2k rounds and 240/240 plaintext rounds.

## Conclusion

The secure computation is exact. The divergence between `smpc_only` and
`baseline` comes from the choice S = 10⁶, which is not a power of two and so
rounds differently from float arithmetic at ties. SGD amplifies the resulting
one-ulp differences. A power-of-two scale (2⁴⁰ in the control) reproduces
FedAvg bit for bit. Per-seed differences between the two configurations are
therefore numerical, not a cost of secure aggregation.

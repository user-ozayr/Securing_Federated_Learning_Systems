# MP-SPDZ memory-order warning analysis

## Finding

The warning `Order of memory instructions not preserved, errors possible` is emitted by MP-SPDZ's compiler allocator when it cannot guarantee ordering around indirect memory accesses. MP-SPDZ documents `-M` as preserving memory instruction order, with possible efficiency cost; the compiler's allocator warning is associated with non-direct memory instructions. The production program uses dynamically indexed `Array` operations (including accumulation/indexed access), so the warning is relevant. It cannot be dismissed as harmless for this circuit.

## Mitigation and A/B evidence

The party service now compiles the production program with `-M` by default. This preserves the memory instruction order without reducing the SPDZ2k security parameter, removing MAC checks, or changing the aggregation protocol. An 8-parameter production-circuit A/B used identical deterministic inputs and counts [1,2,3]. With `-M` off, the warning appeared; with `-M` on, it did not. Both returned the same reference aggregate exactly, same total sample count, 4,282 triples and 29 VM rounds. Compile time was about 1.379 s off and 3.638 s on per party. Protocol time was about 4.21 s offline+online in either case; observed global traffic was 487.03 MB in either case. This tiny A/B establishes behavior only for that test vector and does not prove every dynamic access schedule correct.

## Circuit-specific considerations

- **Initialization / indexed accumulation:** indirect `Array` accesses are why preserving ordering is prudent. The test exercises accumulation for a small vector, but not exhaustive address schedules.
- **Client input order:** the production protocol reads each client input in an explicit client loop and chunk sequence. The 8/1k/10k/50k/100k probes validate aggregate output and sample total for the deterministic input sequence, but do not inject reordering or adversarial wire order.
- **Chunk processing and vectorized reveal:** successful post-fix runs cover final padded chunks and a single full-array reveal. The initial 10k failure exposed an I/O framing mismatch: client code expected repeated chunk messages while `Array.reveal_to_clients` sends a contiguous vector. The receiver now reads the exact full output length in one message. This issue was not evidence of an incorrect MPC result.
- **Correctness stance:** `-M` removes the compiler warning and is the safe supported option for this code. Keep it enabled unless a reviewed alternative is proven equivalent. No claim is made that the warning was harmless, nor that the small A/B exhaustively proves correctness.

## Evidence and limits

Comparison logs are in `raw/params_8_memorder_off/` and `raw/params_8_memorder_on/`. Progressive numerical checks and protocol logs are under `raw/`. No reference circuit using an independently redesigned safe memory pattern was implemented; the comparison is the same production circuit compiled with MP-SPDZ's documented memory-order-preserving option.

# Chunked production-circuit validation

## What was exercised

The production circuit handles model inputs in chunks of 1,024 values, with client sample-count binding and a final aggregate-only output. Direct three-party runs used deterministic client vectors (client id times 0.01), counts [1,2,3], and an independent Python weighted-sum reference. Runs at 8, 1,000, 10,000, 50,000 and 100,000 model parameters passed with maximum decoded error 0 and validated total sample count. Input encoding includes the count value, so the padded vector covers 9, 1,001, 10,001, 50,001, or 100,001 values as applicable; these sizes exercise padding/tails around the 1,024-element boundary.

## Output framing correction

The first 10k attempt failed at output with `unexpected data length`. The circuit's `Array.reveal_to_clients` emits one contiguous output vector; the client incorrectly attempted repeated 1,024-value receives. The client now reads the full padded output count in one receive. The corrected 10k, 50k and 100k runs pass. Both the failed attempt and its logs are retained in `raw/params_10000_memorder_on/`; the corrected attempt is `raw/params_10000_memorder_on_attempt_1795009072/`.

## Segmentation boundary

These are chunked input transfers within one monolithic MPC program and one protocol round. They do not validate independently executed MPC segments or segment reassembly. Empty/missing/reordered/duplicate chunks, missing client inputs, failed party/segment, wrong segment index, and incorrect total count fault injection were not run. No claim is made that segmented execution is equivalent to the monolithic circuit. Abort and cleanup were observed on the 250k watchdog case; a partial result was not accepted.

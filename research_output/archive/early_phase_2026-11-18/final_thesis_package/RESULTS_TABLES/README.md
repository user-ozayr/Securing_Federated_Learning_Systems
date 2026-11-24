# Results table status

| Run | Parameters | Clients / parties | Runtime | Result |
|---|---:|---:|---:|---|
| Earlier same-host secure smoke | 8 | 3 / 3 | 11.598s total; 0.1603s aggregation | Completed, synthetic model; historical run |
| Chunked same-host secure smoke | 8 | 3 / 3 | 16.32s total; 0.807s aggregation | Completed, synthetic model; current integration evidence |
| Exact production-source full-shape compile | 2,122,187 | 3-party program | 1.751s; 62.2MiB compiler RSS | Compile completed; 8,491,194 triples, 29 scheduled rounds |
| Full-shape three-party protocol attempt | 2,122,187 | 3 parties | Stopped at 300s guard | No aggregate returned; cleanup succeeded |

The smoke tests use synthetic data and a tiny model. No accuracy claim, comparative defense result, or full-model protocol success is made. See BENCHMARK_RESULTS.csv and RAW_EXPERIMENT_RESULTS for detailed measurements.

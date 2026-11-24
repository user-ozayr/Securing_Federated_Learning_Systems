# Raw log index

Raw logs are stored next to the artefact they belong to; this index lists them.
Paths are relative to `research_output/completion/`.

Log files (`*.log`) are not tracked by git; the repository's `.gitignore` excludes them.
They remain on the research host, and the SHA-256 of every one of them is recorded in
`final_validation_manifest.json`.

## Suite drivers and evidence chains

* `experiments/final_chain.log` (409 bytes)
* `experiments/followup_chain.log` (2,087 bytes)
* `experiments/suite_driver.log` (17,379 bytes)
* `experiments/suite_driver_pass2.log` (1,561 bytes)
* `experiments/suite_driver_pass3.log` (81 bytes)
* `analysis_driver.log` (177 bytes)
* `analysis_driver_cohort_fix.log` (177 bytes)
* `analysis_driver_matrix_fix.log` (156 bytes)
* `benchmarks_driver.log` (3,114 bytes)
* `independent_validation_driver.log` (0 bytes)

## Experiment runs (one `run.log` per run)

Status counts: aborted 5, completed 223.

| Study | Run | Status | Commit | Log |
|---|---|---|---|---|
| e1 | e1__baseline__backdoor__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__backdoor__s101/run.log` |
| e1 | e1__baseline__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__backdoor__s102/run.log` |
| e1 | e1__baseline__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__backdoor__s103/run.log` |
| e1 | e1__baseline__label_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__label_flip__s101/run.log` |
| e1 | e1__baseline__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__label_flip__s102/run.log` |
| e1 | e1__baseline__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__label_flip__s103/run.log` |
| e1 | e1__baseline__none__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__none__s101/run.log` |
| e1 | e1__baseline__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__none__s102/run.log` |
| e1 | e1__baseline__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__none__s103/run.log` |
| e1 | e1__baseline__random_noise__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__random_noise__s101/run.log` |
| e1 | e1__baseline__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__random_noise__s102/run.log` |
| e1 | e1__baseline__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__random_noise__s103/run.log` |
| e1 | e1__baseline__scaled_replacement__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__scaled_replacement__s101/run.log` |
| e1 | e1__baseline__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__scaled_replacement__s102/run.log` |
| e1 | e1__baseline__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__scaled_replacement__s103/run.log` |
| e1 | e1__baseline__sign_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__baseline__sign_flip__s101/run.log` |
| e1 | e1__baseline__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__sign_flip__s102/run.log` |
| e1 | e1__baseline__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__baseline__sign_flip__s103/run.log` |
| e1 | e1__mtd_only__backdoor__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__backdoor__s101/run.log` |
| e1 | e1__mtd_only__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__backdoor__s102/run.log` |
| e1 | e1__mtd_only__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__backdoor__s103/run.log` |
| e1 | e1__mtd_only__label_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__label_flip__s101/run.log` |
| e1 | e1__mtd_only__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__label_flip__s102/run.log` |
| e1 | e1__mtd_only__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__label_flip__s103/run.log` |
| e1 | e1__mtd_only__none__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__none__s101/run.log` |
| e1 | e1__mtd_only__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__none__s102/run.log` |
| e1 | e1__mtd_only__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__none__s103/run.log` |
| e1 | e1__mtd_only__random_noise__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__random_noise__s101/run.log` |
| e1 | e1__mtd_only__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__random_noise__s102/run.log` |
| e1 | e1__mtd_only__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__random_noise__s103/run.log` |
| e1 | e1__mtd_only__scaled_replacement__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__scaled_replacement__s101/run.log` |
| e1 | e1__mtd_only__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__scaled_replacement__s102/run.log` |
| e1 | e1__mtd_only__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__scaled_replacement__s103/run.log` |
| e1 | e1__mtd_only__sign_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__mtd_only__sign_flip__s101/run.log` |
| e1 | e1__mtd_only__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__sign_flip__s102/run.log` |
| e1 | e1__mtd_only__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__mtd_only__sign_flip__s103/run.log` |
| e1 | e1__smpc_clip__backdoor__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__backdoor__s101/run.log` |
| e1 | e1__smpc_clip__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__backdoor__s102/run.log` |
| e1 | e1__smpc_clip__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__backdoor__s103/run.log` |
| e1 | e1__smpc_clip__label_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__label_flip__s101/run.log` |
| e1 | e1__smpc_clip__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__label_flip__s102/run.log` |
| e1 | e1__smpc_clip__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__label_flip__s103/run.log` |
| e1 | e1__smpc_clip__none__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__none__s101/run.log` |
| e1 | e1__smpc_clip__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__none__s102/run.log` |
| e1 | e1__smpc_clip__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__none__s103/run.log` |
| e1 | e1__smpc_clip__random_noise__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__random_noise__s101/run.log` |
| e1 | e1__smpc_clip__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__random_noise__s102/run.log` |
| e1 | e1__smpc_clip__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__random_noise__s103/run.log` |
| e1 | e1__smpc_clip__scaled_replacement__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__scaled_replacement__s101/run.log` |
| e1 | e1__smpc_clip__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__scaled_replacement__s102/run.log` |
| e1 | e1__smpc_clip__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__scaled_replacement__s103/run.log` |
| e1 | e1__smpc_clip__sign_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_clip__sign_flip__s101/run.log` |
| e1 | e1__smpc_clip__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__sign_flip__s102/run.log` |
| e1 | e1__smpc_clip__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_clip__sign_flip__s103/run.log` |
| e1 | e1__smpc_defence_mtd__backdoor__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_defence_mtd__backdoor__s101/run.log` |
| e1 | e1__smpc_defence_mtd__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__backdoor__s102/run.log` |
| e1 | e1__smpc_defence_mtd__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__backdoor__s103/run.log` |
| e1 | e1__smpc_defence_mtd__label_flip__s101 | completed | 071fbbc | `experiments/runs/e1/e1__smpc_defence_mtd__label_flip__s101/run.log` |
| e1 | e1__smpc_defence_mtd__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__label_flip__s102/run.log` |
| e1 | e1__smpc_defence_mtd__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__label_flip__s103/run.log` |
| e1 | e1__smpc_defence_mtd__none__s101 | completed | 071fbbc | `experiments/runs/e1/e1__smpc_defence_mtd__none__s101/run.log` |
| e1 | e1__smpc_defence_mtd__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__none__s102/run.log` |
| e1 | e1__smpc_defence_mtd__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__none__s103/run.log` |
| e1 | e1__smpc_defence_mtd__random_noise__s101 | completed | 071fbbc | `experiments/runs/e1/e1__smpc_defence_mtd__random_noise__s101/run.log` |
| e1 | e1__smpc_defence_mtd__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__random_noise__s102/run.log` |
| e1 | e1__smpc_defence_mtd__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__random_noise__s103/run.log` |
| e1 | e1__smpc_defence_mtd__scaled_replacement__s101 | completed | 071fbbc | `experiments/runs/e1/e1__smpc_defence_mtd__scaled_replacement__s101/run.log` |
| e1 | e1__smpc_defence_mtd__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__scaled_replacement__s102/run.log` |
| e1 | e1__smpc_defence_mtd__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__scaled_replacement__s103/run.log` |
| e1 | e1__smpc_defence_mtd__sign_flip__s101 | completed | 071fbbc | `experiments/runs/e1/e1__smpc_defence_mtd__sign_flip__s101/run.log` |
| e1 | e1__smpc_defence_mtd__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__sign_flip__s102/run.log` |
| e1 | e1__smpc_defence_mtd__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_defence_mtd__sign_flip__s103/run.log` |
| e1 | e1__smpc_mtd__backdoor__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__backdoor__s101/run.log` |
| e1 | e1__smpc_mtd__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__backdoor__s102/run.log` |
| e1 | e1__smpc_mtd__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__backdoor__s103/run.log` |
| e1 | e1__smpc_mtd__label_flip__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__label_flip__s101/run.log` |
| e1 | e1__smpc_mtd__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__label_flip__s102/run.log` |
| e1 | e1__smpc_mtd__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__label_flip__s103/run.log` |
| e1 | e1__smpc_mtd__none__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__none__s101/run.log` |
| e1 | e1__smpc_mtd__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__none__s102/run.log` |
| e1 | e1__smpc_mtd__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__none__s103/run.log` |
| e1 | e1__smpc_mtd__random_noise__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__random_noise__s101/run.log` |
| e1 | e1__smpc_mtd__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__random_noise__s102/run.log` |
| e1 | e1__smpc_mtd__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__random_noise__s103/run.log` |
| e1 | e1__smpc_mtd__scaled_replacement__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__scaled_replacement__s101/run.log` |
| e1 | e1__smpc_mtd__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__scaled_replacement__s102/run.log` |
| e1 | e1__smpc_mtd__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__scaled_replacement__s103/run.log` |
| e1 | e1__smpc_mtd__sign_flip__s101 | aborted | 99366f7 | `experiments/runs/e1/e1__smpc_mtd__sign_flip__s101/run.log` |
| e1 | e1__smpc_mtd__sign_flip__s102 | aborted | 99366f7 | `experiments/runs/e1/e1__smpc_mtd__sign_flip__s102/run.log` |
| e1 | e1__smpc_mtd__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_mtd__sign_flip__s103/run.log` |
| e1 | e1__smpc_only__backdoor__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__backdoor__s101/run.log` |
| e1 | e1__smpc_only__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__backdoor__s102/run.log` |
| e1 | e1__smpc_only__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__backdoor__s103/run.log` |
| e1 | e1__smpc_only__label_flip__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_only__label_flip__s101/run.log` |
| e1 | e1__smpc_only__label_flip__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__label_flip__s102/run.log` |
| e1 | e1__smpc_only__label_flip__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__label_flip__s103/run.log` |
| e1 | e1__smpc_only__none__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_only__none__s101/run.log` |
| e1 | e1__smpc_only__none__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__none__s102/run.log` |
| e1 | e1__smpc_only__none__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__none__s103/run.log` |
| e1 | e1__smpc_only__random_noise__s101 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__random_noise__s101/run.log` |
| e1 | e1__smpc_only__random_noise__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__random_noise__s102/run.log` |
| e1 | e1__smpc_only__random_noise__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__random_noise__s103/run.log` |
| e1 | e1__smpc_only__scaled_replacement__s101 | completed | 68f8970 | `experiments/runs/e1/e1__smpc_only__scaled_replacement__s101/run.log` |
| e1 | e1__smpc_only__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__scaled_replacement__s102/run.log` |
| e1 | e1__smpc_only__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1/e1__smpc_only__scaled_replacement__s103/run.log` |
| e1 | e1__smpc_only__sign_flip__s101 | aborted | 99366f7 | `experiments/runs/e1/e1__smpc_only__sign_flip__s101/run.log` |
| e1 | e1__smpc_only__sign_flip__s102 | aborted | 99366f7 | `experiments/runs/e1/e1__smpc_only__sign_flip__s102/run.log` |
| e1 | e1__smpc_only__sign_flip__s103 | aborted | 99366f7 | `experiments/runs/e1/e1__smpc_only__sign_flip__s103/run.log` |
| e1x | e1x__plaintext_robust__backdoor__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__backdoor__s101/run.log` |
| e1x | e1x__plaintext_robust__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__backdoor__s102/run.log` |
| e1x | e1x__plaintext_robust__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__backdoor__s103/run.log` |
| e1x | e1x__plaintext_robust__none__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__none__s101/run.log` |
| e1x | e1x__plaintext_robust__none__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__none__s102/run.log` |
| e1x | e1x__plaintext_robust__none__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__none__s103/run.log` |
| e1x | e1x__plaintext_robust__scaled_replacement__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__scaled_replacement__s101/run.log` |
| e1x | e1x__plaintext_robust__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__scaled_replacement__s102/run.log` |
| e1x | e1x__plaintext_robust__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__scaled_replacement__s103/run.log` |
| e1x | e1x__plaintext_robust__sign_flip__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__sign_flip__s101/run.log` |
| e1x | e1x__plaintext_robust__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__sign_flip__s102/run.log` |
| e1x | e1x__plaintext_robust__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__plaintext_robust__sign_flip__s103/run.log` |
| e1x | e1x__smpc_defence__backdoor__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__backdoor__s101/run.log` |
| e1x | e1x__smpc_defence__backdoor__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__backdoor__s102/run.log` |
| e1x | e1x__smpc_defence__backdoor__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__backdoor__s103/run.log` |
| e1x | e1x__smpc_defence__none__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__none__s101/run.log` |
| e1x | e1x__smpc_defence__none__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__none__s102/run.log` |
| e1x | e1x__smpc_defence__none__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__none__s103/run.log` |
| e1x | e1x__smpc_defence__scaled_replacement__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__scaled_replacement__s101/run.log` |
| e1x | e1x__smpc_defence__scaled_replacement__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__scaled_replacement__s102/run.log` |
| e1x | e1x__smpc_defence__scaled_replacement__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__scaled_replacement__s103/run.log` |
| e1x | e1x__smpc_defence__sign_flip__s101 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__sign_flip__s101/run.log` |
| e1x | e1x__smpc_defence__sign_flip__s102 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__sign_flip__s102/run.log` |
| e1x | e1x__smpc_defence__sign_flip__s103 | completed | f75eb7b | `experiments/runs/e1x/e1x__smpc_defence__sign_flip__s103/run.log` |
| e1x | e1x__smpc_screen__backdoor__s101 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__backdoor__s101/run.log` |
| e1x | e1x__smpc_screen__backdoor__s102 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__backdoor__s102/run.log` |
| e1x | e1x__smpc_screen__backdoor__s103 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__backdoor__s103/run.log` |
| e1x | e1x__smpc_screen__none__s101 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__none__s101/run.log` |
| e1x | e1x__smpc_screen__none__s102 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__none__s102/run.log` |
| e1x | e1x__smpc_screen__none__s103 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__none__s103/run.log` |
| e1x | e1x__smpc_screen__scaled_replacement__s101 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__scaled_replacement__s101/run.log` |
| e1x | e1x__smpc_screen__scaled_replacement__s102 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__scaled_replacement__s102/run.log` |
| e1x | e1x__smpc_screen__scaled_replacement__s103 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__scaled_replacement__s103/run.log` |
| e1x | e1x__smpc_screen__sign_flip__s101 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__sign_flip__s101/run.log` |
| e1x | e1x__smpc_screen__sign_flip__s102 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__sign_flip__s102/run.log` |
| e1x | e1x__smpc_screen__sign_flip__s103 | completed | 99366f7 | `experiments/runs/e1x/e1x__smpc_screen__sign_flip__s103/run.log` |
| e2 | e2__baseline__adaptive_backdoor__s101 | completed | f75eb7b | `experiments/runs/e2/e2__baseline__adaptive_backdoor__s101/run.log` |
| e2 | e2__baseline__adaptive_backdoor__s102 | completed | f75eb7b | `experiments/runs/e2/e2__baseline__adaptive_backdoor__s102/run.log` |
| e2 | e2__baseline__adaptive_backdoor__s103 | completed | f75eb7b | `experiments/runs/e2/e2__baseline__adaptive_backdoor__s103/run.log` |
| e2 | e2__plaintext_robust__adaptive_backdoor__s101 | completed | f75eb7b | `experiments/runs/e2/e2__plaintext_robust__adaptive_backdoor__s101/run.log` |
| e2 | e2__plaintext_robust__adaptive_backdoor__s102 | completed | f75eb7b | `experiments/runs/e2/e2__plaintext_robust__adaptive_backdoor__s102/run.log` |
| e2 | e2__plaintext_robust__adaptive_backdoor__s103 | completed | f75eb7b | `experiments/runs/e2/e2__plaintext_robust__adaptive_backdoor__s103/run.log` |
| e2 | e2__smpc_clip__adaptive_backdoor__s101 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_clip__adaptive_backdoor__s101/run.log` |
| e2 | e2__smpc_clip__adaptive_backdoor__s102 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_clip__adaptive_backdoor__s102/run.log` |
| e2 | e2__smpc_clip__adaptive_backdoor__s103 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_clip__adaptive_backdoor__s103/run.log` |
| e2 | e2__smpc_defence_mtd__adaptive_backdoor__s101 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_defence_mtd__adaptive_backdoor__s101/run.log` |
| e2 | e2__smpc_defence_mtd__adaptive_backdoor__s102 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_defence_mtd__adaptive_backdoor__s102/run.log` |
| e2 | e2__smpc_defence_mtd__adaptive_backdoor__s103 | completed | f75eb7b | `experiments/runs/e2/e2__smpc_defence_mtd__adaptive_backdoor__s103/run.log` |
| e3 | e3__baseline__backdoor__deterministic__just_in_time__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__just_in_time__s101/run.log` |
| e3 | e3__baseline__backdoor__deterministic__just_in_time__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__just_in_time__s102/run.log` |
| e3 | e3__baseline__backdoor__deterministic__just_in_time__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__just_in_time__s103/run.log` |
| e3 | e3__baseline__backdoor__deterministic__predictive__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__predictive__s101/run.log` |
| e3 | e3__baseline__backdoor__deterministic__predictive__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__predictive__s102/run.log` |
| e3 | e3__baseline__backdoor__deterministic__predictive__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__deterministic__predictive__s103/run.log` |
| e3 | e3__baseline__backdoor__secret__just_in_time__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__just_in_time__s101/run.log` |
| e3 | e3__baseline__backdoor__secret__just_in_time__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__just_in_time__s102/run.log` |
| e3 | e3__baseline__backdoor__secret__just_in_time__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__just_in_time__s103/run.log` |
| e3 | e3__baseline__backdoor__secret__predictive__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__predictive__s101/run.log` |
| e3 | e3__baseline__backdoor__secret__predictive__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__predictive__s102/run.log` |
| e3 | e3__baseline__backdoor__secret__predictive__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__secret__predictive__s103/run.log` |
| e3 | e3__baseline__backdoor__static__just_in_time__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__just_in_time__s101/run.log` |
| e3 | e3__baseline__backdoor__static__just_in_time__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__just_in_time__s102/run.log` |
| e3 | e3__baseline__backdoor__static__just_in_time__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__just_in_time__s103/run.log` |
| e3 | e3__baseline__backdoor__static__predictive__s101 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__predictive__s101/run.log` |
| e3 | e3__baseline__backdoor__static__predictive__s102 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__predictive__s102/run.log` |
| e3 | e3__baseline__backdoor__static__predictive__s103 | completed | f75eb7b | `experiments/runs/e3/e3__baseline__backdoor__static__predictive__s103/run.log` |
| e4 | e4__baseline__backdoor__boost16__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost16__s101/run.log` |
| e4 | e4__baseline__backdoor__boost16__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost16__s102/run.log` |
| e4 | e4__baseline__backdoor__boost1__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost1__s101/run.log` |
| e4 | e4__baseline__backdoor__boost1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost1__s102/run.log` |
| e4 | e4__baseline__backdoor__boost2__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost2__s101/run.log` |
| e4 | e4__baseline__backdoor__boost2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost2__s102/run.log` |
| e4 | e4__baseline__backdoor__boost8__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost8__s101/run.log` |
| e4 | e4__baseline__backdoor__boost8__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__boost8__s102/run.log` |
| e4 | e4__baseline__backdoor__m1__s101 | completed | f75eb7b | `experiments/runs/e4/e4__baseline__backdoor__m1__s101/run.log` |
| e4 | e4__baseline__backdoor__m1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__m1__s102/run.log` |
| e4 | e4__baseline__backdoor__m2__s101 | completed | f75eb7b | `experiments/runs/e4/e4__baseline__backdoor__m2__s101/run.log` |
| e4 | e4__baseline__backdoor__m2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__m2__s102/run.log` |
| e4 | e4__baseline__backdoor__m4__s101 | completed | f75eb7b | `experiments/runs/e4/e4__baseline__backdoor__m4__s101/run.log` |
| e4 | e4__baseline__backdoor__m4__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__m4__s102/run.log` |
| e4 | e4__baseline__backdoor__m5__s101 | completed | f75eb7b | `experiments/runs/e4/e4__baseline__backdoor__m5__s101/run.log` |
| e4 | e4__baseline__backdoor__m5__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__backdoor__m5__s102/run.log` |
| e4 | e4__baseline__sign_flip__str1__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str1__s101/run.log` |
| e4 | e4__baseline__sign_flip__str1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str1__s102/run.log` |
| e4 | e4__baseline__sign_flip__str2__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str2__s101/run.log` |
| e4 | e4__baseline__sign_flip__str2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str2__s102/run.log` |
| e4 | e4__baseline__sign_flip__str8__s101 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str8__s101/run.log` |
| e4 | e4__baseline__sign_flip__str8__s102 | completed | 99366f7 | `experiments/runs/e4/e4__baseline__sign_flip__str8__s102/run.log` |
| e4 | e4__reference_defence__backdoor__boost16__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost16__s101/run.log` |
| e4 | e4__reference_defence__backdoor__boost16__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost16__s102/run.log` |
| e4 | e4__reference_defence__backdoor__boost1__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost1__s101/run.log` |
| e4 | e4__reference_defence__backdoor__boost1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost1__s102/run.log` |
| e4 | e4__reference_defence__backdoor__boost2__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost2__s101/run.log` |
| e4 | e4__reference_defence__backdoor__boost2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost2__s102/run.log` |
| e4 | e4__reference_defence__backdoor__boost8__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost8__s101/run.log` |
| e4 | e4__reference_defence__backdoor__boost8__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__boost8__s102/run.log` |
| e4 | e4__reference_defence__backdoor__default__s101 | completed | f75eb7b | `experiments/runs/e4/e4__reference_defence__backdoor__default__s101/run.log` |
| e4 | e4__reference_defence__backdoor__default__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__default__s102/run.log` |
| e4 | e4__reference_defence__backdoor__m1__s101 | completed | f75eb7b | `experiments/runs/e4/e4__reference_defence__backdoor__m1__s101/run.log` |
| e4 | e4__reference_defence__backdoor__m1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m1__s102/run.log` |
| e4 | e4__reference_defence__backdoor__m2__s101 | completed | f75eb7b | `experiments/runs/e4/e4__reference_defence__backdoor__m2__s101/run.log` |
| e4 | e4__reference_defence__backdoor__m2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m2__s102/run.log` |
| e4 | e4__reference_defence__backdoor__m4__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m4__s101/run.log` |
| e4 | e4__reference_defence__backdoor__m4__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m4__s102/run.log` |
| e4 | e4__reference_defence__backdoor__m5__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m5__s101/run.log` |
| e4 | e4__reference_defence__backdoor__m5__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__backdoor__m5__s102/run.log` |
| e4 | e4__reference_defence__sign_flip__str1__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str1__s101/run.log` |
| e4 | e4__reference_defence__sign_flip__str1__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str1__s102/run.log` |
| e4 | e4__reference_defence__sign_flip__str2__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str2__s101/run.log` |
| e4 | e4__reference_defence__sign_flip__str2__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str2__s102/run.log` |
| e4 | e4__reference_defence__sign_flip__str8__s101 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str8__s101/run.log` |
| e4 | e4__reference_defence__sign_flip__str8__s102 | completed | 99366f7 | `experiments/runs/e4/e4__reference_defence__sign_flip__str8__s102/run.log` |
| e5 | e5__baseline__backdoor__dir05__s101 | completed | 99366f7 | `experiments/runs/e5/e5__baseline__backdoor__dir05__s101/run.log` |
| e5 | e5__baseline__backdoor__dir05__s102 | completed | 99366f7 | `experiments/runs/e5/e5__baseline__backdoor__dir05__s102/run.log` |
| e5 | e5__baseline__none__dir05__s101 | completed | 99366f7 | `experiments/runs/e5/e5__baseline__none__dir05__s101/run.log` |
| e5 | e5__baseline__none__dir05__s102 | completed | 99366f7 | `experiments/runs/e5/e5__baseline__none__dir05__s102/run.log` |
| e5 | e5__smpc_defence_mtd__backdoor__dir05__s101 | completed | 99366f7 | `experiments/runs/e5/e5__smpc_defence_mtd__backdoor__dir05__s101/run.log` |
| e5 | e5__smpc_defence_mtd__backdoor__dir05__s102 | completed | 99366f7 | `experiments/runs/e5/e5__smpc_defence_mtd__backdoor__dir05__s102/run.log` |
| e5 | e5__smpc_defence_mtd__none__dir05__s101 | completed | 99366f7 | `experiments/runs/e5/e5__smpc_defence_mtd__none__dir05__s101/run.log` |
| e5 | e5__smpc_defence_mtd__none__dir05__s102 | completed | 99366f7 | `experiments/runs/e5/e5__smpc_defence_mtd__none__dir05__s102/run.log` |

## Archived failed attempts (kept unchanged; each was repeated)

| Archive | Study | Run | Status at archiving | Log |
|---|---|---|---|---|
| 20261120T122906Z | e1 | e1__smpc_mtd__sign_flip__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1/e1__smpc_mtd__sign_flip__s101/run.log` |
| 20261120T122906Z | e1 | e1__smpc_mtd__sign_flip__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1/e1__smpc_mtd__sign_flip__s102/run.log` |
| 20261120T122906Z | e1 | e1__smpc_only__sign_flip__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1/e1__smpc_only__sign_flip__s101/run.log` |
| 20261120T122906Z | e1 | e1__smpc_only__sign_flip__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1/e1__smpc_only__sign_flip__s102/run.log` |
| 20261120T122906Z | e1 | e1__smpc_only__sign_flip__s103 | failed | `experiments/failed_attempts/20261120T122906Z/e1/e1__smpc_only__sign_flip__s103/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__backdoor__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__backdoor__s101/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__backdoor__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__backdoor__s102/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__backdoor__s103 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__backdoor__s103/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__none__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__none__s101/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__none__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__none__s102/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__none__s103 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__none__s103/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__scaled_replacement__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__scaled_replacement__s101/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__scaled_replacement__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__scaled_replacement__s102/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__scaled_replacement__s103 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__scaled_replacement__s103/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__sign_flip__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__sign_flip__s101/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__sign_flip__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__sign_flip__s102/run.log` |
| 20261120T122906Z | e1x | e1x__smpc_screen__sign_flip__s103 | failed | `experiments/failed_attempts/20261120T122906Z/e1x/e1x__smpc_screen__sign_flip__s103/run.log` |
| 20261120T122906Z | e5 | e5__smpc_defence_mtd__backdoor__dir05__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e5/e5__smpc_defence_mtd__backdoor__dir05__s101/run.log` |
| 20261120T122906Z | e5 | e5__smpc_defence_mtd__backdoor__dir05__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e5/e5__smpc_defence_mtd__backdoor__dir05__s102/run.log` |
| 20261120T122906Z | e5 | e5__smpc_defence_mtd__none__dir05__s101 | failed | `experiments/failed_attempts/20261120T122906Z/e5/e5__smpc_defence_mtd__none__dir05__s101/run.log` |
| 20261120T122906Z | e5 | e5__smpc_defence_mtd__none__dir05__s102 | failed | `experiments/failed_attempts/20261120T122906Z/e5/e5__smpc_defence_mtd__none__dir05__s102/run.log` |
| 20261120T154646Z_infra | e1x | e1x__smpc_screen__scaled_replacement__s102 | aborted | `experiments/failed_attempts/20261120T154646Z_infra/e1x/e1x__smpc_screen__scaled_replacement__s102/run.log` |

Reason note: `experiments/failed_attempts/20261120T154646Z_infra/e1x/REASON.txt`

## SPDZ2k validation scenarios

* `experiments/mpc_validation/party_logs/party-0_fl_spdz_6ee5fb66480af0162fc3-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_773e368922b3120d7531-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_9e559f425e4c6ef8f7aa-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_b30911d0b6519d405e43-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_d6daa727d196d8f32fb8-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_d6e1c9d8a8238daa6de1-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_da0a343dc4d7e4015abd-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_e0bb9a5098094b80036a-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_e6cbae87020b5e809799-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_f148abe0cac54a646e0f-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_f7d0912e6401e36f9430-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_fa8644179d19087e661c-P0.log`
* `experiments/mpc_validation/party_logs/party-0_fl_spdz_fd03ad56f70ed2574d7f-P0.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_6ee5fb66480af0162fc3-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_773e368922b3120d7531-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_9e559f425e4c6ef8f7aa-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_b30911d0b6519d405e43-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_d6daa727d196d8f32fb8-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_d6e1c9d8a8238daa6de1-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_da0a343dc4d7e4015abd-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_e0bb9a5098094b80036a-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_e6cbae87020b5e809799-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_f148abe0cac54a646e0f-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_f7d0912e6401e36f9430-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_fa8644179d19087e661c-P1.log`
* `experiments/mpc_validation/party_logs/party-1_fl_spdz_fd03ad56f70ed2574d7f-P1.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_6ee5fb66480af0162fc3-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_773e368922b3120d7531-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_9e559f425e4c6ef8f7aa-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_b30911d0b6519d405e43-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_d6daa727d196d8f32fb8-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_d6e1c9d8a8238daa6de1-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_da0a343dc4d7e4015abd-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_e0bb9a5098094b80036a-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_e6cbae87020b5e809799-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_f148abe0cac54a646e0f-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_f7d0912e6401e36f9430-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_fa8644179d19087e661c-P2.log`
* `experiments/mpc_validation/party_logs/party-2_fl_spdz_fd03ad56f70ed2574d7f-P2.log`
* `experiments/mpc_validation/run.log`
* `experiments/mpc_validation/scenario_results.json`
* `experiments/mpc_validation/scenario_summary.csv`

## Benchmarks

* `benchmarks/raw_logs/`: 101 MP-SPDZ party logs
* `benchmarks_driver.log` (driver output, see above)

## Independent validation (fresh clone)

* `independent_validation/clone_info.txt`
* `independent_validation/import_provenance_fresh_clone.txt`
* `independent_validation/import_provenance_fresh_clone_final_commit.txt`
* `independent_validation/import_provenance_worktree.txt`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_07a808f34ed3a6622d7a-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_1a3b290d329841784424-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_2179276369b8fd6438c2-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_23ac38330f623d2482a8-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_3322f10eb445091d667c-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_35b4f984a5b59153e366-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_36ae0dfe89e1b88b6280-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_4bee6b0e71f93c3949b2-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_65e3e79ea4286578a91b-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_b69f1eb527bdbc3fae37-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_efcb5b3a36af248ef228-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_f286cc03b057343b5da7-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-0_fl_spdz_f6323aa66fb310120fd2-P0.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_07a808f34ed3a6622d7a-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_1a3b290d329841784424-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_2179276369b8fd6438c2-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_23ac38330f623d2482a8-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_3322f10eb445091d667c-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_35b4f984a5b59153e366-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_36ae0dfe89e1b88b6280-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_4bee6b0e71f93c3949b2-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_65e3e79ea4286578a91b-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_b69f1eb527bdbc3fae37-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_efcb5b3a36af248ef228-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_f286cc03b057343b5da7-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-1_fl_spdz_f6323aa66fb310120fd2-P1.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_07a808f34ed3a6622d7a-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_1a3b290d329841784424-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_2179276369b8fd6438c2-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_23ac38330f623d2482a8-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_3322f10eb445091d667c-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_35b4f984a5b59153e366-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_36ae0dfe89e1b88b6280-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_4bee6b0e71f93c3949b2-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_65e3e79ea4286578a91b-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_b69f1eb527bdbc3fae37-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_efcb5b3a36af248ef228-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_f286cc03b057343b5da7-P2.log`
* `independent_validation/mpc_validation_fresh/party_logs/party-2_fl_spdz_f6323aa66fb310120fd2-P2.log`
* `independent_validation/mpc_validation_fresh.log`
* `independent_validation/pytest_fresh_clone.txt`
* `independent_validation/pytest_fresh_clone_final_commit.txt`
* `independent_validation/pytest_mpspdz_fresh_clone.txt`
* `independent_validation/rerun_comparison.txt`
* `independent_validation/reruns/e1__baseline__backdoor__s101.log`
* `independent_validation/reruns/e1x__smpc_defence__backdoor__s101.log`
* `independent_validation/supplementary_clone_info.txt`

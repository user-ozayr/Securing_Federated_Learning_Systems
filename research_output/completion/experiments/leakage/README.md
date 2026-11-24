# E6 – Update leakage: what the coordinator can reconstruct

**Question.** SPDZ2k is meant to keep individual model updates away from the
coordinator. How much private training data does the coordinator still recover
when it sees only the SPDZ2k aggregate, compared with plaintext FedAvg, where
it sees every client's update?

## Setting

| Item | Value |
|---|---|
| Threat model | honest-but-curious coordinator; it knows the global model and the training procedure |
| Plaintext FedAvg view | the target client's update `w_i − w` |
| SPDZ2k view | the decoded sum-only aggregate of the K = 4 cohort models: per client `round(n_i · w_i · 10^6)`, integer sum, `/ 10^6 / Σ n_i`. This uses the protocol's own encoder (`mp_spdz._encode_weighted_model`); the SPDZ2k output equals this arithmetic bit for bit (diagnostics/sum_only_divergence) |
| Client step | one local SGD step (lr 0.05, momentum 0.9) on B ∈ {1, 2, 4, 8} images. This is FedSGD, the setting most favourable to the attacker; the E1 runs use one epoch of about 157 steps |
| Data | Fashion-MNIST, 12 IID partitions (seed 101); 11 provide cohorts, the 12th trains the "trained" models |
| Model states | `initial` (random, test accuracy 0.10) and `trained` (one epoch on the reserved partition; CNN 0.690, MLP 0.699) |
| Trials | 8 per (model state, B); random cohort and target client per trial; 1,440 image-level records |
| Statistics | trial means with 95 % t-intervals (`leakage_summary.csv`) |

## Attacks

| Attack | Model | What it recovers | Score |
|---|---|---|---|
| `optimisation` | CompactCNN (deployed, 2,202 parameters) | images, by optimising dummy inputs to match the update (Geiping et al. 2020: cosine loss, TV prior, signed Adam, 2,000 iterations, 2 restarts); attacker given the true labels (upper bound) | SSIM / PSNR of the best one-to-one match |
| `fc_features` | CompactCNN | the 128-d input of the output layer: `dW_c / db_c` per class row (exact for one image) | best cosine similarity to the true features |
| `fc_input` | probe MLP 784-100-10 (79,510 parameters; not used in E1–E5) | input images through the first fully connected layer: `dW_j / db_j` per hidden unit (Phong et al. 2017) | SSIM / PSNR of the best one-to-one match |
| labels | CompactCNN | classes whose output bias grew (iDLG) | precision / recall against the target's labels |

The TV weight was calibrated on seed 7, which the evaluation does not use
(`calibration/`, `calibrate.sh`): 0.05 gave the best reconstructions from the
plaintext view (mean SSIM 0.371 untrained, 0.214 trained; the alternatives 0,
0.001 and 0.01 scored 0.31–0.34 and 0.10–0.19).

## Results (`evaluation/`, table in `leakage_table.md`, figure `leakage_quality.png`)

**Analytic input read-out, probe MLP: secure aggregation does not stop it.**
The table gives the share of the target client's images recovered near-exactly
(SSIM ≥ 0.9) and, in brackets, the mean SSIM:

| B | FedAvg, untrained | SPDZ2k, untrained | FedAvg, trained | SPDZ2k, trained |
|---:|---|---|---|---|
| 1 | 1.00 (1.000) | 1.00 (1.000) | 1.00 (1.000) | 0.75 (0.865) |
| 2 | 1.00 (1.000) | 0.75 (0.920) | 0.88 (0.937) | 0.63 (0.765) |
| 4 | 1.00 (1.000) | 0.31 (0.789) | 0.81 (0.892) | 0.41 (0.662) |
| 8 | 0.80 (0.953) | 0.03 (0.586) | 0.66 (0.780) | 0.28 (0.568) |

A ReLU unit that only one image in the whole cohort activates carries that image
alone, so its row of the aggregate is still an exact copy. Aggregating four
clients removes this only when the cohort holds many images.
`leakage_examples_initial_b4.png` shows all four images of a target client
recovered from an aggregate of 16.

**Feature read-out, CompactCNN.** From an individual update, the 128-d
penultimate features of a single image are recovered exactly (cosine 1.000).
From the aggregate, the best candidate still reaches a cosine of 0.96–0.97 at
B = 1 and 0.73–0.89 at B = 8. A cosine of at least 0.99 occurs in 50 % of
trained-model trials at B = 1 under SPDZ2k, against 100 % under FedAvg, and in
none at B ≥ 2 for the untrained model.

**Optimisation inversion, CompactCNN: weak in both views.**
* Mean SSIM is 0.25–0.33 from the individual update at B = 1, against 0.18 from
  the aggregate.
* Both views converge to about 0.10–0.16 at B = 8.
* No reconstruction in either view reached SSIM 0.5; the maximum was 0.44.

The 2,202-parameter network's update does not determine a 784-pixel image well
enough for this attack.

**Labels.** From an individual update the output-bias read-out has precision
1.00 in every cell, and recall 1.00 for the untrained model (0.69–1.00 trained).
From the aggregate, precision falls to 0.29–0.71: the read-out names the
cohort's classes without attributing them to a client.

## What this establishes

1. Against a coordinator that sees individual updates, single-image updates
   leak the label, the penultimate features exactly and, for a fully connected
   first layer, the image exactly.
2. SPDZ2k sum-only aggregation over 4 clients **reduces but does not remove**
   this leakage. It removes the attribution to a client, and recovery degrades
   with the number of images in the cohort. For small cohorts and batches,
   however, the aggregate still yields exact copies of individual images through
   a fully connected layer.
3. For the deployed CompactCNN, optimisation-based inversion recovers no
   recognisable image from either view in this setting. This is a property of
   the small model and is no evidence of protection.

## Limits

* One local step (FedSGD). Multi-step updates such as the 157-step epoch in
  E1–E5 are harder to invert; that setting was not measured.
* The analytic image attack applies to a fully connected first layer. The
  deployed CNN begins with convolutions, so for it only the feature and label
  read-outs were measured.
* The coordinator is passive. A malicious coordinator that manipulates the global
  model can isolate single clients even under secure aggregation (Fowl et al.
  2022, Pasquini et al. 2022); this was not evaluated.
* The aggregate was computed with the protocol's exact arithmetic, not by
  running SPDZ2k for every trial. Bit-exactness of that arithmetic is verified
  separately (324/324 sum-only rounds).
* Run provenance: the trials ran at commit `14b7bb5` from an uncommitted tree.
  `run_metadata.json` in each shard records the SHA-256 of every source file
  that defines the study. After the trials, only the merge step of
  `run_leakage_study.py` was corrected (it matched the shard log files); the
  trial code is unchanged.

## Reproduce

```bash
research_output/completion/experiments/leakage/calibrate.sh    # about 10 min
research_output/completion/experiments/leakage/evaluate.sh     # about 30 min on 3 vCPU
```

| Attack | Model | B | View | Metric | Mean | 95 % CI |
|---|---|---:|---|---|---:|---|
| optimisation | initial | 1 | individual | ssim | 0.331 | 0.243–0.420 |
| optimisation | initial | 1 | secure_aggregate | ssim | 0.181 | 0.141–0.221 |
| optimisation | initial | 2 | individual | ssim | 0.226 | 0.159–0.294 |
| optimisation | initial | 2 | secure_aggregate | ssim | 0.164 | 0.130–0.198 |
| optimisation | initial | 4 | individual | ssim | 0.156 | 0.118–0.194 |
| optimisation | initial | 4 | secure_aggregate | ssim | 0.148 | 0.129–0.167 |
| optimisation | initial | 8 | individual | ssim | 0.162 | 0.139–0.185 |
| optimisation | initial | 8 | secure_aggregate | ssim | 0.157 | 0.130–0.184 |
| optimisation | trained | 1 | individual | ssim | 0.248 | 0.175–0.321 |
| optimisation | trained | 1 | secure_aggregate | ssim | 0.176 | 0.122–0.230 |
| optimisation | trained | 2 | individual | ssim | 0.235 | 0.162–0.307 |
| optimisation | trained | 2 | secure_aggregate | ssim | 0.160 | 0.102–0.217 |
| optimisation | trained | 4 | individual | ssim | 0.163 | 0.119–0.207 |
| optimisation | trained | 4 | secure_aggregate | ssim | 0.142 | 0.095–0.189 |
| optimisation | trained | 8 | individual | ssim | 0.103 | 0.077–0.128 |
| optimisation | trained | 8 | secure_aggregate | ssim | 0.141 | 0.134–0.148 |
| fc_features | initial | 1 | individual | feature_cosine | 1.000 | 1.000–1.000 |
| fc_features | initial | 1 | secure_aggregate | feature_cosine | 0.960 | 0.938–0.981 |
| fc_features | initial | 2 | individual | feature_cosine | 0.989 | 0.975–1.002 |
| fc_features | initial | 2 | secure_aggregate | feature_cosine | 0.930 | 0.914–0.947 |
| fc_features | initial | 4 | individual | feature_cosine | 0.968 | 0.956–0.980 |
| fc_features | initial | 4 | secure_aggregate | feature_cosine | 0.910 | 0.891–0.930 |
| fc_features | initial | 8 | individual | feature_cosine | 0.933 | 0.924–0.941 |
| fc_features | initial | 8 | secure_aggregate | feature_cosine | 0.891 | 0.867–0.915 |
| fc_features | trained | 1 | individual | feature_cosine | 1.000 | 1.000–1.000 |
| fc_features | trained | 1 | secure_aggregate | feature_cosine | 0.970 | 0.937–1.004 |
| fc_features | trained | 2 | individual | feature_cosine | 0.997 | 0.993–1.001 |
| fc_features | trained | 2 | secure_aggregate | feature_cosine | 0.943 | 0.907–0.978 |
| fc_features | trained | 4 | individual | feature_cosine | 0.936 | 0.900–0.971 |
| fc_features | trained | 4 | secure_aggregate | feature_cosine | 0.794 | 0.731–0.856 |
| fc_features | trained | 8 | individual | feature_cosine | 0.855 | 0.794–0.916 |
| fc_features | trained | 8 | secure_aggregate | feature_cosine | 0.734 | 0.659–0.809 |
| fc_input | initial | 1 | individual | ssim | 1.000 | 1.000–1.000 |
| fc_input | initial | 1 | secure_aggregate | ssim | 1.000 | 1.000–1.000 |
| fc_input | initial | 2 | individual | ssim | 1.000 | 1.000–1.000 |
| fc_input | initial | 2 | secure_aggregate | ssim | 0.920 | 0.864–0.976 |
| fc_input | initial | 4 | individual | ssim | 1.000 | 1.000–1.000 |
| fc_input | initial | 4 | secure_aggregate | ssim | 0.789 | 0.729–0.848 |
| fc_input | initial | 8 | individual | ssim | 0.953 | 0.924–0.983 |
| fc_input | initial | 8 | secure_aggregate | ssim | 0.586 | 0.504–0.669 |
| fc_input | trained | 1 | individual | ssim | 1.000 | 1.000–1.000 |
| fc_input | trained | 1 | secure_aggregate | ssim | 0.865 | 0.671–1.060 |
| fc_input | trained | 2 | individual | ssim | 0.937 | 0.804–1.069 |
| fc_input | trained | 2 | secure_aggregate | ssim | 0.765 | 0.587–0.942 |
| fc_input | trained | 4 | individual | ssim | 0.892 | 0.795–0.989 |
| fc_input | trained | 4 | secure_aggregate | ssim | 0.662 | 0.543–0.781 |
| fc_input | trained | 8 | individual | ssim | 0.780 | 0.721–0.839 |
| fc_input | trained | 8 | secure_aggregate | ssim | 0.568 | 0.483–0.654 |

Label read-out from the output-bias update (target client's labels):

| Model | B | View | Precision | Recall |
|---|---:|---|---:|---:|
| initial | 1 | individual | 1.00 | 1.00 |
| initial | 1 | secure_aggregate | 0.34 | 1.00 |
| initial | 2 | individual | 1.00 | 1.00 |
| initial | 2 | secure_aggregate | 0.29 | 1.00 |
| initial | 4 | individual | 1.00 | 1.00 |
| initial | 4 | secure_aggregate | 0.56 | 0.75 |
| initial | 8 | individual | 1.00 | 1.00 |
| initial | 8 | secure_aggregate | 0.71 | 0.49 |
| trained | 1 | individual | 1.00 | 1.00 |
| trained | 1 | secure_aggregate | 0.39 | 1.00 |
| trained | 2 | individual | 1.00 | 0.94 |
| trained | 2 | secure_aggregate | 0.32 | 0.75 |
| trained | 4 | individual | 1.00 | 0.89 |
| trained | 4 | secure_aggregate | 0.55 | 0.73 |
| trained | 8 | individual | 1.00 | 0.69 |
| trained | 8 | secure_aggregate | 0.63 | 0.45 |

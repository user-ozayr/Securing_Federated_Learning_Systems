import csv, json
from pathlib import Path
import numpy as np
import torch
from fl_security.attacks.byzantine import ByzantineAttacker
from fl_security.attacks.label_flip import apply_label_flip
from fl_security.federated.robust_aggregation import robust_filter_and_aggregate

OUT = Path('research_output/final_validation_20261119T194946Z')
rows = []
base = {'weight': torch.zeros(2)}
benign = {'weight': torch.tensor([1.0, 0.5])}
for attack_type in ('sign_flip', 'random_noise'):
    cfg = {'experiment': {'seed': 42}, 'attacks': {'enabled': True, 'attack_type': attack_type, 'compromised_fraction': 0.4, 'strength': 1.0}}
    attacker = ByzantineAttacker(cfg, 5)
    malicious = sorted(attacker.malicious_clients)
    rounds = []
    for rnd in (1, 2):
        states = [attacker.perturb_update(cid, rnd, base, benign) for cid in range(5)]
        agg = torch.stack([s['weight'] for s in states]).mean(0)
        clean = benign['weight']
        rounds.append({'round': rnd, 'aggregate': agg.tolist(), 'clean_reference': clean.tolist(), 'aggregate_deviation_l2': float(torch.linalg.vector_norm(agg-clean)), 'malicious_ids': malicious})
    rows.append({'case': attack_type, 'malicious_clients': json.dumps(malicious), 'rounds': json.dumps(rounds), 'observed': 'synthetic weighted-average parameter vector; no training/accuracy metric'})

labels = np.array([0,1,2,9])
flipped = apply_label_flip(labels, num_classes=10)
rows.append({'case':'label_flip_transform','malicious_clients':'n/a','rounds':json.dumps({'input':labels.tolist(),'output':flipped.tolist()}),'observed':'transform-only; no model training'})

updates = [torch.tensor([v, 2*v]) for v in (1.0,1.1,0.9,-1.0,-1.1)]
states = [{'weight':v} for v in updates]
plain, report = robust_filter_and_aggregate(states,[1]*5,base,client_ids=list(range(5)),max_malicious=2,residual_z_threshold=3.5,min_cosine_similarity=0.0)
rows.append({'case':'standalone_robust_filter_sign_flip','malicious_clients':'[3,4]','rounds':json.dumps({'detected':report['detected_client_ids'],'accepted':report['accepted_client_ids'],'aggregate':plain['weight'].tolist(),'fallback':report['fallback_used']}),'observed':'synthetic detector check only; ordinary plaintext path, not MPC'})
with (OUT/'ATTACK_MICROBENCHMARK.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['case','malicious_clients','rounds','observed']);w.writeheader();w.writerows(rows)
(OUT/'ATTACK_MICROBENCHMARK.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))

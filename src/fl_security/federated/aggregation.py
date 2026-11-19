"""Plaintext weighted FedAvg for experiments that explicitly disable SMPC."""
from __future__ import annotations
from typing import Mapping, Sequence
import torch

def weighted_fedavg(client_states: Sequence[Mapping[str, torch.Tensor]], num_examples: Sequence[int],
                    global_state: Mapping[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    """Sample-count weighted FedAvg; integer buffers remain from global model."""
    if not client_states or len(client_states) != len(num_examples):
        raise ValueError("client_states and num_examples must be non-empty and aligned")
    if any(isinstance(n, bool) or not isinstance(n, int) or n <= 0 for n in num_examples):
        raise ValueError("each client example count must be a positive integer")
    keys, total_examples = list(global_state), sum(num_examples)
    expected = set(keys)
    if any(set(state) != expected for state in client_states):
        raise ValueError("all client states must match global_state keys")
    aggregated = {}
    for key in keys:
        base = global_state[key]
        if not torch.is_floating_point(base):
            aggregated[key] = base.detach().clone()
            continue
        weighted = [state[key].detach().cpu().to(torch.float64) * n
                    for state, n in zip(client_states, num_examples)]
        summed = torch.zeros_like(weighted[0], dtype=torch.float64)
        for item in weighted:
            summed += item
        average = summed / total_examples
        aggregated[key] = average.to(device=base.device, dtype=base.dtype)
    return aggregated

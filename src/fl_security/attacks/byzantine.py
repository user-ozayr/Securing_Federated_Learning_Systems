"""Configurable malicious-client behaviour for controlled FL experiments.

Attack types (``attacks.attack_type``):

* ``sign_flip``  – submit ``-strength * delta`` (update manipulation);
* ``label_flip`` – train on labels mapped ``y -> (y + 1) mod C`` (data poisoning);
* ``random_noise`` – add N(0, strength^2) to every parameter (corrupted update);
* ``scaled_replacement`` – train on flipped labels and multiply the update by
  ``boost`` (model replacement, Bagdasaryan et al. 2020);
* ``backdoor`` – BadNets trigger poisoning of ``poison_fraction`` of each batch,
  update multiplied by ``boost`` (``boost`` = 1 is a naive backdoor);
* ``adaptive_backdoor`` – backdoor poisoning, then the update is rescaled to
  ``adaptive_norm_fraction`` times the defence threshold the attacker expects
  (constrain-and-scale against norm bounds);
* ``evasive_backdoor`` – as ``adaptive_backdoor``, and in addition the attacker
  also trains a clean update and copies it into the coordinates it believes the
  direction screen checks, so that its signs look honest there. If the checked
  subset is public it uses that subset; otherwise it guesses a random subset of
  ``evasion_guess_fraction`` of the coordinates each round.

Malicious-client placement (``attacks.placement``):

* ``random`` (default, unchanged) – a seeded random subset;
* ``stratified`` – the static cohort (first K clients) receives the population's
  expected number of malicious clients, removing the "cohort lottery" when
  static and dynamic participation are compared;
* ``predictive`` – a fixed subset supplied by an adversary model (see
  fl_security.mtd.exposure), e.g. clients predicted to participate most;
* per-round sets can be installed with :meth:`set_round_assignment`.
"""
import math
import numpy as np
import torch
from fl_security.attacks.label_flip import apply_label_flip
from fl_security.attacks.sign_flip import apply_sign_flip

SUPPORTED_ATTACKS = {
    "sign_flip", "label_flip", "random_noise",
    "scaled_replacement", "backdoor", "adaptive_backdoor", "evasive_backdoor",
}
BACKDOOR_ATTACKS = {"backdoor", "adaptive_backdoor", "evasive_backdoor"}
SUPPORTED_PLACEMENTS = {"random", "stratified", "predictive"}


class ByzantineAttacker:
    def __init__(self, config: dict, num_clients: int):
        attacks = config.get("attacks", {})
        self.enabled = bool(attacks.get("enabled", False))
        self.attack_type = attacks.get("attack_type", "sign_flip")
        self.compromised_fraction = float(attacks.get("compromised_fraction", 0.0))
        if not 0.0 <= self.compromised_fraction <= 1.0:
            raise ValueError("compromised_fraction must be in [0, 1]")
        configured_rounds = attacks.get("activation_rounds")
        self.activation_rounds = None if configured_rounds is None else set(int(x) for x in configured_rounds)
        self.strength = float(attacks.get("strength", 1.0))
        self.boost = float(attacks.get("boost", 1.0))
        self.adaptive_norm_fraction = float(attacks.get("adaptive_norm_fraction", 0.95))
        self.evasion_guess_fraction = float(attacks.get("evasion_guess_fraction", 0.25))
        if not 0 < self.evasion_guess_fraction <= 1:
            raise ValueError("attacks.evasion_guess_fraction must be in (0, 1]")
        self.seed = int(config.get("experiment", {}).get("seed", 42))
        if self.attack_type not in SUPPORTED_ATTACKS:
            raise ValueError(f"unsupported attack_type: {self.attack_type}")
        if not math.isfinite(self.boost) or self.boost <= 0:
            raise ValueError("attacks.boost must be finite and positive")
        if not 0 < self.adaptive_norm_fraction <= 4:
            raise ValueError("attacks.adaptive_norm_fraction must be in (0, 4]")
        backdoor = dict(attacks.get("backdoor", {}) or {})
        self.poison_fraction = float(backdoor.get("poison_fraction", 0.5))
        if not 0.0 <= self.poison_fraction <= 1.0:
            raise ValueError("attacks.backdoor.poison_fraction must be in [0, 1]")
        self.trigger = None
        if self.attack_type in BACKDOOR_ATTACKS:
            from fl_security.attacks.backdoor import BackdoorTrigger

            dataset = config.get("federated_learning", {}).get("dataset", "cifar10")
            self.trigger = BackdoorTrigger(
                dataset=dataset,
                target_label=int(backdoor.get("target_label", 0)),
                size=int(backdoor.get("trigger_size", 4)),
            )

        self.placement = attacks.get("placement", "random")
        if self.placement not in SUPPORTED_PLACEMENTS:
            raise ValueError(f"unsupported attacks.placement: {self.placement}")
        count = int(math.ceil(num_clients * self.compromised_fraction))
        configured_count = attacks.get("num_malicious")
        if configured_count is not None:
            count = int(configured_count)
            if not 0 <= count <= num_clients:
                raise ValueError("attacks.num_malicious must be in [0, num_clients]")
        self.malicious_count = count
        rng = np.random.default_rng(self.seed + 20_000)
        if self.placement == "stratified" and count:
            fraction = float(config.get("federated_learning", {}).get("fraction_train", 1.0))
            cohort = min(num_clients, max(1, int(num_clients * fraction)))
            inside = min(cohort, count, int(round(count * cohort / num_clients)))
            outside = count - inside
            if outside > num_clients - cohort:
                raise ValueError("stratified placement cannot fit the malicious clients")
            chosen = set(int(x) for x in rng.choice(cohort, inside, replace=False))
            if outside:
                chosen |= set(int(cohort + x) for x in rng.choice(num_clients - cohort, outside, replace=False))
            self.malicious_clients = chosen
        else:
            self.malicious_clients = (
                set(int(x) for x in rng.choice(num_clients, count, replace=False))
                if count else set()
            )
        self.round_assignment: dict[int, set[int]] | None = None

    # ---- placement -------------------------------------------------------------
    def set_malicious_clients(self, clients) -> None:
        """Install an adversary-chosen fixed set (``placement: predictive``)."""
        chosen = set(int(c) for c in clients)
        if len(chosen) != self.malicious_count:
            raise ValueError("predictive placement must choose exactly num_malicious clients")
        self.malicious_clients = chosen

    def set_round_assignment(self, assignment: dict[int, set[int]]) -> None:
        """Just-in-time compromise: a separate malicious set for every round."""
        self.round_assignment = {int(r): set(int(c) for c in v) for r, v in assignment.items()}

    def is_malicious(self, client_id: int, round_num: int) -> bool:
        active = self.activation_rounds is None or round_num in self.activation_rounds
        if self.round_assignment is not None:
            current = self.round_assignment.get(int(round_num), set())
            return self.enabled and active and client_id in current
        return self.enabled and active and client_id in self.malicious_clients

    # ---- data poisoning -----------------------------------------------------------
    def data_poisoning(self, client_id: int, round_num: int) -> str | None:
        if not self.is_malicious(client_id, round_num):
            return None
        if self.attack_type in {"label_flip", "scaled_replacement"}:
            return "label_flip"
        if self.attack_type in BACKDOOR_ATTACKS:
            return "backdoor"
        return None

    def needs_clean_update(self, client_id: int, round_num: int) -> bool:
        return self.attack_type == "evasive_backdoor" and self.is_malicious(client_id, round_num)

    def poison_batch(self, client_id: int, round_num: int, images, labels, generator=None):
        if self.data_poisoning(client_id, round_num) != "backdoor":
            return images, labels
        return self.trigger.poison_batch(images, labels, self.poison_fraction, generator)

    # ---- update manipulation ------------------------------------------------------
    def perturb_update(self, client_id: int, round_num: int, global_state_dict: dict,
                       local_state_dict: dict, threshold_estimate: float | None = None,
                       clean_state_dict: dict | None = None,
                       known_indices: list[int] | None = None) -> dict:
        if not self.is_malicious(client_id, round_num):
            return local_state_dict
        if self.attack_type == "evasive_backdoor":
            if clean_state_dict is None:
                raise ValueError("evasive_backdoor needs the attacker's clean update")
            norm = _update_norm(global_state_dict, local_state_dict)
            factor = (self.boost if threshold_estimate is None or norm <= 0
                      else self.adaptive_norm_fraction * float(threshold_estimate) / norm)
            scaled = _scale_update(global_state_dict, local_state_dict, factor)
            clean = _scale_update(global_state_dict, clean_state_dict, factor)
            if known_indices is None:
                dimension = sum(v.numel() for v in global_state_dict.values()
                                if torch.is_floating_point(v))
                rng = np.random.default_rng(self.seed * 1_000_003 + round_num * 1_009 + client_id)
                size = max(1, int(round(self.evasion_guess_fraction * dimension)))
                known_indices = rng.choice(dimension, size, replace=False).tolist()
            return _copy_coordinates(global_state_dict, scaled, clean, known_indices)
        if self.attack_type == "sign_flip":
            return apply_sign_flip(global_state_dict, local_state_dict, strength=self.strength)
        if self.attack_type == "random_noise":
            result = {}
            for key, value in local_state_dict.items():
                if torch.is_floating_point(value):
                    generator = torch.Generator(device=value.device)
                    generator.manual_seed(self.seed + round_num * 10_000 + client_id)
                    noise = torch.randn(value.shape, dtype=value.dtype, device=value.device, generator=generator)
                    result[key] = value + noise * self.strength
                else:
                    result[key] = value
            return result
        if self.attack_type in {"scaled_replacement", "backdoor"}:
            return _scale_update(global_state_dict, local_state_dict, self.boost)
        if self.attack_type == "adaptive_backdoor":
            norm = _update_norm(global_state_dict, local_state_dict)
            if threshold_estimate is None or norm <= 0:
                factor = self.boost
            else:
                factor = self.adaptive_norm_fraction * float(threshold_estimate) / norm
            return _scale_update(global_state_dict, local_state_dict, factor)
        return local_state_dict

    def perturb_labels(self, client_id: int, round_num: int, labels, num_classes: int = 10) -> np.ndarray:
        values = labels.detach().cpu().numpy() if torch.is_tensor(labels) else labels
        if self.data_poisoning(client_id, round_num) != "label_flip":
            return np.asarray(values)
        return apply_label_flip(values, num_classes=num_classes)


def _update_norm(global_state: dict, local_state: dict) -> float:
    total = 0.0
    for key, base in global_state.items():
        if torch.is_floating_point(base):
            delta = local_state[key].detach().to(torch.float64) - base.detach().to(torch.float64)
            total += float((delta * delta).sum().item())
    return math.sqrt(total)


def _copy_coordinates(global_state: dict, target: dict, source: dict, indices) -> dict:
    """``target`` with the flat coordinates ``indices`` taken from ``source``.

    Flat order is the order of the floating-point tensors in ``global_state``,
    the same order the defence uses (smpc.robust.flatten_delta).
    """
    chosen = set(int(i) for i in indices)
    result, offset = {}, 0
    for key, base in global_state.items():
        if not torch.is_floating_point(base):
            result[key] = target[key]
            continue
        count = base.numel()
        local = [i - offset for i in chosen if offset <= i < offset + count]
        value = target[key].detach().clone()
        if local:
            flat = value.reshape(-1)
            index = torch.tensor(local, dtype=torch.long)
            flat[index] = source[key].detach().reshape(-1)[index].to(flat.dtype)
        result[key] = value
        offset += count
    return result


def _scale_update(global_state: dict, local_state: dict, factor: float) -> dict:
    result = {}
    for key, base in global_state.items():
        local = local_state[key]
        if torch.is_floating_point(base):
            delta = local.detach().to(torch.float64) - base.detach().to(torch.float64)
            result[key] = (base.detach().to(torch.float64) + factor * delta).to(dtype=local.dtype)
        else:
            result[key] = local
    return result

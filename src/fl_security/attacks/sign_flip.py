"""Apply sign-flip attacks to model states or local updates."""
import torch


def apply_sign_flip(arg1, arg2=None, strength=1.0):
    """Flip a state dict directly or negate a local delta from a global state.

    A single state dict uses the legacy elementwise form. Two state dicts use
    the delta-based form used by the federated-learning attack pipeline. A
    scalar second positional argument remains supported as legacy strength.
    """
    if isinstance(arg2, dict):
        global_state_dict, local_state_dict = arg1, arg2
        flipped = {}
        for key, global_value in global_state_dict.items():
            local_value = local_state_dict[key]
            if torch.is_floating_point(global_value) or global_value.is_complex():
                local_delta = local_value - global_value
                flipped[key] = global_value + (-1.0 * strength * local_delta)
            else:
                flipped[key] = local_value
        return flipped

    state_dict = arg1
    effective_strength = strength if arg2 is None else arg2
    flipped = {}
    for key, value in state_dict.items():
        if torch.is_floating_point(value) or value.is_complex():
            flipped[key] = -1.0 * effective_strength * value
        else:
            flipped[key] = value
    return flipped

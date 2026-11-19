"""Fixed-point conversion for integer inputs and outputs in SPDZ2k."""
from __future__ import annotations
import torch

class FixedPointEncoder:
    def __init__(self, scale: int = 1_000_000):
        if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
            raise ValueError("scale must be a positive integer")
        self.scale = scale

    def encode(self, tensor: torch.Tensor) -> torch.Tensor:
        if not torch.is_tensor(tensor) or not torch.is_floating_point(tensor):
            raise TypeError("encode expects a floating-point torch.Tensor")
        value = tensor.detach().to(dtype=torch.float64, device="cpu")
        if not torch.isfinite(value).all():
            raise ValueError("tensor contains NaN or infinite values")
        scaled = torch.round(value * self.scale)
        if torch.any(torch.abs(scaled) >= float(1 << 63)):
            raise OverflowError("fixed-point value exceeds int64 range")
        return scaled.to(dtype=torch.int64)

    def decode(self, encoded_tensor: torch.Tensor) -> torch.Tensor:
        if not torch.is_tensor(encoded_tensor) or encoded_tensor.dtype != torch.int64:
            raise TypeError("decode expects an int64 torch.Tensor")
        return encoded_tensor.to(dtype=torch.float32) / self.scale

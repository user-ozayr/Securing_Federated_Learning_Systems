"""Round-scoped client selection with secret-keyed randomness."""
import hashlib
import hmac
import os

from fl_security.mtd.client_selection import select_clients
from fl_security.mtd.randomness import HMACCounterRNG


SCHEDULES = ("static", "deterministic", "secret")


class MTDController:
    """Round-scoped participation scheduling.

    ``mtd.schedule`` (optional) makes the participation regime explicit:

    * ``static`` – the same cohort (first K clients) every round;
    * ``deterministic`` – a fresh cohort every round derived from the public
      experiment seed only (reproducible, therefore predictable);
    * ``secret`` – a fresh cohort every round derived with HMAC-SHA256 from
      ``FL_MTD_SECRET`` (required, at least 32 bytes) and the seed.

    Without ``schedule`` the historical behaviour is kept: ``enabled`` selects a
    dynamic schedule, which is secret-derived whenever FL_MTD_SECRET is set.
    """

    def __init__(self, config: dict):
        self.config = config.get("mtd", {})
        self.enabled = bool(self.config.get("enabled", False))
        self.schedule = self.config.get("schedule")
        if self.schedule is not None:
            if self.schedule not in SCHEDULES:
                raise ValueError(f"mtd.schedule must be one of {SCHEDULES}")
            self.enabled = self.schedule != "static"
        self.selection_strategy = self.config.get("selection_strategy", "random")
        configured_seed = int(config.get("experiment", {}).get("seed", 42))

        # The live schedule uses an HMAC-derived PRF key. Without this secret,
        # schedules are reproducible simulation artifacts and are not secret.
        secret = os.environ.get("FL_MTD_SECRET", "")
        if self.schedule == "deterministic":
            secret = ""
        if self.schedule == "secret" and not secret:
            raise ValueError("mtd.schedule 'secret' requires FL_MTD_SECRET to be set")
        material = f"fl-security-mtd-seed-v1:{configured_seed}".encode("utf-8")
        if secret:
            secret_bytes = secret.encode("utf-8")
            if len(secret_bytes) < 32:
                raise ValueError("FL_MTD_SECRET must contain at least 32 bytes")
            self.seed = int.from_bytes(
                hmac.new(secret_bytes, material, hashlib.sha256).digest()[:8],
                byteorder="big",
                signed=False,
            )
            self._random_key = hmac.new(
                secret_bytes, b"fl-security-mtd-rng-v1:" + material, hashlib.sha256
            ).digest()
            self.secret_seeded = True
        else:
            self.seed = configured_seed
            self._random_key = hashlib.sha256(
                b"fl-security-mtd-simulation-v1:" + material
            ).digest()
            self.secret_seeded = False

        smpc = config.get("smpc", {})
        self.smpc_enabled = bool(smpc.get("enabled", False))
        self.min_clients_per_round = int(smpc.get("min_clients_per_round", 2))
        self.num_aggregation_parties = int(
            smpc.get("num_aggregation_parties", 0)
        )
        if self.smpc_enabled and self.num_aggregation_parties < 2:
            raise ValueError("SPDZ2k aggregation party count must be >= 2")
        if self.min_clients_per_round < 2:
            raise ValueError("smpc.min_clients_per_round must be >= 2")

    def generate_round_config(self, round_num: int, num_clients: int, fraction: float) -> dict:
        if isinstance(round_num, bool) or not isinstance(round_num, int) or round_num <= 0:
            raise ValueError("round_num must be positive")
        moving = self.enabled and self.config.get("change_every_round", True)
        round_seed = self.seed + round_num if moving else self.seed
        schedule_scope = f"round:{round_num}" if moving else "static-round-schedule"
        round_material = f"{schedule_scope}:seed:{round_seed}".encode("ascii")
        round_key = hmac.new(self._random_key, round_material, hashlib.sha256).digest()
        rng = HMACCounterRNG(round_key)

        strategy = self.selection_strategy if self.enabled else "fixed"
        selected = select_clients(
            num_clients, fraction, strategy=strategy, seed=round_seed, rng=rng
        )

        if self.smpc_enabled and len(selected) < self.min_clients_per_round:
            raise ValueError(
                f"SPDZ2k requires at least {self.min_clients_per_round} selected clients per round"
            )

        return {
            "round": round_num,
            "selected_clients": selected,
            "seed": round_seed,
            "secret_seeded": self.secret_seeded,
            "num_aggregation_parties": self.num_aggregation_parties,
        }

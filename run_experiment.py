"""Launch the configured Flower-based FL security experiment."""
import argparse

from fl_security.config import load_config
from fl_security.federated.flower_simulation import run_flower_simulation
from fl_security.smpc.local_demo import run_with_local_mp_spdz


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FL Security with Flower")
    parser.add_argument("--config", required=True, help="Path to YAML configuration")
    parser.add_argument(
        "--local-mp-spdz",
        action="store_true",
        help="Start local MP-SPDZ SPDZ2k party services for an SMPC experiment",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    framework = config.get("federated_learning", {}).get("framework", "flower")
    if framework != "flower":
        raise ValueError(f"Unsupported framework: {framework!r}; Flower is required")
    print(f"Starting Flower experiment: {config['experiment']['name']}")

    if args.local_mp_spdz:
        run_with_local_mp_spdz(config)
    else:
        run_flower_simulation(config)


if __name__ == "__main__":
    main()

"""Run the Proxmox defense eval for both HONEST and ATTACK modes.

Requires environment variables (put them in the sops-encrypted secrets.env, loaded
by direnv):
  - OPENROUTER_API_KEY                          (models)
  - PROXMOX_HOST / PROXMOX_PORT / PROXMOX_USER / PROXMOX_REALM / PROXMOX_PASSWORD /
    PROXMOX_NODE / PROXMOX_VERIFY_TLS / PROXMOX_IMAGE_STORAGE   (sandbox)

Usage:
    uv run python run_eval.py                 # 1 epoch per mode
    uv run python run_eval.py --epochs 50     # 50 epochs per mode (score distribution)
"""

import argparse

from control_arena import EvalMode
from control_arena.eval import ControlEvalConfig, get_control_task_product
from control_arena.micro_protocol import trusted_monitoring_builder
from control_arena.scorers import max_suspicion_scorer
from inspect_ai import eval
from inspect_ai.model import GenerateConfig

from ooc_arena.monitor import full_transcript_monitor
from ooc_arena.setting import ProxmoxDefenseSetting

# Confirm the exact slug on https://openrouter.ai/models if this 404s.
MODEL = "openrouter/deepseek/deepseek-v4.1-flash"

# Bound each model call so a stalled OpenRouter/DeepSeek request can't wedge a
# sample: 120s per request, at most 2 retries (short backoff instead of a long
# indefinite one).
MODEL_CONFIG = GenerateConfig(timeout=120, max_retries=2)


def main(epochs: int = 1) -> None:
    setting = ProxmoxDefenseSetting()
    protocol = trusted_monitoring_builder(monitor=full_transcript_monitor())
    config = ControlEvalConfig(
        untrusted_model=MODEL,  # agent under test (offense)
        trusted_model=MODEL,  # defensive monitor (defense) — same model for now
        untrusted_config=MODEL_CONFIG,
        trusted_config=MODEL_CONFIG,
        # Budget covers BOTH agents per sample: the benign workload agent AND the
        # blue investigator that runs afterward (post_submission).
        message_limit=50,
        time_limit=600,  # hard cap per sample (seconds); kills runaway/hung runs
        epochs=epochs,  # re-run each sample N times for a score distribution
        max_sandboxes=1,  # single Proxmox instance (raise only with a multi-instance pool)
    )
    # HONEST mode = the blue-team benchmark: one sample per host case (benign,
    # standalone_c2). The workload is benign; malice (if any) is a planted process
    # the transcript monitor cannot see but the blue investigator can.
    tasks = get_control_task_product(
        setting,
        protocol,
        [EvalMode.HONEST],
        eval_config=config,
        monitoring_scorers=[max_suspicion_scorer()],
    )
    # sandbox_cleanup=True tears down each sample's VM + SDN before the next starts
    # (required with per-sample subnets so live SDNs never overlap). No `limit` so
    # every host-case sample runs.
    eval(tasks=tasks, sandbox_cleanup=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Proxmox defense eval.")
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Times to re-run each sample per mode (default: 1). "
        "With max_sandboxes=1 epochs run sequentially, ~2 min each.",
    )
    args = parser.parse_args()
    main(epochs=args.epochs)

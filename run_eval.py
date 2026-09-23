"""Run the Proxmox defense eval for both HONEST and ATTACK modes.

Requires environment variables (put them in the sops-encrypted secrets.env, loaded
by direnv):
  - OPENROUTER_API_KEY                          (models)
  - PROXMOX_HOST / PROXMOX_PORT / PROXMOX_USER / PROXMOX_REALM / PROXMOX_PASSWORD /
    PROXMOX_NODE / PROXMOX_VERIFY_TLS / PROXMOX_IMAGE_STORAGE   (sandbox)

Usage:
    uv run python run_eval.py                                      # honest, 1 epoch, all samples
    uv run python run_eval.py --epochs 50                          # 50 epochs (score distribution)
    uv run python run_eval.py --modes honest attack --epochs 10 --limit 1
                                                                    # smoke test: 10 honest +
                                                                    # 10 attack epochs, first
                                                                    # sample of each mode only
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

# HONEST = the blue-team benchmark: one sample per host case (benign, standalone_c2).
# The workload is benign; malice (if any) is a planted process the transcript
# monitor cannot see but the blue investigator can.
# ATTACK = the red-agent credential-harvest sample (single sample), kept for the
# transcript-monitor line of experiments.
MODE_MAP = {"honest": EvalMode.HONEST, "attack": EvalMode.ATTACK}


def main(
    epochs: int = 1, modes: list[str] | None = None, limit: int | None = None
) -> None:
    eval_modes = [MODE_MAP[m] for m in (modes or ["honest"])]

    setting = ProxmoxDefenseSetting()
    protocol = trusted_monitoring_builder(monitor=full_transcript_monitor())
    config = ControlEvalConfig(
        untrusted_model=MODEL,  # agent under test (offense)
        trusted_model=MODEL,  # defensive monitor (defense) — same model for now
        untrusted_config=MODEL_CONFIG,
        trusted_config=MODEL_CONFIG,
        # Budget for the workload agent's own phase (main + side task, up to
        # submission). The blue investigator that runs afterward (post_submission)
        # no longer shares this: it opens its own independent message_limit scope
        # (see ooc_arena.blue_agent.DEFAULT_BLUE_MESSAGE_LIMIT) — inspect_ai's
        # message-limit checks are leaf-only, so that scope doesn't loosen this one.
        message_limit=50,
        # token_limit, unlike message_limit, IS a cumulative ceiling across the
        # whole sample regardless of nesting (inspect_ai checks it root-to-leaf) —
        # so it's genuinely shared across the workload agent, the full-transcript
        # monitor, and the blue investigator, and can't be carved up per-phase the
        # way message_limit was. Raised well above the ~1.1M peak seen with the old
        # (starved, ~50-message) blue investigator, since letting it actually run
        # its full ~100-message budget uses more tokens too.
        token_limit=3_000_000,
        time_limit=600,  # hard cap per sample (seconds); kills runaway/hung runs
        epochs=epochs,  # re-run each sample N times for a score distribution
        max_sandboxes=1,  # single Proxmox instance (raise only with a multi-instance pool)
    )
    tasks = get_control_task_product(
        setting,
        protocol,
        eval_modes,
        eval_config=config,
        monitoring_scorers=[max_suspicion_scorer()],
    )
    # sandbox_cleanup=True tears down each sample's VM + SDN before the next starts
    # (required with per-sample subnets so live SDNs never overlap). `limit` caps
    # each task to its first N dataset samples; None (default) runs every sample.
    eval(tasks=tasks, sandbox_cleanup=True, limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Proxmox defense eval.")
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Times to re-run each sample per mode (default: 1). "
        "With max_sandboxes=1 epochs run sequentially, ~2 min each.",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=sorted(MODE_MAP),
        default=["honest"],
        help="Which eval mode(s) to run (default: honest only).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap each mode's dataset to its first N samples "
        "(e.g. --limit 1 to run only the first sample of each mode).",
    )
    args = parser.parse_args()
    main(epochs=args.epochs, modes=args.modes, limit=args.limit)

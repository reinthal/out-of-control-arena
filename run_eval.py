"""Run the Proxmox defense eval for both HONEST and ATTACK modes.

Requires environment variables (put them in the sops-encrypted secrets.env, loaded
by direnv):
  - OPENROUTER_API_KEY                          (models)
  - PROXMOX_HOST / PROXMOX_PORT / PROXMOX_USER / PROXMOX_REALM / PROXMOX_PASSWORD /
    PROXMOX_NODE / PROXMOX_VERIFY_TLS / PROXMOX_IMAGE_STORAGE   (sandbox)

Usage:
    uv run python run_eval.py
"""

from control_arena import EvalMode
from control_arena.eval import ControlEvalConfig, get_control_task_product
from control_arena.micro_protocol import trusted_monitoring_builder
from control_arena.scorers import max_suspicion_scorer
from inspect_ai import eval
from inspect_ai.model import GenerateConfig

from ooc_bench.monitor import full_transcript_monitor
from ooc_bench.setting import ProxmoxDefenseSetting

# Confirm the exact slug on https://openrouter.ai/models if this 404s.
MODEL = "openrouter/deepseek/deepseek-v4.1-flash"

# Bound each model call so a stalled OpenRouter/DeepSeek request can't wedge a
# sample: 120s per request, at most 2 retries (short backoff instead of a long
# indefinite one).
MODEL_CONFIG = GenerateConfig(timeout=120, max_retries=2)

# Number of times to re-run each sample. With max_sandboxes=1 the epochs run
# sequentially (50 epochs x 2 modes = 100 VM provisions), so expect a few hours.
EPOCHS = 50


def main() -> None:
    setting = ProxmoxDefenseSetting()
    protocol = trusted_monitoring_builder(monitor=full_transcript_monitor())
    config = ControlEvalConfig(
        untrusted_model=MODEL,  # agent under test (offense)
        trusted_model=MODEL,  # defensive monitor (defense) — same model for now
        untrusted_config=MODEL_CONFIG,
        trusted_config=MODEL_CONFIG,
        message_limit=20,
        time_limit=300,  # hard cap per sample (seconds); kills runaway/hung runs
        epochs=EPOCHS,  # re-run each sample N times for a score distribution
        max_sandboxes=1,  # single Proxmox instance (raise only with a multi-instance pool)
    )
    tasks = get_control_task_product(
        setting,
        protocol,
        [EvalMode.HONEST, EvalMode.ATTACK],
        eval_config=config,
        monitoring_scorers=[max_suspicion_scorer()],
    )
    # sandbox_cleanup=True tears down each sample's VM + SDN before the next
    # sample starts. This is REQUIRED when running >1 sample with a pinned
    # SANDBOX_CIDR: otherwise sample N's leftover SDN and sample N+1's new SDN
    # both claim the same subnet, PVE rejects the overlapping IP range, and
    # provisioning hangs. To keep a VM alive for debugging, run a single mode
    # (e.g. just EvalMode.ATTACK) with sandbox_cleanup=False.
    eval(tasks=tasks, limit=1, sandbox_cleanup=True)


if __name__ == "__main__":
    main()

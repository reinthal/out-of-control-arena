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

from ooc_bench.monitor import full_transcript_monitor
from ooc_bench.setting import ProxmoxDefenseSetting

# Confirm the exact slug on https://openrouter.ai/models if this 404s.
MODEL = "openrouter/deepseek/deepseek-v4.1-flash"


def main() -> None:
    setting = ProxmoxDefenseSetting()
    protocol = trusted_monitoring_builder(monitor=full_transcript_monitor())
    config = ControlEvalConfig(
        untrusted_model=MODEL,  # agent under test (offense)
        trusted_model=MODEL,  # defensive monitor (defense) — same model for now
        message_limit=30,
        max_sandboxes=1,  # single Proxmox instance
    )
    tasks = get_control_task_product(
        setting,
        protocol,
        [EvalMode.HONEST, EvalMode.ATTACK],
        eval_config=config,
        monitoring_scorers=[max_suspicion_scorer()],
    )
    # sandbox_cleanup=False keeps the VM around for debugging; run
    # `inspect sandbox cleanup proxmox` afterwards to remove inspect-tagged VMs.
    eval(tasks=tasks, limit=1, sandbox_cleanup=False)


if __name__ == "__main__":
    main()

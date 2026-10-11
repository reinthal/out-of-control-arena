"""Run BashArena tasks on the Proxmox backend.

Each sample gets two full Proxmox VMs: the agent works directly on a task VM
(auditd installed), next to a VM holding BashArena's router + fake external
servers. The first run of a task bakes its VM templates; later runs clone them.
See ooc_arena.bash_arena_proxmox. Needs the same environment as run_eval.py
(OPENROUTER_API_KEY and PROXMOX_*).

Experiment: research-log/2026-10-07-basharena-proxmox-gpt41mini-usefulness-baseline.md
Eval logs are written to logs/ next to this script.

Usage (from the repo root; HERE = this script's directory):
    # The pre-registered run: GPT-4.1 mini usefulness with BashArena's own
    # honest policy, 100 actions, 50 random tasks.
    uv run python HERE/run_bash_arena.py --baseline --max-tasks 50 --shuffle-seed 0

    uv run python HERE/run_bash_arena.py                       # honest, first task
    uv run python HERE/run_bash_arena.py --task-ids 6935769    # a specific task
    uv run python HERE/run_bash_arena.py --modes honest attack --max-tasks 2
"""

import argparse
from pathlib import Path

from control_arena import EvalMode
from control_arena.eval import ControlEvalConfig, get_control_task_product
from control_arena.micro_protocol import trusted_monitoring_builder
from control_arena.scorers import max_suspicion_scorer
from control_arena.settings.bash_arena.policies import honest_policy as ba_honest
from control_arena.settings.bash_arena.task.dataset import DatasetSpec
from inspect_ai import eval
from inspect_ai.model import GenerateConfig, get_model

from ooc_arena.bash_arena_proxmox import MAX_SANDBOXES, BashArenaProxmoxSetting
from ooc_arena.monitor import full_transcript_monitor
from ooc_arena.parallel import enable_same_host_parallelism

MODEL = "openrouter/deepseek/deepseek-v4.1-flash"
BASELINE_MODEL = "openrouter/openai/gpt-4.1-mini"
MODEL_CONFIG = GenerateConfig(timeout=120, max_retries=2)
MODE_MAP = {"honest": EvalMode.HONEST, "attack": EvalMode.ATTACK}
LOG_DIR = Path(__file__).parent / "logs"

# The BashArena honest prompt its authors tuned for weaker models (GPT-4.1 mini).
TRUSTED_ELICITATION_PROMPT = (
    Path(ba_honest.__file__).parent / "system_prompts/honest_trusted_elicitation.txt"
).read_text()


def _get_model_lenient_tools(name: str):
    """get_model() for BashArena's policy with non-strict tool schemas.

    Inspect's OpenRouter provider marks every tool `strict`, and OpenAI rejects
    the text editor's schema in strict mode (it has optional parameters).
    """
    return get_model(name, strict_tools=False)


def main(
    modes: list[str],
    max_tasks: int | None,
    task_ids: list[str] | None,
    shuffle_seed: int | None,
    max_sandboxes: int,
    message_limit: int | None,
    baseline: bool,
    model: str | None,
) -> None:
    enable_same_host_parallelism(max_sandboxes)

    setting = BashArenaProxmoxSetting(
        dataset_spec=DatasetSpec(
            max_tasks=max_tasks,
            task_id_whitelist=task_ids,
            shuffle_seed=shuffle_seed,
        )
    )
    if baseline:
        # Reproduce the paper's usefulness measurement: BashArena's own honest
        # policy, a 100-action budget, no monitor in the loop.
        model = model or BASELINE_MODEL
        ba_honest.get_model = _get_model_lenient_tools
        protocol = ba_honest.honest_policy(
            # Explicit: the policy's default model is resolved when it is built,
            # before ControlEvalConfig has set the untrusted model.
            model_name=model,
            system_prompt=TRUSTED_ELICITATION_PROMPT,
            trusted_elicitation=True,
        )
        monitoring_scorers = []
        limits = {"max_steps": 100, "token_limit": 30_000_000, "time_limit": 7200}
    else:
        model = model or MODEL
        protocol = trusted_monitoring_builder(monitor=full_transcript_monitor())
        monitoring_scorers = [max_suspicion_scorer()]
        limits = {
            "message_limit": message_limit,
            "token_limit": 6_000_000,
            "time_limit": 2400,
        }
    config = ControlEvalConfig(
        untrusted_model=model,
        trusted_model=model,
        untrusted_config=MODEL_CONFIG,
        trusted_config=MODEL_CONFIG,
        # time_limit excludes sandbox init (~1 min from templates; minutes more
        # to bake them).
        **limits,
        max_sandboxes=max_sandboxes,
        # A task whose Dockerfile does not build on the VM image fails only its
        # own sample (recorded as an error) instead of aborting the whole run.
        fail_on_error=False,
    )
    tasks = get_control_task_product(
        setting,
        protocol,
        [MODE_MAP[m] for m in modes],
        eval_config=config,
        monitoring_scorers=monitoring_scorers,
    )
    # eval_args() carries time_limit, max_sandboxes and fail_on_error; they are
    # eval()-level settings that get_control_task_product does not apply.
    eval_args = {**config.eval_args(), "log_dir": str(LOG_DIR)}
    eval(tasks=tasks, sandbox_cleanup=True, **eval_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run BashArena on Proxmox.")
    parser.add_argument(
        "--modes", nargs="+", choices=sorted(MODE_MAP), default=["honest"]
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=1,
        help="Number of BashArena main tasks to run per mode (default: 1).",
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        default=None,
        help="Run only these BashArena task ids.",
    )
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        default=None,
        help="Shuffle the task list with this seed before applying --max-tasks "
        "(default: dataset order).",
    )
    parser.add_argument(
        "--max-sandboxes",
        type=int,
        default=MAX_SANDBOXES,
        help="Concurrent samples on the Proxmox host (each 6 GB RAM / 6 vCPU; "
        f"default {MAX_SANDBOXES} fills the host's 40 GB).",
    )
    parser.add_argument(
        "--message-limit",
        type=int,
        default=75,
        help="Message limit per sample (ignored with --baseline).",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Paper usefulness setup: BashArena's honest policy (trusted "
        "elicitation prompt), 100 actions, no monitor, GPT-4.1 mini.",
    )
    parser.add_argument(
        "--model", default=None, help="Override the agent model (Inspect model id)."
    )
    args = parser.parse_args()
    main(
        modes=args.modes,
        max_tasks=args.max_tasks,
        task_ids=args.task_ids,
        shuffle_seed=args.shuffle_seed,
        max_sandboxes=args.max_sandboxes,
        message_limit=args.message_limit,
        baseline=args.baseline,
        model=args.model,
    )

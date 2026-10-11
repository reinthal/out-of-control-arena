"""Honest-mode usefulness of one model on BashArena, Proxmox backend (Ubuntu 22.04).

The paper's usefulness setup: BashArena's own honest policy (ReAct with
bash/python/text-editor/submit, tests hidden from the agent), a 100-action
budget, no monitor. Needs OPENROUTER_API_KEY and PROXMOX_* in the environment.

Experiment: research-log/2026-10-08-basharena-proxmox-ubuntu2204-usefulness.md
Eval logs go to logs/<run name>/ next to this script.

Usage (from the repo root; HERE = this script's directory):
    uv run python HERE/run_usefulness.py --name sonnet45 \
        --model openrouter/anthropic/claude-sonnet-4.5
    uv run python HERE/run_usefulness.py --name gpt41mini \
        --model openrouter/openai/gpt-4.1-mini --trusted-elicitation
"""

import argparse
from pathlib import Path

from control_arena import EvalMode
from control_arena.eval import ControlEvalConfig, get_control_task_product
from control_arena.settings.bash_arena.policies import honest_policy as ba_honest
from control_arena.settings.bash_arena.task.dataset import DatasetSpec
from inspect_ai import eval
from inspect_ai.model import GenerateConfig, get_model

from ooc_arena.bash_arena_proxmox import MAX_SANDBOXES, BashArenaProxmoxSetting
from ooc_arena.parallel import enable_same_host_parallelism

HERE = Path(__file__).parent
MODEL_CONFIG = GenerateConfig(timeout=120, max_retries=2)
# The BashArena honest prompt its authors tuned for weaker models (GPT-4.1 mini).
TRUSTED_ELICITATION_PROMPT = (
    Path(ba_honest.__file__).parent / "system_prompts/honest_trusted_elicitation.txt"
).read_text()
# Per sample. time_limit is wall-clock from the end of sandbox init, so a stuck
# sample ends (and is scored on what it left behind) instead of holding a slot.
# Inspect also cuts scoring at half of it, and BashArena test suites can run
# long: its firewall drops loopback packets, so every call the tests make to a
# local service that is down waits out the connect timeout. --time-limit raises
# both.
MAX_STEPS = 100
# BashArena's default for the policy; restated because Anthropic models get an
# extra field. Inspect's OpenRouter provider only marks the system prompt and
# tools for caching in a tool loop, so every step re-bills the whole
# conversation. The top-level `cache_control` makes Anthropic cache up to the
# last message of each request; it is ignored unless the provider's own markers
# are off (`cache_prompt=False`). This changes billing, not what the model sees.
POLICY_CONFIG = {"max_tokens": 16000, "reasoning_tokens": 8000}
AUTO_CACHE = {"cache_control": {"type": "ephemeral"}}
TOKEN_LIMIT = 30_000_000
TIME_LIMIT_S = 7200


def _get_model_lenient_tools(name: str):
    """get_model() for BashArena's policy with non-strict tool schemas.

    Inspect's OpenRouter provider marks every tool `strict`, and OpenAI rejects
    the text editor's schema in strict mode (it has optional parameters).
    """
    return get_model(name, strict_tools=False)


def main(
    name: str,
    model: str,
    trusted_elicitation: bool,
    max_tasks: int | None,
    task_ids: list[str] | None,
    shuffle_seed: int | None,
    max_sandboxes: int,
    time_limit: int,
) -> None:
    enable_same_host_parallelism(max_sandboxes)
    setting = BashArenaProxmoxSetting(
        dataset_spec=DatasetSpec(
            max_tasks=max_tasks,
            task_id_whitelist=task_ids,
            shuffle_seed=shuffle_seed,
        )
    )
    ba_honest.get_model = _get_model_lenient_tools
    prompt = (
        {"system_prompt": TRUSTED_ELICITATION_PROMPT} if trusted_elicitation else {}
    )
    anthropic = "/anthropic/" in model
    generate_config = GenerateConfig(
        **POLICY_CONFIG,
        reasoning_effort="medium",
        extra_body=AUTO_CACHE if anthropic else None,
        cache_prompt=False if anthropic else None,
    )
    protocol = ba_honest.honest_policy(
        # Explicit: the policy's default model is resolved when it is built,
        # before ControlEvalConfig has set the untrusted model.
        model_name=model,
        trusted_elicitation=trusted_elicitation,
        generate_config=generate_config,
        **prompt,
    )
    config = ControlEvalConfig(
        untrusted_model=model,
        trusted_model=model,
        untrusted_config=MODEL_CONFIG,
        trusted_config=MODEL_CONFIG,
        max_steps=MAX_STEPS,
        token_limit=TOKEN_LIMIT,
        time_limit=time_limit,
        max_sandboxes=max_sandboxes,
        # A task that fails to build errors only its own sample.
        fail_on_error=False,
    )
    tasks = get_control_task_product(
        setting, protocol, [EvalMode.HONEST], eval_config=config, monitoring_scorers=[]
    )
    eval_args = {**config.eval_args(), "log_dir": str(HERE / "logs" / name)}
    eval(tasks=tasks, sandbox_cleanup=True, **eval_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="Run name: logs/<name>/.")
    parser.add_argument("--model", required=True, help="Inspect model id.")
    parser.add_argument(
        "--trusted-elicitation",
        action="store_true",
        help="Use BashArena's honest prompt and reminders for weaker models.",
    )
    parser.add_argument("--max-tasks", type=int, default=50)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument(
        "--task-ids",
        nargs="+",
        default=None,
        help="Run only these task ids (e.g. to finish an aborted run).",
    )
    parser.add_argument(
        "--max-sandboxes",
        type=int,
        default=MAX_SANDBOXES,
        help=f"Concurrent samples (each 6 GB RAM; default {MAX_SANDBOXES} fills "
        "the host's 40 GB).",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=TIME_LIMIT_S,
        help=f"Seconds per sample (default {TIME_LIMIT_S}); scoring gets half.",
    )
    args = parser.parse_args()
    main(
        name=args.name,
        model=args.model,
        trusted_elicitation=args.trusted_elicitation,
        max_tasks=None if args.task_ids else args.max_tasks,
        task_ids=args.task_ids,
        shuffle_seed=args.shuffle_seed,
        max_sandboxes=args.max_sandboxes,
        time_limit=args.time_limit,
    )

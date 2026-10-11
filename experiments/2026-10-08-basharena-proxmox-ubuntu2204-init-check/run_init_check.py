"""Bake and start BashArena tasks on the Proxmox backend without running an agent.

For each task: sandbox init (template bakes included), BashArena's setup solver,
then a few read-only probes of the agent VM. No model is called and nothing is
scored. Needs PROXMOX_* in the environment.

Experiment: research-log/2026-10-08-basharena-proxmox-ubuntu2204-init-check.md
Eval logs go to logs/ next to this script; probes.jsonl (one line per task that
got as far as the probes) is written next to it.

Usage (from the repo root; HERE = this script's directory):
    uv run python HERE/run_init_check.py --task-ids 36194749 26550327
    uv run python HERE/run_init_check.py --max-sandboxes 5 --task-ids ...
"""

import argparse
import json
from pathlib import Path

from control_arena import EvalMode
from control_arena.settings.bash_arena.task.dataset import DatasetSpec
from inspect_ai import Task, eval
from inspect_ai.solver import Generate, Solver, TaskState, chain, solver
from inspect_ai.util import sandbox

from ooc_arena.bash_arena_proxmox import MAX_SANDBOXES, BashArenaProxmoxSetting
from ooc_arena.parallel import enable_same_host_parallelism

HERE = Path(__file__).parent
LOG_DIR = HERE / "logs"
PROBES = HERE / "probes.jsonl"

# name -> shell command run as root on the agent VM after setup.
PROBE_COMMANDS = {
    "os": ". /etc/os-release; echo $VERSION_ID",
    "kernel": "uname -r",
    "python": "python3 --version; pip3 --version",
    "route": "ip -4 -o route get 1.1.1.1",
    "policy_rc_d": "cat /usr/sbin/policy-rc.d",
    # Units enabled now that were not before base.Dockerfile was applied.
    "new_enabled_units": "systemctl list-unit-files --state=enabled --no-legend "
    "| cut -d' ' -f1 | sort | comm -13 /var/lib/bash_arena_units -",
    "running_services": "systemctl list-units --type=service --state=running "
    "--no-legend --plain | cut -d' ' -f1",
    "failed_units": "systemctl list-units --state=failed --no-legend --plain "
    "| cut -d' ' -f1",
    "listening": "ss -ltnuH | awk '{print $1, $5}' | sort -u",
    "run_state": 'for f in /var/lib/bash_arena_run/*.tar; do [ -e "$f" ] || continue; '
    'tar -tf "$f" | while read -r p; do ls -ld "/run/$p"; done; done 2>&1',
    "database_server": "curl -s -m 10 -o /dev/null -w '%{http_code}' "
    "http://192.0.2.10/ || true",
}


@solver
def probe() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        row: dict[str, object] = {"task_id": str(state.sample_id)}
        for name, command in PROBE_COMMANDS.items():
            result = await sandbox().exec(
                ["bash", "-c", command], user="root", cwd="/", timeout=60
            )
            row[name] = (result.stdout + result.stderr).strip().splitlines()
        for key in ("base_setup_script_result", "task_setup_script_result"):
            result = state.metadata.get(key)
            row[key] = None if result is None else result.returncode
        with PROBES.open("a") as f:
            f.write(json.dumps(row) + "\n")
        state.completed = True
        return state

    return solve


def main(task_ids: list[str], max_sandboxes: int) -> None:
    enable_same_host_parallelism(max_sandboxes)
    setting = BashArenaProxmoxSetting(
        dataset_spec=DatasetSpec(task_id_whitelist=task_ids)
    )
    setup = setting.setup_environment()
    assert setup is not None
    task = Task(
        dataset=setting.get_dataset(EvalMode.HONEST),
        solver=chain(setup, probe()),
        name="bash_arena_proxmox_init_check",
    )
    eval(
        task,
        model="mockllm/model",
        sandbox_cleanup=True,
        max_sandboxes=max_sandboxes,
        # One task failing to bake must not stop the others.
        fail_on_error=False,
        log_dir=str(LOG_DIR),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task-ids", nargs="+", required=True)
    parser.add_argument(
        "--max-sandboxes",
        type=int,
        default=MAX_SANDBOXES,
        help="Concurrent samples on the Proxmox host (each 6 GB RAM; default "
        f"{MAX_SANDBOXES} fills the host's 40 GB). Lower it by one for every "
        "sample another eval is running there.",
    )
    args = parser.parse_args()
    main(args.task_ids, args.max_sandboxes)

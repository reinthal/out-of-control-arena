# Agent instructions

## Experiments and the research log

Every experiment has two homes that share one name, `<date>-<name-of-experiment>` (date as
`YYYY-MM-DD`, name in kebab-case):

- `experiments/<date>-<name-of-experiment>/` holds the one-off scripts written for that experiment and
  the artifacts specific to that run (eval logs, console output, plots, result tables). Scripts here
  are throwaway by design: they import reusable code from `src/ooc_arena/` and are not imported by
  anything else. Run them from the repo root.
- `research-log/<date>-<name-of-experiment>.md` documents the experiment. Start from
  `research-log/template.md`: context, a falsifiable hypothesis with accept/reject/inconclusive
  conditions decided before running, expected outcome, actual outcome, the exact command and
  parameters, and pointers to the artifacts in the experiment folder.

Rules of thumb:

- Do not add one-off run scripts to the repo root. Code that more than one experiment needs belongs in
  `src/ooc_arena/`.
- Point each script's eval logs at a `logs/` directory inside its experiment folder. `logs/` is
  gitignored at every depth, so eval logs stay local; anything that should be versioned (small result
  tables, plots) goes directly in the experiment folder.
- "Expected Outcome" in a research-log entry is for the human to fill in. Leave it as
  `<human fills in>` rather than writing a prediction.
- Write the research-log entry before running, and record the actual outcome in the same file after.

## Running evals: use the Proxmox host's memory

The Proxmox host has 40 GB of memory available for sandbox VMs. Evals should use it fully: do not run
samples one at a time unless there is a stated reason (for example a first smoke test of new backend
code). Set the number of concurrent samples from the memory each sample's VMs take:

    max sandboxes = floor(40 GB / memory per sample)

| Setting | VMs per sample | Memory per sample | `--max-sandboxes` |
| --- | --- | --- | --- |
| `BashArenaProxmoxSetting` | agent 4 GB + services 2 GB | 6 GB | 6 (the default) |
| `ProxmoxDefenseSetting` (`run_eval.py`) | one 2 GB VM | 2 GB | 20 (default is still 1) |

The 40 GB figure lives in `PROXMOX_MEMORY_MB` in `src/ooc_arena/parallel.py`; change it there if the
host changes. `MAX_SANDBOXES` in `src/ooc_arena/bash_arena_proxmox.py` is derived from it and is the
default for `--max-sandboxes` in the BashArena experiment scripts, so a new BashArena script should
import it rather than hardcode a number.

Recompute when a setting's VM sizes change (`AGENT_RAM_MB` in `src/ooc_arena/bash_arena_proxmox.py`,
`ram_mb` in the VM config), and count everything that will be on the host at the same time: other
evals already running there, and the one-off image import, which boots an 8 GB VM.

How parallelism works here (`src/ooc_arena/parallel.py`):

- Experiment scripts take `--max-sandboxes N` and call `enable_same_host_parallelism(N)` before
  `eval()`, and pass the same N to Inspect as `max_sandboxes`.
- Several eval processes started from this machine can share the host as well; their memory use adds
  up, so split the 40 GB between them (lower `--max-sandboxes` by one for every 6 GB another eval is
  using).
- Runs no longer sweep "orphan" VMs off the host at sample start. After a killed run, remove what it
  left with `sops exec-env secrets.env 'uv run inspect sandbox cleanup proxmox'`, and only while no
  eval is running: that command removes every sandbox VM on the host. It asks for confirmation only
  on an interactive terminal. Run from a script or an agent's shell it deletes at once, whatever is
  piped into it, so it cannot be used to list what is on the host. Check for a running eval by its
  process and log instead.

Record the `--max-sandboxes` value used in the research-log entry, and when a sequential run was
chosen, why.

## Excluded BashArena tasks

`EXCLUDED_TASK_IDS` in `src/ooc_arena/bash_arena_proxmox.py` lists tasks that are never run on the
Proxmox backend, each with its reason and a link to the issue that documents it. Do not remove an
entry to "get the full 50": the exclusion is applied after `max_tasks`, so `shuffle_seed=0,
max_tasks=50` now yields 49 tasks, and research-log entries should state the number actually run.

- `50618411` ("Resource Guardian"): its solution kills the VM's own long-running system processes.
  https://github.com/reinthal/out-of-control-arena/issues/1

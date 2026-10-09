## 2026-10-08

### Context
The GPT-4.1 mini usefulness baseline on the Proxmox BashArena backend
(`research-log/2026-10-07-basharena-proxmox-gpt41mini-usefulness-baseline.md`) was inconclusive: too
many samples errored before the agent ran. The errors, and a follow-up audit of the task Dockerfiles,
came down to two kinds of difference from BashArena's Docker environment:

- Release mismatch. The agent VM ran Ubuntu 24.04 because that is the only Ubuntu image the Proxmox
  sandbox plugin ships; BashArena's base image is 22.04. Effects: pip refusing to replace
  distro-installed packages (8 samples), packages missing on 24.04 (`netcat`, `php8.1-*`, versioned
  PostgreSQL/MariaDB, renamed libraries; 34 of 637 tasks predicted to fail), version drift.
- VM versus container. The `systemctl` stand-in package conflicts with systemd (13 tasks); `/run` is
  a tmpfs and systemd removes runtime directories (bake failure for `62987154`, 74 tasks set up state
  there); services installed by a task's packages were running at agent start (about 60-70 tasks);
  the setup step that routes the agent VM through the services VM raced the network coming up
  (4 samples).

A translation bug was found on the way: Docker drops backslashes and expands variables in an unquoted
`COPY <<EOF` heredoc, the backend wrote the body verbatim (87 tasks have `\$` in one; e.g. nginx
config with `\$uri`).

Changes made in `src/ooc_arena/bash_arena_proxmox.py` (`TEMPLATE_VERSION` 1 -> 2):

- Agent VM on Ubuntu 22.04: the jammy cloud image is imported with the plugin's own routine for its
  built-in image and tagged `builtin-ubuntu22.04`. The services VM stays on the plugin's 24.04.
  The 24.04 workarounds on the agent side are removed (`netcat` rewrite, `break-system-packages`).
- Routing step waits for a default route with a source address that holds for 5 s, and logs network
  state on failure (Linear AIS-384).
- `systemctl` is dropped from `apt-get install` package lists (AIS-385).
- Runtime directories are kept when a service stops during the bake, and the `/run` paths a
  Dockerfile names are archived and restored at every boot (AIS-386).
- Container-like service handling: a `policy-rc.d` that exits 101, as in the `ubuntu` Docker image,
  and units that a Dockerfile's packages enabled are disabled after it has been applied.
- `apt-daily` timers and unattended upgrades disabled, `needrestart` purged, in the base template.
- Unquoted `COPY` heredocs are expanded as Docker does (checked against `docker build` output).

None of this has run on Proxmox. Before spending model calls on a re-run of the baseline, check that
the environment comes up.

### Experiment

**Hypothesis (falsifiable):** With these changes, every task in the list below completes sandbox
initialisation (template bake, clone, services VM, routing) and BashArena's setup solver on the
Proxmox backend, on an agent VM that reports Ubuntu 22.04 and has no service running that the task's
packages installed.

**Test:** `run_init_check.py` runs each task through Inspect with BashArena's unchanged setup solver
followed by a probe solver that only reads state from the agent VM. No model is called, no agent
acts, nothing is scored. One epoch, up to 6 samples at a time.

Tasks (20):
- the 14 that errored in the baseline run as of 42/50 finished:
  `33519640 26550327 44938745 26415833 13293452 14234907 4357073 19750796 36194749 62987154 5844364
  50618411 9433452 1216794`
- `53451103` (installs `systemctl`), `31699056` (heredocs with `\$`, supervisor/nginx/php-fpm/
  memcached were running at start on 24.04)
- four that ran without error on 24.04, as a regression check: `6935769 19776681 24829213 7099712`

**Accept** if all 20 samples finish without error and, for every sample, the probes show: `os` is
`22.04`; `route` goes via the services VM; `new_enabled_units` contains nothing except
`bash-arena-run.service`; and `running_services` contains none of nginx, apache2, mysql, mariadb,
redis-server, postgresql, memcached, supervisor, php*-fpm, docker, containerd.

**Reject** if any sample errors for a reason attributable to the backend (bake, clone, routing,
setup solver), or any probe condition above fails.

**Inconclusive** if samples fail for reasons outside the backend (Proxmox host or network outage,
Ubuntu archive or PPA unavailable) and the rest pass.

Not covered, by design: whether tasks are as solvable as in Docker (that is the baseline re-run),
and the other 617 tasks. The four routing failures on 24.04 were intermittent (4 of 42), so four
clean samples here are weak evidence for that fix; all 20 samples exercise the step.

### Expected Outcome
<human fills in>

### Actual Outcome
**Accept.** All 20 samples finished without error (16:32 to 17:07, 35 minutes including the 22.04
image import, the services and base template bakes and 20 task template bakes, 6 samples at a time),
and every probe condition held for every sample:

| Condition | Result |
| --- | --- |
| Samples errored | 0 of 20 |
| `os` | `22.04` on all 20 (kernel 5.15.0-198, Python 3.10.12, pip 22.0.2) |
| `route` via the sample's services VM | all 20 |
| `new_enabled_units` | empty on all 20 |
| Task-installed services running at start | none on any sample |
| Failed units | none |
| Base and task setup scripts | exit 0 on all 20 |

Per group:
- The 14 tasks that errored on 24.04 all bake and start, as do `53451103` (`systemctl` package) and
  the four regression tasks.
- `/run` state: the directories the Dockerfiles create are present after boot with their owner and
  mode, e.g. `/run/mysqld` `root:root 700` on `62987154` (the fault that task plants) and `/run/php`
  `www-data` on `31699056`.
- `31699056` listens on :80 and 127.0.0.1:11211 with no nginx/memcached/php-fpm systemd unit
  running: its own setup script starts those three as plain daemons ("running but not supervised"),
  as it does in Docker. nginx starting is indirect evidence that its config, written from a `COPY`
  heredoc, is now valid.
- The database-server probe returned `401` (reached the server, no API key sent) on `5844364` and
  `44938745`, whose setup scripts whitelist `192.0.2.0/24` in BashArena's firewall, and no connection
  on the other 18, where the firewall blocks that address by default. So the route, the DNAT on the
  services VM and the agent-side firewall all behave as designed.

What this does not show:
- The routing fix was only exercised 20 times against a failure that occurred 4 times in 42.
- No probe reads the content of a heredoc-written file; the expansion was checked against
  `docker build` output locally, not on the VM.
- Services of the cloud image itself run on the agent VM and have no counterpart in the container:
  besides sshd, cron, rsyslog and systemd-resolved (named in the backend's docstring) also `snapd`,
  `packagekit`, `multipathd`, `irqbalance`, `polkit` and `systemd-timesyncd`.
- `21880360`, which failed the baseline with "Command timed out" during setup, was not in the list.
- In-process parallelism (6) and host sharing worked here without model traffic; a full agent run
  at 6 in parallel is still untested.

### Parameters/Configurations/scripts run
**Status (2026-10-08 16:32): running.** The baseline run was stopped by hand at 16:31 (it could no
longer change its verdict), its leftover VMs removed, and this check launched at 16:32 on an
otherwise empty host with `--max-sandboxes 6`. "Expected Outcome" above was still unfilled at launch.

Changed after this entry was first written, before launch:
- `src/ooc_arena/parallel.py`: host sharing (no sweep, own-VM cleanup, free /24 per sample) now
  applies to every run, not only `--max-sandboxes` > 1, with a lock file between eval processes for
  subnet/VM-id allocation and template bakes.
- This check runs samples in parallel (default 6, from the 40 GB in `AGENTS.md`) instead of
  sequentially. It is the first use of in-process parallelism on this backend, so a failure here can
  come from parallelism as well as from the environment changes; the error text should tell which.

From the repo root:
```
E=experiments/2026-10-08-basharena-proxmox-ubuntu2204-init-check
INSPECT_DISPLAY=plain INSPECT_LOG_LEVEL=info setsid nohup sops exec-env secrets.env \
  "uv run python $E/run_init_check.py --max-sandboxes 6 --task-ids 33519640 26550327 44938745 26415833 13293452 \
   14234907 4357073 19750796 36194749 62987154 5844364 50618411 9433452 1216794 53451103 31699056 \
   6935769 19776681 24829213 7099712; echo RUN_EXIT=\$?" \
  > $E/logs/run.log 2>&1 < /dev/null &
```
- `mockllm/model`, `--max-sandboxes 6`, `fail_on_error=False`, no limits.
- First sample also imports the 22.04 cloud image and bakes the services and agent base templates.
- Agent VM 4 GB RAM / 4 vCPU, services VM 2 GB / 2 vCPU, as in the baseline.
- Code uncommitted at time of writing (base commit `23fece6`).

### Artifacts
- Script: `experiments/2026-10-08-basharena-proxmox-ubuntu2204-init-check/run_init_check.py`
- Probe results, one JSON line per task that reached the probes:
  `experiments/2026-10-08-basharena-proxmox-ubuntu2204-init-check/probes.jsonl`
- Eval logs and console output: the experiment folder's `logs/` (local, gitignored).

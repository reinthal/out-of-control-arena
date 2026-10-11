"""Summarise a usefulness run from its eval logs while it is running or after.

A run that was aborted and restarted has several logs in its folder; they are
read together (a task id appears in one of them only).

Usage (from the repo root): uv run python HERE/status.py <run name> [--samples]
"""

import collections
import re
import statistics
import sys
from pathlib import Path

from inspect_ai.log import read_eval_log_samples

# Text in tool output that points at the environment rather than the task.
SIGNATURES = {
    "pip_distro": r"Cannot uninstall .*installed by debian|RECORD file not found",
    "port_in_use": r"Address already in use",
    "net_unreachable": r"Network is unreachable",
    "dns": r"Temporary failure in name resolution|Could not resolve host",
    "disk_full": r"No space left on device",
    "apt_lock": r"Could not get lock /var/lib/(dpkg|apt)",
    "no_candidate": r"has no installation candidate|Unable to locate package",
    "systemd_offline": r"System has not been booted with systemd|Failed to connect to bus",
    "oom": r"Out of memory|Cannot allocate memory|Killed process",
}


def main(name: str, per_sample: bool) -> None:
    logs = sorted((Path(__file__).parent / "logs" / name).glob("*.eval"))
    if not logs:
        print("no eval log yet")
        return
    scores, errors, limits = [], collections.defaultdict(list), collections.Counter()
    usage: collections.Counter[str] = collections.Counter()
    hits: dict[str, list[str]] = collections.defaultdict(list)
    side = 0
    samples = (
        s
        for log in logs
        for s in read_eval_log_samples(log, all_samples_required=False)
    )
    for s in samples:
        sid = str(s.id)
        if s.error:
            lines = [
                x.strip() for x in s.error.message.replace("\\n", "\n").splitlines()
            ]
            lines = [x for x in lines if x]
            errors[
                f"{lines[0][:70]} ... {lines[-2 if len(lines) > 1 else -1][:90]}"
            ].append(sid)
            continue
        value = s.scores["main_task_success"].value
        score = value["main_task_score"] if isinstance(value, dict) else None
        scores.append(score)
        side += s.scores["side_task_success"].value == "C"
        if s.limit:
            limits[s.limit.type] += 1
        fresh = cached = 0
        for u in (s.model_usage or {}).values():
            fresh += u.input_tokens or 0
            cached += u.input_tokens_cache_read or 0
            usage["input"] += u.input_tokens or 0
            usage["output"] += u.output_tokens or 0
            usage["cache_read"] += u.input_tokens_cache_read or 0
            usage["cache_write"] += u.input_tokens_cache_write or 0
        text = "\n".join(m.text for m in s.messages if m.role == "tool")
        found = [k for k, pat in SIGNATURES.items() if re.search(pat, text)]
        for k in found:
            hits[k].append(sid)
        if per_sample:
            steps = sum(1 for m in s.messages if m.role == "assistant")
            mins = round((s.total_time or 0) / 60)
            print(
                f"  {sid:>9} score={score} steps={steps} min={mins} "
                f"limit={s.limit.type if s.limit else '-'} "
                f"in={fresh / 1e3:.0f}k cache_read={cached / 1e3:.0f}k {','.join(found)}"
            )
    done = [x for x in scores if x is not None]
    print(f"logs: {len(logs)}, latest {logs[-1].name}")
    print(
        f"finished {len(scores) + sum(map(len, errors.values()))}: "
        f"scored {len(done)}, errored {sum(map(len, errors.values()))}, "
        f"unscored {len(scores) - len(done)}"
    )
    if len(done) > 1:
        sd = statistics.stdev(done)
        print(
            f"mean main_task_score {statistics.mean(done):.3f} (sd {sd:.3f}, "
            f"95% CI +-{1.96 * sd / len(done) ** 0.5:.3f}); side-task successes {side}"
        )
    print(f"limits hit: {dict(limits)}")
    print(f"tokens: { {k: f'{v / 1e6:.1f}M' for k, v in usage.items()} }")
    for k, ids in errors.items():
        print(f"ERROR x{len(ids)}: {k} | {' '.join(ids)}")
    for k, ids in hits.items():
        print(f"signature {k} x{len(ids)}: {' '.join(ids)}")


if __name__ == "__main__":
    main(sys.argv[1], "--samples" in sys.argv)

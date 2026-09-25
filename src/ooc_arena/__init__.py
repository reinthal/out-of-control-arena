"""Out-of-Control Arena: a ControlArena setting for AI cyber-defense evaluation.

An agent operates a shell on a Proxmox VM to solve a benign main task. In ATTACK
mode it also attempts a malicious side task (credential harvesting). A defensive
monitor reads the full transcript + tool calls and emits a suspicion score.
"""

# --- tenacity: surface the real error instead of RetryError -----------------
# inspect_proxmox_sandbox wraps most Proxmox API polling in @tenacity.retry
# without reraise=True, so when a retry loop times out (e.g. 300 s waiting for
# the QEMU guest agent) Inspect only sees "RetryError[<Future ... raised
# HTTPStatusError>]" and the underlying 403/500 message is lost. The plugin
# does not log it either. Default reraise=True so the last exception bubbles
# up. Must run before any proxmoxsandbox module is imported, which holds
# because ooc_arena.setting is the only importer and this package __init__
# runs first.
import tenacity as _tenacity

_original_tenacity_retry = _tenacity.retry


def _retry_reraise_by_default(*args, **kwargs):
    kwargs.setdefault("reraise", True)
    return _original_tenacity_retry(*args, **kwargs)


_tenacity.retry = _retry_reraise_by_default

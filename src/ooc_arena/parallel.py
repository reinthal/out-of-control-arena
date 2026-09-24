"""Run N sandbox samples concurrently on ONE Proxmox host.

inspect_proxmox_sandbox (0.11) hands out Proxmox *instances* from a pool and
guarantees each instance runs one sample at a time, so concurrency == number of
configured instances. With a single PROXMOX_HOST that is 1, regardless of
`max_sandboxes`. To use a big host we register the same host N times (distinct
`instance_id`, same `pool_id`) through PROXMOX_CONFIG_FILE.

Three plugin behaviours assume an instance is exclusive and are patched here:

1. `_ensure_instance_clean` (every sample start) treats *any* provider-managed
   VNET on the host as an orphan and sweeps every provider VM/VNET — including
   other live samples'. Disabled; sweep orphans manually with `cleanup-vms`.
2. On `sample_init` failure the plugin calls `cleanup_no_id`, the same
   host-wide sweep. Replaced with `task_cleanup`, which only destroys the
   resources this instance registered.
3. Every epoch of a dataset sample reuses the sample's `SandboxEnvironmentSpec`,
   so a per-sample subnet is still duplicated across concurrent epochs and
   Proxmox rejects it ("Duplicate IP range"). `create_sdn_and_vms` runs under
   the plugin's per-host lock, so we allocate a free 172.31.N.0/24 there by
   reading the host's live subnets, and rewrite the sample's SDN config.
"""

import ipaddress
import json
import logging
import os
import tempfile
from typing import Any

from proxmoxsandbox._impl.infra_commands import InfraCommands
from proxmoxsandbox._proxmox_sandbox_environment import ProxmoxSandboxEnvironment
from proxmoxsandbox.schema import SdnConfig

from ooc_arena.setting import SANDBOX_SUPERNET

logger = logging.getLogger(__name__)

_PATCHED = False
_SUPERNET = ipaddress.IPv4Network(SANDBOX_SUPERNET)


def _instances_json(n: int) -> str:
    env = os.environ
    host = env["PROXMOX_HOST"]
    base = {
        "pool_id": "default",
        "host": host,
        "port": int(env.get("PROXMOX_PORT", "8006")),
        "user": env.get("PROXMOX_USER", "root"),
        "user_realm": env.get("PROXMOX_REALM", "pam"),
        "password": env["PROXMOX_PASSWORD"],
        "node": env.get("PROXMOX_NODE", "proxmox"),
        "verify_tls": env.get("PROXMOX_VERIFY_TLS", "1") == "1",
        "image_storage": env.get("PROXMOX_IMAGE_STORAGE", "local-lvm"),
    }
    return json.dumps(
        {"instances": [{"instance_id": f"{host}-{i}", **base} for i in range(n)]}
    )


async def _used_third_octets(infra: InfraCommands) -> set[int]:
    """Third octets of every /24 under SANDBOX_SUPERNET configured on the host."""
    used: set[int] = set()
    for vnet in await infra.sdn_commands.read_all_vnets():
        subnets = await infra.async_proxmox.request(
            "GET", f"/cluster/sdn/vnets/{vnet['vnet']}/subnets"
        )
        for s in subnets or []:
            cidr = s.get("cidr")
            if not cidr:
                continue
            net = ipaddress.IPv4Network(cidr, strict=False)
            if net.subnet_of(_SUPERNET):
                used.add(int(str(net.network_address).split(".")[2]))
    return used


def _rewrite_octet(sdn_config: SdnConfig, new_octet: int) -> SdnConfig:
    """Move every 172.31.X.* address in the config to 172.31.<new_octet>.*."""
    prefix = ".".join(str(_SUPERNET.network_address).split(".")[:2])  # "172.31"

    def fix(v: Any) -> Any:
        if isinstance(v, str) and v.startswith(prefix + "."):
            parts = v.split(".")
            parts[2] = str(new_octet)
            return ".".join(parts)
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [fix(x) for x in v]
        return v

    # mode="json" so IPv4Network/IPv4Address fields come out as strings.
    return SdnConfig.model_validate(fix(sdn_config.model_dump(mode="json")))


def enable_same_host_parallelism(n: int) -> None:
    """Allow up to `n` concurrent samples on the single PROXMOX_HOST.

    Must be called before inspect_ai.eval() (the pool is initialised lazily at
    eval start). No-op for n <= 1.
    """
    global _PATCHED
    if n <= 1:
        return
    if os.environ.get("PROXMOX_CONFIG_FILE"):
        raise RuntimeError(
            "PROXMOX_CONFIG_FILE is already set; same-host parallelism only "
            "applies to the single-host PROXMOX_* env configuration."
        )

    # Contains the password: private tempfile, never written into the repo.
    fd, path = tempfile.mkstemp(prefix="proxmox-instances-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(_instances_json(n))
    os.chmod(path, 0o600)
    os.environ["PROXMOX_CONFIG_FILE"] = path

    if not _PATCHED:
        # 1. no host-wide orphan sweep at sample start
        async def _no_instance_sweep(_cls, _infra_commands, instance_id) -> None:
            logger.debug(f"skipping _ensure_instance_clean for {instance_id}")

        ProxmoxSandboxEnvironment._ensure_instance_clean = classmethod(  # type: ignore[method-assign]
            _no_instance_sweep
        )

        # 2. init-failure cleanup destroys only this instance's tracked resources
        async def _tracked_cleanup_only(self, _skip_confirmation=False) -> None:
            logger.info("cleanup_no_id -> task_cleanup (tracked resources only)")
            await self.task_cleanup()

        InfraCommands.cleanup_no_id = _tracked_cleanup_only  # type: ignore[method-assign]

        # 3. allocate a free /24 for this sample right before SDN creation
        _orig_create = InfraCommands.create_sdn_and_vms

        async def _create_with_free_subnet(
            self, proxmox_ids_start, sdn_config, vms_config
        ):
            if isinstance(sdn_config, SdnConfig):
                used = await _used_third_octets(self)
                free = next((o for o in range(1, 255) if o not in used), None)
                if free is None:
                    raise RuntimeError(f"no free /24 left under {SANDBOX_SUPERNET}")
                sdn_config = _rewrite_octet(sdn_config, free)
                logger.info(
                    f"{proxmox_ids_start}: allocated 172.31.{free}.0/24 "
                    f"(in use: {sorted(used)})"
                )
            return await _orig_create(self, proxmox_ids_start, sdn_config, vms_config)

        InfraCommands.create_sdn_and_vms = _create_with_free_subnet  # type: ignore[method-assign]
        _PATCHED = True

    logger.info(f"same-host parallelism: {n} instances on {os.environ['PROXMOX_HOST']}")

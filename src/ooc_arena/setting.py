"""ProxmoxDefenseSetting: a ControlArena Setting backed by a Proxmox VM.

Subclasses control_arena.settings._setting.Setting and implements the five required
members. The sandbox is a single built-in ubuntu24.04 VM provisioned by the
inspect_proxmox_sandbox plugin (which implements Inspect's SandboxEnvironment
contract, so the stock bash/python/text_editor tools work over it unchanged).

Proxmox connection is configured via environment variables read by the plugin
(PROXMOX_HOST/PORT/USER/REALM/PASSWORD/NODE/VERIFY_TLS/IMAGE_STORAGE); see README of
inspect_proxmox_sandbox. Requires Proxmox 9+.
"""

import itertools

from control_arena import EvalMode
from control_arena.settings._setting import Setting
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Scorer
from inspect_ai.solver import Solver, TaskState
from inspect_ai.tool import Tool, bash, python, text_editor
from inspect_ai.util import SandboxEnvironmentSpec
from proxmoxsandbox._proxmox_sandbox_environment import ProxmoxSandboxEnvironmentConfig
from proxmoxsandbox.schema import (
    DhcpRange,
    SdnConfig,
    SubnetConfig,
    VmConfig,
    VmNicConfig,
    VmSourceConfig,
    VnetConfig,
)

from ooc_arena.blue_agent import blue_investigation
from ooc_arena.dataset import get_dataset
from ooc_arena.environment import setup_environment_solver
from ooc_arena.scorers import blue_detection, main_task_success, side_task_success

DEFAULT_TOOL_TIMEOUT_S = 120

# Each sample gets its own /24 under this supernet (172.31.N.0/24). Distinct
# subnets per sample avoid the IP-range overlap that hangs provisioning when two
# sandboxes are alive at once; 172.31.0.0/16 is an uncommon slice of RFC-1918
# space, so one host-firewall rule blocking the whole supernet isolates every
# sandbox from the Proxmox control plane without touching typical LAN/pfSense
# networks. Do NOT collapse this back to a single hardcoded CIDR.
SANDBOX_SUPERNET = "172.31.0.0/16"

# Hands out distinct third octets (172.31.1, .2, ...) across get_sandbox_config
# calls within a process. Wraps at 253; sandbox_cleanup tears down each SDN
# after its sample, so reuse across runs is safe.
_subnet_octets = itertools.count(1)


class ProxmoxDefenseSetting(Setting):
    """Single-VM Proxmox setting for cyber-defense monitoring evaluation."""

    tool_timeout_s: int = DEFAULT_TOOL_TIMEOUT_S
    vm_image: str = "ubuntu24.04"

    @classmethod
    def get_name(cls) -> str:
        return "proxmox_defense"

    def get_agent_tools(self, state: TaskState) -> list[Tool]:
        return [
            bash(timeout=self.tool_timeout_s),
            python(timeout=self.tool_timeout_s),
            text_editor(),
        ]

    def get_dataset(self, eval_mode: EvalMode) -> list[Sample]:
        return get_dataset(eval_mode)

    def setup_environment(self) -> Solver | None:
        # Runs first: installs/locks auditd and starts the planted C2 process
        # for the standalone_c2 case (reads metadata["case"]).
        return setup_environment_solver()

    def post_submission(self) -> Solver | None:
        # Runs after the workload agent submits: the blue investigator with root
        # tools, blind to the transcript, writes its verdict to the store.
        return blue_investigation(tool_timeout_s=self.tool_timeout_s)

    def get_scorers(self) -> list[Scorer]:
        return [main_task_success(), side_task_success(), blue_detection()]

    def get_sandbox_config(self) -> SandboxEnvironmentSpec:
        # Build a per-sample SDN on 172.31.N.0/24 (N unique per call) and attach
        # the VM's NIC to it. Distinct subnet per sample => no IP-range overlap.
        octet = next(_subnet_octets) % 254 or 1
        base = f"172.31.{octet}"
        alias = f"ooc_sandbox_{octet}"
        sdn_config = SdnConfig(
            vnet_configs=(
                VnetConfig(
                    alias=alias,
                    subnets=(
                        SubnetConfig(
                            cidr=f"{base}.0/24",
                            gateway=f"{base}.1",
                            snat=True,  # NAT egress; needed for the built-in image bake
                            dhcp_ranges=(
                                DhcpRange(start=f"{base}.50", end=f"{base}.100"),
                            ),
                        ),
                    ),
                ),
            ),
            use_pve_ipam_dnsnmasq=True,
        )
        return SandboxEnvironmentSpec(
            "proxmox",
            ProxmoxSandboxEnvironmentConfig(
                vms_config=(
                    VmConfig(
                        vm_source_config=VmSourceConfig(built_in=self.vm_image),
                        name="agent",
                        nics=(VmNicConfig(vnet_alias=alias),),
                    ),
                ),
                sdn_config=sdn_config,
            ),
        )

"""ProxmoxDefenseSetting: a ControlArena Setting backed by a Proxmox VM.

Subclasses control_arena.settings._setting.Setting and implements the five required
members. The sandbox is a single built-in ubuntu24.04 VM provisioned by the
inspect_proxmox_sandbox plugin (which implements Inspect's SandboxEnvironment
contract, so the stock bash/python/text_editor tools work over it unchanged).

Proxmox connection is configured via environment variables read by the plugin
(PROXMOX_HOST/PORT/USER/REALM/PASSWORD/NODE/VERIFY_TLS/IMAGE_STORAGE); see README of
inspect_proxmox_sandbox. Requires Proxmox 9+.
"""

from control_arena import EvalMode
from control_arena.settings._setting import Setting
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Scorer
from inspect_ai.solver import TaskState
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

from ooc_bench.dataset import get_dataset
from ooc_bench.scorers import main_task_success, side_task_success

DEFAULT_TOOL_TIMEOUT_S = 120

# Pinned sandbox subnet (instead of sdn_config="auto", which picks a random
# 192.168.x.0/24 each run). A fixed, unusual CIDR lets you write a single stable
# host-firewall rule to block the sandbox from the Proxmox control plane, and
# avoids collisions with LAN/pfSense networks. See README firewall notes.
SANDBOX_CIDR = "172.31.99.0/24"
SANDBOX_GATEWAY = "172.31.99.1"
SANDBOX_DHCP_START = "172.31.99.50"
SANDBOX_DHCP_END = "172.31.99.100"
SANDBOX_VNET_ALIAS = "ooc_sandbox"


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

    def get_scorers(self) -> list[Scorer]:
        return [main_task_success(), side_task_success()]

    def get_sandbox_config(self) -> SandboxEnvironmentSpec:
        sdn_config = SdnConfig(
            vnet_configs=(
                VnetConfig(
                    alias=SANDBOX_VNET_ALIAS,
                    subnets=(
                        SubnetConfig(
                            cidr=SANDBOX_CIDR,
                            gateway=SANDBOX_GATEWAY,
                            snat=True,  # NAT egress; needed for the built-in image bake
                            dhcp_ranges=(
                                DhcpRange(
                                    start=SANDBOX_DHCP_START,
                                    end=SANDBOX_DHCP_END,
                                ),
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
                        nics=(VmNicConfig(vnet_alias=SANDBOX_VNET_ALIAS),),
                    ),
                ),
                sdn_config=sdn_config,
            ),
        )

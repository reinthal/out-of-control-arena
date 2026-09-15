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
from proxmoxsandbox.schema import VmConfig, VmSourceConfig

from ooc_bench.dataset import get_dataset
from ooc_bench.scorers import main_task_success, side_task_success

DEFAULT_TOOL_TIMEOUT_S = 120


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
        return SandboxEnvironmentSpec(
            "proxmox",
            ProxmoxSandboxEnvironmentConfig(
                vms_config=(
                    VmConfig(
                        vm_source_config=VmSourceConfig(built_in=self.vm_image),
                        name="agent",
                    ),
                ),
                sdn_config="auto",
            ),
        )

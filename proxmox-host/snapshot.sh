#!/usr/bin/env bash
#
# Copy the hand-maintained Proxmox host config into ./files/ so it is tracked in
# git. Run this ON the Proxmox node after changing any of the files below, then
# review `git diff proxmox-host/` and commit.
#
# Secrets (/etc/pve/priv/*, shadow, API tokens) are deliberately NOT captured.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HERE}/files"

PATHS=(
    # vnet-guard: block SDN guests from reaching the host
    /etc/vnet-guard.nft
    /etc/systemd/system/vnet-guard.service
    # host networking
    /etc/network/interfaces
    /etc/sysctl.d/99-forward.conf
    /etc/modprobe.d/zfs.conf
    # SDN (lab zone / vnet1 / 10.10.1.0/24, inspect zone / inspvmv0)
    /etc/pve/sdn/zones.cfg
    /etc/pve/sdn/vnets.cfg
    /etc/pve/sdn/subnets.cfg
    # PVE firewall
    /etc/pve/firewall/cluster.fw
    /etc/pve/firewall/100.fw
    /etc/pve/firewall/101.fw
    # VMs: 100 kali, 101 nix, 102 inspect template
    /etc/pve/qemu-server/100.conf
    /etc/pve/qemu-server/101.conf
    /etc/pve/qemu-server/102.conf
    # datacenter-wide
    /etc/pve/user.cfg
    /etc/pve/storage.cfg
    /etc/pve/datacenter.cfg
)

for p in "${PATHS[@]}"; do
    if [[ -f "$p" ]]; then
        install -D -m 0644 "$p" "${DEST}${p}"
        echo "captured ${p}"
    else
        echo "missing  ${p} (skipped)" >&2
    fi
done

# Record the PVE version the snapshot was taken on.
pveversion > "${DEST}/pveversion.txt"

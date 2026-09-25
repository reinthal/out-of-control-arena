#!/usr/bin/env bash
#
# Isolate the Proxmox host(s) from the eval sandbox network.
#
# The inspect_proxmox_sandbox VMs live on per-sample /24s under the
# 172.31.0.0/16 supernet (see src/ooc_arena/setting.py). This script installs
# persistent, cluster-synced Proxmox firewall rules so those sandbox VMs can
# still boot (DHCP) and resolve names (DNS) via the node, but cannot reach any
# other host service -- the API (8006), SSH, etc. A possibly-malicious agent in
# the sandbox therefore cannot attack the hypervisor control plane.
#
# Run this ON a Proxmox node (needs `pvesh`). Idempotent: re-running skips a
# node that already has rules for the supernet.
#
# Usage:
#   ./isolate_sandbox_host.sh                 # nodes: pve pvd
#   ./isolate_sandbox_host.sh pve pvd pvc     # custom node list
#   SANDBOX_SUPERNET=172.31.0.0/16 ./isolate_sandbox_host.sh
#
set -euo pipefail

SANDBOX_SUPERNET="${SANDBOX_SUPERNET:-172.31.0.0/16}"
NODES=("${@:-pve pvd}")
# Re-split in case the default single arg carried two names.
read -r -a NODES <<<"${NODES[*]}"

if ! command -v pvesh >/dev/null 2>&1; then
    echo "error: pvesh not found -- run this on a Proxmox node." >&2
    exit 1
fi

echo "Isolating sandbox supernet ${SANDBOX_SUPERNET} from nodes: ${NODES[*]}"

for N in "${NODES[@]}"; do
    echo "== node ${N} =="

    existing="$(pvesh get "/nodes/${N}/firewall/rules" --output-format json 2>/dev/null || echo '[]')"
    if printf '%s' "$existing" | grep -q "${SANDBOX_SUPERNET}"; then
        echo "  rules for ${SANDBOX_SUPERNET} already present -- skipping"
        continue
    fi

    # Enable the node firewall but keep the default inbound policy ACCEPT, so we
    # cannot lock ourselves out: only the sandbox supernet is dropped.
    pvesh set "/nodes/${N}/firewall/options" --enable 1 --policy_in ACCEPT

    # Allow the sandbox to reach the node's DHCP + DNS (needed to boot/resolve).
    # These ACCEPTs must precede the DROP -- pvesh appends, so add them first.
    pvesh create "/nodes/${N}/firewall/rules" --type in --action ACCEPT \
        --source "${SANDBOX_SUPERNET}" --proto udp --dport 67 --enable 1 \
        --comment "ooc-isolate: sandbox DHCP"
    pvesh create "/nodes/${N}/firewall/rules" --type in --action ACCEPT \
        --source "${SANDBOX_SUPERNET}" --proto udp --dport 53 --enable 1 \
        --comment "ooc-isolate: sandbox DNS (udp)"
    pvesh create "/nodes/${N}/firewall/rules" --type in --action ACCEPT \
        --source "${SANDBOX_SUPERNET}" --proto tcp --dport 53 --enable 1 \
        --comment "ooc-isolate: sandbox DNS (tcp)"

    # Drop everything else from the sandbox to this host (blocks 8006, SSH, ...).
    pvesh create "/nodes/${N}/firewall/rules" --type in --action DROP \
        --source "${SANDBOX_SUPERNET}" --enable 1 \
        --comment "ooc-isolate: sandbox -> host deny"

    echo "  rules installed"
done

# Cluster firewall must be enabled for node rules to take effect.
pvesh set /cluster/firewall/options --enable 1

echo "Done. Verify with: pvesh get /nodes/<node>/firewall/rules"
echo
echo "Note: this covers host-inbound traffic only. Cloud/link-local metadata"
echo "(169.254.169.254) is *forwarded*, not host-inbound -- if you need that"
echo "blocked too, add raw/FORWARD drops per the inspect_proxmox_sandbox README"
echo "and persist them separately (they do not survive reboot on their own)."

# Proxmox host config

The hand-maintained config of the Proxmox node (`pve`, 78.46.98.89) that runs the
lab. `files/` mirrors the host filesystem: `files/etc/foo` is `/etc/foo`.

Secrets are **not** tracked (`/etc/pve/priv/*`, the `inspect@pve` password, API
tokens). Set those again by hand after a rebuild.

## What's here

| Path | Purpose |
|---|---|
| `etc/vnet-guard.nft`, `etc/systemd/system/vnet-guard.service` | nftables `input` guard: SDN guests may reach the host only for DHCP, DNS and ping. The one exception is nix (10.10.1.101), which may reach the PVE API on :8006. |
| `etc/network/interfaces` | `vmbr0` uplink bridge. SDN vnets are written by PVE to `interfaces.d/sdn`, which is generated and not tracked. |
| `etc/sysctl.d/99-forward.conf` | IPv4 forwarding, needed for the SDN SNAT. |
| `etc/modprobe.d/zfs.conf` | ZFS ARC cap. |
| `etc/pve/sdn/*.cfg` | Zone `lab` → `vnet1` → 10.10.1.0/24 (kali, nix). Zone `inspvmz` → `inspvmv0` → 192.168.99.0/24 (inspect sandbox). Both use dnsmasq DHCP and SNAT. |
| `etc/pve/firewall/*.fw` | Cluster firewall, plus per-VM IP/MAC filters that pin kali to .100 and nix to .101. |
| `etc/pve/qemu-server/{100,101,102}.conf` | VMs: 100 `kali`, 101 `nix`, 102 `inspect-ubuntu24.04` (template). |
| `etc/pve/{user,storage,datacenter}.cfg` | `inspect@pve` user, the `InspectSandbox` role and its ACL, and storage definitions. |

The eval sandbox firewall rules (172.31.0.0/16) are managed separately by
`scripts/isolate_sandbox_host.sh`.

## Updating

After changing anything on the host:

```bash
./proxmox-host/snapshot.sh
git diff proxmox-host/
```

To track a new file, add it to `PATHS` in `snapshot.sh`.

## Rebuilding a host

On a fresh PVE 9 install whose root pool is `rpool`:

```bash
F=proxmox-host/files

# host files
install -m 0644 $F/etc/vnet-guard.nft /etc/
install -m 0644 $F/etc/systemd/system/vnet-guard.service /etc/systemd/system/
install -m 0644 $F/etc/sysctl.d/99-forward.conf /etc/sysctl.d/
install -m 0644 $F/etc/modprobe.d/zfs.conf /etc/modprobe.d/
# review before copying: the NIC name and IP/gateway are specific to this server
diff $F/etc/network/interfaces /etc/network/interfaces

# cluster filesystem (/etc/pve)
cp $F/etc/pve/{user,storage,datacenter}.cfg /etc/pve/
mkdir -p /etc/pve/sdn /etc/pve/firewall
cp $F/etc/pve/sdn/*.cfg /etc/pve/sdn/
cp $F/etc/pve/firewall/*.fw /etc/pve/firewall/
cp $F/etc/pve/qemu-server/*.conf /etc/pve/qemu-server/   # configs only, disks are not included

# apply
apt install -y dnsmasq && systemctl disable --now dnsmasq   # required by SDN DHCP
pvesh set /cluster/sdn                                      # apply SDN
sysctl --system
systemctl daemon-reload && systemctl enable --now vnet-guard
passwd / pveum passwd inspect@pve                           # secrets
```

The VM configs reference disks such as `local-zfs:vm-101-disk-0`. Restore those
from a backup (`vzdump` / `qmrestore`) or create empty disks and reinstall.
Remove the `[PENDING]` section from `100.conf` if you don't want those changes.

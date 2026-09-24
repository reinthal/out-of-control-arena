#!/usr/bin/env python3
"""Run a command inside a sandbox VM via the QEMU guest agent (Proxmox API).

Uses the same PROXMOX_* env vars as the eval (loaded by direnv from secrets.env).

    uv run python scripts/ga_exec.py <vmid> <cmd> [args...]
    uv run python scripts/ga_exec.py 103 bash -c 'id; hostname; ip -4 a'
"""

import os
import sys
import time

import httpx


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    vmid, cmd = sys.argv[1], sys.argv[2:]
    host = os.environ["PROXMOX_HOST"]
    port = os.environ.get("PROXMOX_PORT", "8006")
    node = os.environ["PROXMOX_NODE"]
    user = f"{os.environ['PROXMOX_USER']}@{os.environ['PROXMOX_REALM']}"
    verify = os.environ.get("PROXMOX_VERIFY_TLS", "1").lower() in ("1", "true", "yes")
    base = f"https://{host}:{port}/api2/json"

    c = httpx.Client(verify=verify, timeout=30)
    r = c.post(
        f"{base}/access/ticket",
        data={"username": user, "password": os.environ["PROXMOX_PASSWORD"]},
    )
    r.raise_for_status()
    d = r.json()["data"]
    c.cookies.set("PVEAuthCookie", d["ticket"])
    headers = {"CSRFPreventionToken": d["CSRFPreventionToken"]}

    r = c.post(
        f"{base}/nodes/{node}/qemu/{vmid}/agent/exec",
        headers=headers,
        json={"command": cmd},
    )
    if r.status_code != 200:
        print(f"exec failed: {r.status_code} {r.text}", file=sys.stderr)
        return 1
    pid = r.json()["data"]["pid"]

    deadline = time.time() + 120
    while time.time() < deadline:
        s = c.get(
            f"{base}/nodes/{node}/qemu/{vmid}/agent/exec-status", params={"pid": pid}
        ).json()["data"]
        if s.get("exited"):
            sys.stdout.write(s.get("out-data", ""))
            sys.stderr.write(s.get("err-data", ""))
            return int(s.get("exitcode", 0))
        time.sleep(0.5)
    print("timed out waiting for command", file=sys.stderr)
    return 124


if __name__ == "__main__":
    sys.exit(main())

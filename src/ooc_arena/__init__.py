"""Out-of-Control Arena: a ControlArena setting for AI cyber-defense evaluation.

An agent operates a shell on a Proxmox VM to solve a benign main task. In ATTACK
mode it also attempts a malicious side task (credential harvesting). A defensive
monitor reads the full transcript + tool calls and emits a suspicion score.
"""

#!/usr/bin/env python3
"""Minimal fake `docker` for lib_partition.sh tests. State lives in $FAKE_DOCKER_STATE (JSON).
Supports only the calls the library makes. Fault knobs: FAIL_CONNECT=1, DROP_ALIAS=<alias>,
FAIL_DISCONNECT=1. Every invocation is appended to $FAKE_DOCKER_LOG."""
import json, os, re, sys
S = os.environ["FAKE_DOCKER_STATE"]
st = json.load(open(S))
a = sys.argv[1:]
open(os.environ["FAKE_DOCKER_LOG"], "a").write(" ".join(a) + "\n")
def save(): json.dump(st, open(S, "w"))
C = st["containers"]
if a[0] == "info":
    print("fake docker"); sys.exit(0)
if a[0] == "inspect":
    c, fmt = a[1], a[3]
    if c not in C: sys.exit(1)
    if fmt == "{{json .NetworkSettings.Networks}}": print(json.dumps(C[c]["networks"]))
    elif fmt == "{{.State.Running}}": print("true" if C[c]["running"] else "false")
    elif m := re.fullmatch(r'\{\{json \(index \.NetworkSettings\.Networks "(.+)"\)\}\}', fmt):
        print(json.dumps(C[c]["networks"].get(m.group(1))))
    else: sys.exit(f"unsupported format {fmt}")
elif a[0] == "network" and a[1] == "disconnect":
    if os.environ.get("FAIL_DISCONNECT"): sys.exit(1)
    C[a[3]]["networks"].pop(a[2]); save()
elif a[0] == "network" and a[1] == "connect":
    if os.environ.get("FAIL_CONNECT"): sys.exit(1)
    rest, aliases, ipam = a[2:], [], {}
    while rest[0].startswith("--"):
        k, v = rest[0], rest[1]; rest = rest[2:]
        if k == "--alias": aliases.append(v)
        elif k == "--ip": ipam["IPv4Address"] = v
        elif k == "--ip6": ipam["IPv6Address"] = v
    net, c = rest
    drop = os.environ.get("DROP_ALIAS")
    C[c]["networks"][net] = {"Aliases": [x for x in aliases if x != drop], "IPAMConfig": ipam or None}; save()
elif a[0] == "network" and a[1] == "inspect":
    net, fmt = a[2], a[4]
    meta = st["networks"].get(net)
    if meta is None: sys.exit(1)
    if "com.docker.compose.project" in fmt: print(meta["project"])
    elif "com.docker.compose.network" in fmt: print(meta["name"])
    elif "range .Containers" in fmt: print(" ".join(n for n, v in C.items() if net in v["networks"]) + " ")
elif a[0] in ("start", "stop"):
    C[a[1]]["running"] = a[0] == "start"; save(); print(a[1])
elif a[0] == "ps":
    proj = [f.rsplit("=", 1)[1] for f in a if f.startswith("label=com.docker.compose.project=")][0]
    svc = [f.rsplit("=", 1)[1] for f in a if f.startswith("label=com.docker.compose.service=")][0]
    for n, v in C.items():
        if v.get("project") == proj and v.get("service") == svc: print(n)
else:
    sys.exit(f"unsupported: {a}")

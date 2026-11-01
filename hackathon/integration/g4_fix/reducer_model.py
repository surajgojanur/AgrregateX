"""Executable spec for #54: pg_trickle per-row CDC history reduction (offline, no database).

Models the three v0.108.3 copies of the reducer predicate
  DELETE ... WHERE (first_act='I' AND last_act='D') OR (rn_asc > 1 AND rn_desc > 1)
(refresh/delta_stage.rs:164, cdc/mod.rs:1501 compact_change_buffer, cdc/mod.rs:1659
build_st_compact_sql) against the correct keyed net-change rule, and shows what the P5 direct
aggregate (signed sum of staged images, aggregate.rs) would then write.

Correct keyed rule: a row's net effect over a window is (state before) -> (state after).
  before-image exists  <=> its earliest event is D   -> keep that earliest D
  after-image exists   <=> its latest   event is I   -> keep that latest  I
  every other event is discarded.
Proposed SQL:  DELETE ... WHERE NOT ((rn_asc = 1 AND action = 'D') OR (rn_desc = 1 AND action = 'I'))

Keyless sources (identity = row content hash, multiset) are NOT covered by either rule; see KEYLESS below.
usage: python3 -I reducer_model.py          (prints the truth table; exit 1 if the proposed rule is wrong)
"""
import json
import sys
from collections import Counter

# An event is (action, image). image = the group the row image falls into (here: status).
CASES = [
    ("I",            "insert only",                                [("I", "paid")]),
    ("D",            "delete only (row existed before)",           [("D", "paid")]),
    ("I,D",          "insert then delete",                         [("I", "paid"), ("D", "paid")]),
    ("D,I",          "update (existed before)  <- #50 Case B",     [("D", "paid"), ("I", "cancelled")]),
    ("I,D,I",        "insert then update  <- #50 Case A / Fedora", [("I", "paid"), ("D", "paid"), ("I", "cancelled")]),
    ("D,I,D",        "update then delete",                         [("D", "paid"), ("I", "shipped"), ("D", "shipped")]),
    ("D,I,D,I",      "two status updates",                         [("D", "paid"), ("I", "shipped"), ("D", "shipped"), ("I", "cancelled")]),
    ("I,D,I,D,I",    "insert, two updates",                        [("I", "paid"), ("D", "paid"), ("I", "shipped"), ("D", "shipped"), ("I", "cancelled")]),
    ("I,D,I,D",      "insert, update, delete",                     [("I", "paid"), ("D", "paid"), ("I", "shipped"), ("D", "shipped")]),
    ("D,I,D,I,D",    "two updates then delete",                    [("D", "paid"), ("I", "shipped"), ("D", "shipped"), ("I", "cancelled"), ("D", "cancelled")]),
    ("D,I (same grp)", "update not changing group (qty change)",   [("D", "paid"), ("I", "paid")]),
    ("I,D,I (same)", "insert then same-group update",              [("I", "paid"), ("D", "paid"), ("I", "paid")]),
]


def ranked(hist):
    n = len(hist)
    first, last = hist[0][0], hist[-1][0]
    return [(i + 1, n - i, a, img, first, last) for i, (a, img) in enumerate(hist)]


def current_keep(hist):
    """v0.108.3: delete if (first=I and last=D) or interior."""
    return [(a, img) for rn_asc, rn_desc, a, img, first, last in ranked(hist)
            if not ((first == "I" and last == "D") or (rn_asc > 1 and rn_desc > 1))]


def proposed_keep(hist):
    """keep earliest row iff it is D, latest row iff it is I."""
    return [(a, img) for rn_asc, rn_desc, a, img, first, last in ranked(hist)
            if (rn_asc == 1 and a == "D") or (rn_desc == 1 and a == "I")]


def truth(hist):
    keep = []
    if hist[0][0] == "D":
        keep.append(hist[0])
    if hist[-1][0] == "I":
        keep.append(hist[-1])
    return keep


def p5_delta(staged):
    """What the direct aggregate adds per group: +1 per I image, -1 per D image."""
    c = Counter()
    for a, img in staged:
        c[img] += 1 if a == "I" else -1
    return {k: v for k, v in sorted(c.items()) if v}


rows, ok = [], True
for code, label, hist in CASES:
    cur, prop, exp = current_keep(hist), proposed_keep(hist), truth(hist)
    exp_delta = p5_delta(exp)
    r = {"history": code, "case": label,
         "current_staged": cur, "current_delta": p5_delta(cur), "current_correct": p5_delta(cur) == exp_delta,
         "proposed_staged": prop, "proposed_delta": p5_delta(prop), "proposed_correct": prop == exp and p5_delta(prop) == exp_delta,
         "expected_delta": exp_delta}
    ok &= r["proposed_correct"]
    rows.append(r)

w = max(len(r["history"]) for r in rows)
print(f"{'history':<{w}}  {'expected net delta':<26} {'v0.108.3 delta':<34} {'proposed delta':<26}")
for r in rows:
    flag = "OK " if r["current_correct"] else "BUG"
    print(f"{r['history']:<{w}}  {json.dumps(r['expected_delta']):<26} {flag} {json.dumps(r['current_delta']):<30} "
          f"{'OK ' if r['proposed_correct'] else 'BAD'} {json.dumps(r['proposed_delta'])}")

# KEYLESS: identity is the row content hash, so identical rows share an identity and the history is a
# multiset, not one row's timeline. Neither the current nor the proposed positional rule is valid there.
k = [("I", "paid")] * 3
print(f"\nKEYLESS 3 identical inserts: correct +3; v0.108.3 keeps {len(current_keep(k))}, proposed keeps {len(proposed_keep(k))}"
      " -> proposed rule must be limited to keyed (SCAN_KEY) sources; keyless needs multiset (count) cancellation.")
json.dump(rows, open(__file__.replace(".py", "_truth_table.json"), "w"), indent=1)
sys.exit(0 if ok else 1)

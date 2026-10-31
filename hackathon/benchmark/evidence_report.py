"""Generate a conservative Issue #31 scorecard; small-demo results cannot qualify G1–G5."""
import argparse
import hashlib
import json
from pathlib import Path

from read_only_compare import reconciliation_ok


def report(root):
    http = json.loads((root / 'http/http.json').read_text())
    sql = json.loads((root / 'sql-corrected/comparison.json').read_text())
    executed = (root / 'sql-corrected/executed.sql').read_bytes()
    if hashlib.sha256(executed).hexdigest() != sql['sql_sha256']:
        raise ValueError('SQL artifact checksum mismatch')
    rows = http['samples']
    if not rows or not sql['comparisons'] or len(rows) != len(sql['comparisons']):
        raise ValueError('Incomplete API oracle')
    g4 = 'FAIL' if sql['failed'] or not reconciliation_ok(sql['reconciliation']) else 'INCOMPLETE'
    return dict(official_pass=False, automated_candidate_pass=False,
                dataset_orders=sql['source_orders'], scope='Fedora preserved small demo only',
                goals={'G1': 'NOT TESTED', 'G2': 'NOT TESTED', 'G3': 'INCOMPLETE',
                       'G4': g4, 'G5': 'NOT TESTED'}, http=http['summary'],
                comparisons=len(sql['comparisons']), failed=sql['failed'],
                reconciliation=sql['reconciliation'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    args = p.parse_args()
    result = report(args.run)
    (args.run / 'scorecard.json').write_text(json.dumps(result, indent=2) + '\n')
    text = f"# G1–G5 scorecard\n\nScope: preserved Fedora synthetic small demo ({result['dataset_orders']} orders). No official acceptance.\n\n"
    text += '| Goal | Good | Great | Measured evidence | Status |\n|---|---|---|---|---|\n'
    h = result['http']
    text += f"| G1 | <1 s | <200 ms at 10M | {h['samples']} HTTP samples; p50/p95/p99 {h['p50_ms']}/{h['p95_ms']}/{h['p99_ms']} ms; errors {h['errors']}, timeouts {h['timeouts']} | NOT TESTED at scale |\n"
    text += '| G2 | <5 min | <30 s | No Fedora writes authorized; Mac #46: 18/20 >30s timeouts | NOT TESTED locally; Mac Great failed |\n'
    text += '| G3 | <25% slowdown | <10% slowdown | Mac PR #46 matched 5 pairs, confounded by host freezes | INCOMPLETE |\n'
    text += f"| G4 | Most match | All match | {result['comparisons']} selected-field API comparisons, {result['failed']} failures; exact stream differences in comparison.json | {result['goals']['G4']} (small demo) |\n"
    text += '| G5 | <5× | <2× | No matched 1M/10M HTTP measurements | NOT TESTED |\n\n'
    text += 'Raw evidence: [HTTP](http/http.json), [SQL comparisons](sql-corrected/comparison.json), [exact SQL](sql-corrected/executed.sql), [drift detail](drift.txt).\n\n'
    text += 'G4 is a snapshot failure, not a proven engine root cause. No external-writer quiescence guarantee. API subset excludes the affected tenant/product interval. No tenant-isolation, adversarial tie, full boundary or mutation qualification.\n\n'
    text += 'Historical Mac 100k/1M generator evidence is documented in `hackathon/integration/scale/README.md`; no raw 1M HTTP run exists. Mac G3 source: [PR #46 report at 1d653de](https://github.com/surajgojanur/AgrregateX/blob/1d653de/hackathon/integration/g3/results/10k-o200-r20-matched/REPORT.md). No Fedora tuning or teammate files changed.\n'
    (args.run / 'G1_G5_SCORECARD.md').write_text(text)


if __name__ == '__main__':
    main()

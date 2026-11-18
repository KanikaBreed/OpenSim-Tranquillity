#!/usr/bin/env python3
"""Compare several runs of the test suite and report the tests that are not reliable.

Usage: flaky-report.py <rounds-dir>

<rounds-dir> holds one sub-folder per run (round-1, round-2, ...), each with the .trx files that run wrote.
Reports, as Markdown: tests that passed in some runs and failed in others (flaky), tests that failed in
every run, test projects whose test count differs between runs, and runs whose test host crashed or hung.
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
STOPPED = ("The active test run was aborted", "Test host process crashed", "exited with error")


def read_round(folder: Path):
    outcomes, counts, stopped, messages = {}, defaultdict(int), [], {}
    for trx in folder.rglob("*.trx"):
        root = ET.parse(trx).getroot()
        storage = {u.get("id"): Path(u.get("storage", "")).stem for u in root.iterfind("t:TestDefinitions/t:UnitTest", NS)}
        assemblies = sorted(set(storage.values()))
        for info in root.iterfind("t:ResultSummary/t:RunInfos/t:RunInfo", NS):
            text = (info.findtext("t:Text", default="", namespaces=NS) or "").strip()
            if info.get("outcome") == "Error" and any(m in text for m in STOPPED):
                stopped.append(f"{', '.join(assemblies) or trx.name}: {text.splitlines()[0]}")
        for res in root.iterfind("t:Results/t:UnitTestResult", NS):
            assembly = storage.get(res.get("testId"), "?")
            key = f"{assembly} :: {res.get('testName')}"
            outcome = res.get("outcome")
            if outcomes.get(key) != "Failed":
                outcomes[key] = outcome
            if outcome == "Failed" and key not in messages:
                msg = (res.findtext("t:Output/t:ErrorInfo/t:Message", default="", namespaces=NS) or "").strip()
                messages[key] = msg.splitlines()[0][:160] if msg else ""
            counts[assembly] += 1
    return outcomes, counts, stopped, messages


def main() -> int:
    rounds = sorted(p for p in Path(sys.argv[1]).iterdir() if p.is_dir())
    data = {r.name: read_round(r) for r in rounds}
    names = list(data)
    print(f"# Flaky test hunt: {len(names)} runs\n")

    tests = defaultdict(dict)
    messages = {}
    for name, (outcomes, _, _, msgs) in data.items():
        for key, outcome in outcomes.items():
            tests[key][name] = outcome
        messages.update(msgs)

    flaky, always = [], []
    for key, per_run in sorted(tests.items()):
        failed = sum(1 for o in per_run.values() if o == "Failed")
        passed = sum(1 for o in per_run.values() if o == "Passed")
        if failed and passed:
            flaky.append((failed, key))
        elif failed and failed == len(names):
            always.append(key)

    print(f"## Flaky: {len(flaky)}\n")
    for failed, key in sorted(flaky, key=lambda x: (-x[0], x[1])):
        print(f"- {failed}/{len(names)} failed: `{key}`  \n  {messages.get(key, '')}")
    print(f"\n## Failed in every run: {len(always)}\n")
    for key in always:
        print(f"- `{key}`  \n  {messages.get(key, '')}")

    print("\n## Test counts that differ between runs\n")
    assemblies = sorted({a for (_, counts, _, _) in data.values() for a in counts})
    differ = False
    for a in assemblies:
        row = [data[n][1].get(a, 0) for n in names]
        if len(set(row)) > 1:
            differ = True
            print(f"- `{a}`: " + ", ".join(f"{n} {c}" for n, c in zip(names, row)))
    if not differ:
        print("- none")

    print("\n## Test hosts that crashed or hung\n")
    any_stopped = False
    for n in names:
        for s in data[n][2]:
            any_stopped = True
            print(f"- {n}: {s}")
    if not any_stopped:
        print("- none")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Write a compact JUnit summary to GitHub's step summary file."""

from __future__ import annotations

import argparse
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize_junit(path: Path) -> dict[str, int | float]:
    root = ET.parse(path).getroot()
    suites = list(root) if root.tag == "testsuites" else [root]
    totals: dict[str, int | float] = {
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "time": 0.0,
    }
    for suite in suites:
        for key in ("tests", "failures", "errors", "skipped"):
            totals[key] += int(suite.attrib.get(key, 0))
        totals["time"] += float(suite.attrib.get("time", 0.0))
    return totals


def render_summary(label: str, totals: dict[str, int | float]) -> str:
    passed = int(totals["tests"]) - int(totals["failures"]) - int(totals["errors"]) - int(
        totals["skipped"]
    )
    return (
        f"## Tests: {label}\n\n"
        f"- Passed: {passed}\n"
        f"- Failed: {int(totals['failures'])}\n"
        f"- Errors: {int(totals['errors'])}\n"
        f"- Skipped: {int(totals['skipped'])}\n"
        f"- Duration: {float(totals['time']):.2f}s\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit", type=Path)
    parser.add_argument("--label", default="pytest")
    args = parser.parse_args()

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path or not args.junit.exists():
        return 0
    with Path(summary_path).open("a", encoding="utf-8") as summary_file:
        summary_file.write(render_summary(args.label, summarize_junit(args.junit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

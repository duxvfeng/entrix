from pathlib import Path

from scripts.write_test_summary import render_summary, summarize_junit


def test_summarize_junit_aggregates_suites(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuites><testsuite tests="4" failures="1" errors="0" skipped="1" time="1.2"/>'
        '<testsuite tests="2" failures="0" errors="1" skipped="0" time="0.3"/></testsuites>',
        encoding="utf-8",
    )

    totals = summarize_junit(report)

    assert totals == {"tests": 6, "failures": 1, "errors": 1, "skipped": 1, "time": 1.5}
    summary = render_summary("Windows 3.12", totals)
    assert "Passed: 3" in summary
    assert "Duration: 1.50s" in summary

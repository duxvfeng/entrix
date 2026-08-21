from pathlib import Path

from scripts.check_new_debug_prints import (
    Finding,
    findings_from_diff,
    findings_from_untracked,
    is_checked_source,
)


def test_checked_source_excludes_docs_and_tests() -> None:
    assert is_checked_source("entrix/cli.py") is True
    assert is_checked_source("entrix/cli_overview.py") is False
    assert is_checked_source("entrix/test_mapping.py") is True
    assert is_checked_source("src/app.ts") is True
    assert is_checked_source("docs/example.py") is False
    assert is_checked_source("tests/test_cli.py") is False
    assert is_checked_source("src/app.test.ts") is False


def test_findings_from_diff_tracks_the_current_file() -> None:
    diff = """\
diff --git a/entrix/cli.py b/entrix/cli.py
--- a/entrix/cli.py
+++ b/entrix/cli.py
@@ -1,0 +2,2 @@
+print('debug')
+value = 1
diff --git a/tests/test_cli.py b/tests/test_cli.py
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,0 +2 @@
+print('allowed in tests')
"""

    assert findings_from_diff(diff) == [Finding("entrix/cli.py", "print('debug')")]


def test_findings_from_untracked_scans_only_source_files(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("pprint(data)\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_app.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("print('allowed')\n", encoding="utf-8")

    assert findings_from_untracked(tmp_path, ["src/app.py", "tests/test_app.py"]) == [
        Finding("src/app.py", "pprint(data)")
    ]

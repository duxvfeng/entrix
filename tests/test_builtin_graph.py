"""Tests for the built-in structural analyzer."""

import importlib.util
import json
from pathlib import Path

import pytest

from entrix.structure import builtin as builtin_module
from entrix.structure.builtin import BuiltinGraphAdapter

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack is not installed",
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_builtin_graph_parses_typescript_and_links_tests(tmp_path: Path):
    _write(
        tmp_path / "src" / "mod.ts",
        "export function run() { return helper() }\nfunction helper() { return 1 }\n",
    )
    _write(
        tmp_path / "src" / "mod.test.ts",
        "import { run } from './mod'\ntest('run works', () => run())\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    query = adapter.query("tests_for", "src/mod.ts:run")

    assert build["status"] == "ok"
    assert "typescript" in build["languages"]
    assert query["status"] == "ok"
    assert [item["file_path"] for item in query["results"]] == ["src/mod.test.ts"]


def test_builtin_graph_scans_repo_beyond_default_roots(tmp_path: Path):
    _write(
        tmp_path / "pkg" / "service.py",
        "def run():\n    return 1\n",
    )
    _write(
        tmp_path / "tests" / "service_test.py",
        "from pkg.service import run\n\n\ndef test_run():\n    assert run() == 1\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    tests = adapter.query("tests_for", "pkg/service.py:run")

    assert build["status"] == "ok"
    assert build["files_updated"] == 2
    assert [item["qualified_name"] for item in tests["results"]] == [
        "tests/service_test.py:test_run"
    ]


def test_builtin_graph_parses_python_and_tracks_import_impact(tmp_path: Path):
    _write(
        tmp_path / "src" / "service.py",
        "def run():\n    return helper()\n\n\ndef helper():\n    return 1\n",
    )
    _write(
        tmp_path / "src" / "consumer.py",
        "from .service import run\n\n\ndef consume():\n    return run()\n",
    )
    _write(
        tmp_path / "src" / "test_service.py",
        "from .service import run\n\n\ndef test_run():\n    assert run() == 1\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    impact = adapter.impact_radius(["src/service.py"], depth=1)
    tests = adapter.query("tests_for", "src/service.py:run")

    assert impact["status"] == "ok"
    assert sorted(impact["impacted_files"]) == ["src/consumer.py", "src/test_service.py"]
    assert [item["qualified_name"] for item in tests["results"]] == ["src/test_service.py:test_run"]


def test_builtin_graph_qualifies_python_class_methods(tmp_path: Path):
    _write(
        tmp_path / "src" / "service.py",
        "class Service:\n    def run(self):\n        return helper()\n\n\ndef helper():\n    return 1\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    children = adapter.query("children_of", "src/service.py")
    callees = adapter.query("callees_of", "src/service.py:Service.run")

    assert {item["qualified_name"] for item in children["results"]} == {
        "src/service.py:Service",
        "src/service.py:Service.run",
        "src/service.py:helper",
    }
    assert [item["qualified_name"] for item in callees["results"]] == ["src/service.py:helper"]


def test_builtin_graph_parses_rust_test_attributes(tmp_path: Path):
    _write(
        tmp_path / "crates" / "demo" / "src" / "lib.rs",
        "pub fn compute() -> i32 { 1 }\n\n#[cfg(test)]\nmod tests {\n    use super::compute;\n\n    #[test]\n    fn compute_works() {\n        assert_eq!(compute(), 1);\n    }\n}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    tests = adapter.query("tests_for", "crates/demo/src/lib.rs:compute")
    stats = adapter.stats()

    assert build["status"] == "ok"
    assert "rust" in build["languages"]
    assert tests["status"] == "ok"
    assert [item["qualified_name"] for item in tests["results"]] == [
        "crates/demo/src/lib.rs:compute_works"
    ]
    assert stats["backend"] == "builtin-tree-sitter"


def test_builtin_graph_qualifies_rust_impl_methods(tmp_path: Path):
    _write(
        tmp_path / "crates" / "demo" / "src" / "lib.rs",
        "struct Runner;\n\nimpl Runner {\n    fn run(&self) -> i32 {\n        helper()\n    }\n}\n\nfn helper() -> i32 {\n    1\n}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    children = adapter.query("children_of", "crates/demo/src/lib.rs")
    callees = adapter.query("callees_of", "crates/demo/src/lib.rs:Runner.run")

    assert "crates/demo/src/lib.rs:Runner.run" in {
        item["qualified_name"] for item in children["results"]
    }
    assert [item["qualified_name"] for item in callees["results"]] == [
        "crates/demo/src/lib.rs:helper"
    ]


def test_builtin_graph_resolves_multiline_grouped_rust_imports(tmp_path: Path):
    _write(
        tmp_path / "crates" / "demo" / "src" / "lib.rs",
        "mod commands;\nmod agent;\n",
    )
    _write(
        tmp_path / "crates" / "demo" / "src" / "commands" / "mod.rs",
        "pub fn execution_budget() -> u64 { 240 }\npub fn output_contains_artifact_payload() -> bool { true }\n",
    )
    _write(
        tmp_path / "crates" / "demo" / "src" / "agent.rs",
        "use crate::commands::{\n    execution_budget,\n    output_contains_artifact_payload,\n};\n\npub fn run() -> bool {\n    execution_budget() > 0 && output_contains_artifact_payload()\n}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    imports = adapter.query("imports_of", "crates/demo/src/agent.rs")

    assert build["status"] == "ok"
    assert [item["qualified_name"] for item in imports["results"]] == [
        "crates/demo/src/commands/mod.rs"
    ]


def test_builtin_graph_handles_ci_style_grouped_rust_import_text(tmp_path: Path):
    _write(tmp_path / "crates" / "demo" / "src" / "lib.rs", "mod commands;\n")
    _write(
        tmp_path / "crates" / "demo" / "src" / "commands" / "mod.rs",
        "pub fn execution_budget() {}\npub fn output_contains_artifact_payload() {}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    resolved = adapter._resolve_rust_import(
        "crates/demo/src/lib.rs",
        """use crate::commands::{
        execution_budget, output_contains_artifact_payload, parse_prompt,
        recover_success_artifacts_from_output, validate_prompt, validate_success_artifacts,
        write_artifact_set, write_baseline_artifacts, UiJourneyAggregateRun, UiJourneyPromptParams,
        UiJourneyRunContext, UiJourneyRunMetrics, DEFAULT_ARTIFACT_DIR, DEFAULT_BASE_URL,
        DEFAULT_SCENARIO_ID,
    };""",
    )

    assert resolved == "crates/demo/src/commands/mod.rs"


def test_builtin_graph_qualifies_typescript_class_methods(tmp_path: Path):
    _write(
        tmp_path / "src" / "runner.ts",
        "class Runner {\n  run() {\n    return helper();\n  }\n}\n\nfunction helper() {\n  return 1;\n}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    children = adapter.query("children_of", "src/runner.ts")
    callees = adapter.query("callees_of", "src/runner.ts:Runner.run")

    assert "src/runner.ts:Runner.run" in {item["qualified_name"] for item in children["results"]}
    assert [item["qualified_name"] for item in callees["results"]] == ["src/runner.ts:helper"]


def test_builtin_graph_limits_call_edges_to_local_or_imported_symbols(tmp_path: Path):
    _write(
        tmp_path / "src" / "dep.py",
        "def run():\n    return 1\n",
    )
    _write(
        tmp_path / "src" / "other.py",
        "def run():\n    return 2\n",
    )
    _write(
        tmp_path / "src" / "consumer.py",
        "from .dep import run\n\n\ndef consume():\n    return run()\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    callees = adapter.query("callees_of", "src/consumer.py:consume")

    assert [item["qualified_name"] for item in callees["results"]] == ["src/dep.py:run"]


def test_builtin_graph_avoids_ambiguous_global_call_matches(tmp_path: Path):
    _write(
        tmp_path / "src" / "first.py",
        "def run():\n    return 1\n",
    )
    _write(
        tmp_path / "src" / "second.py",
        "def run():\n    return 2\n",
    )
    _write(
        tmp_path / "src" / "consumer.py",
        "def consume():\n    return run()\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    callees = adapter.query("callees_of", "src/consumer.py:consume")

    assert callees["results"] == []


def test_builtin_graph_limits_tests_to_matching_symbols(tmp_path: Path):
    _write(
        tmp_path / "src" / "mod.ts",
        "export function run() { return 1 }\nexport function helper() { return 2 }\n",
    )
    _write(
        tmp_path / "src" / "mod.test.ts",
        "import { run, helper } from './mod'\ntest('run works', () => run())\nvoid helper\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    run_tests = adapter.query("tests_for", "src/mod.ts:run")
    helper_tests = adapter.query("tests_for", "src/mod.ts:helper")

    assert [item["qualified_name"] for item in run_tests["results"]] == ["src/mod.test.ts:test:2"]
    assert helper_tests["results"] == []


def test_builtin_graph_matches_mocked_function_targets_in_tests(tmp_path: Path):
    _write(
        tmp_path / "src" / "boards.ts",
        "export async function ensureDefaultBoard() { return { id: 'board-1' } }\n",
    )
    _write(
        tmp_path / "src" / "task-board-context.test.ts",
        "import { describe, expect, it, vi } from 'vitest'\n"
        "import { ensureDefaultBoard } from './boards'\n"
        "vi.mock('./boards', () => ({ ensureDefaultBoard: vi.fn() }))\n"
        "describe('ctx', () => {\n"
        "  it('uses default board', async () => {\n"
        "    vi.mocked(ensureDefaultBoard).mockResolvedValue({ id: 'board-1' })\n"
        "    expect(ensureDefaultBoard).toBeDefined()\n"
        "  })\n"
        "})\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    tests = adapter.query("tests_for", "src/boards.ts:ensureDefaultBoard")

    assert [item["qualified_name"] for item in tests["results"]] == [
        "src/task-board-context.test.ts:test:5"
    ]


def test_builtin_graph_queries_from_persisted_index_without_file_cache(tmp_path: Path):
    _write(
        tmp_path / "src" / "service.py",
        "def run():\n    return helper()\n\n\ndef helper():\n    return 1\n",
    )
    _write(
        tmp_path / "src" / "consumer.py",
        "from .service import run\n\n\ndef consume():\n    return run()\n",
    )
    _write(
        tmp_path / "src" / "test_service.py",
        "from .service import run\n\n\ndef test_run():\n    assert run() == 1\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    adapter.files_cache_path.unlink()

    persisted = BuiltinGraphAdapter(tmp_path)
    stats = persisted.stats()
    impact = persisted.impact_radius(["src/service.py"], depth=1)
    tests = persisted.query("tests_for", "src/service.py:run")

    assert stats["status"] == "ok"
    assert stats["files"] == 3
    assert sorted(impact["impacted_files"]) == ["src/consumer.py", "src/test_service.py"]
    assert [item["qualified_name"] for item in tests["results"]] == ["src/test_service.py:test_run"]


def test_builtin_graph_parses_go_functions_and_methods(tmp_path: Path):
    _write(
        tmp_path / "pkg" / "runner.go",
        "package pkg\n\ntype Runner struct{}\n\nfunc (r Runner) Start() {\n\thelper()\n}\n\nfunc helper() {}\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    children = adapter.query("children_of", "pkg/runner.go")
    callees = adapter.query("callees_of", "pkg/runner.go:Runner.Start")

    assert build["status"] == "ok"
    assert "go" in build["languages"]
    assert {"pkg/runner.go:Runner", "pkg/runner.go:Runner.Start", "pkg/runner.go:helper"} <= {
        item["qualified_name"] for item in children["results"]
    }
    assert [item["qualified_name"] for item in callees["results"]] == ["pkg/runner.go:helper"]


def test_builtin_graph_parses_plain_javascript(tmp_path: Path):
    _write(
        tmp_path / "src" / "app.js",
        "function run() { return helper(); }\n\nfunction helper() { return 1; }\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    children = adapter.query("children_of", "src/app.js")
    callees = adapter.query("callees_of", "src/app.js:run")

    assert build["status"] == "ok"
    assert "javascript" in build["languages"]
    assert {"src/app.js:run", "src/app.js:helper"} <= {
        item["qualified_name"] for item in children["results"]
    }
    assert [item["qualified_name"] for item in callees["results"]] == ["src/app.js:helper"]


def test_builtin_graph_rejects_unknown_query_type(tmp_path: Path):
    adapter = BuiltinGraphAdapter(tmp_path)

    result = adapter.query("bogus_query", "src/app.py")

    assert result["status"] == "error"
    assert "bogus_query" in result["summary"]


def test_builtin_graph_returns_not_found_for_missing_target(tmp_path: Path):
    _write(tmp_path / "src" / "app.py", "def run():\n    return 1\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)

    missing_node = adapter.query("callees_of", "src/ghost.py:nope")
    missing_file = adapter.query("file_summary", "docs/nope.py")

    assert missing_node["status"] == "not_found"
    assert missing_file["status"] == "not_found"


def test_builtin_graph_summarizes_single_file(tmp_path: Path):
    _write(
        tmp_path / "src" / "service.py",
        "class Service:\n    def run(self):\n        return 1\n",
    )

    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    summary = adapter.query("file_summary", "src/service.py")

    assert summary["status"] == "ok"
    qualified = {item["qualified_name"] for item in summary["results"]}
    assert "src/service.py" in qualified
    assert "src/service.py:Service.run" in qualified


def test_builtin_graph_impact_radius_ignores_unknown_files(tmp_path: Path):
    _write(tmp_path / "src" / "app.py", "def run():\n    return 1\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)

    impact = adapter.impact_radius(["docs/not-in-index.py"], depth=1)

    assert impact["status"] == "ok"
    assert impact["impacted_files"] == []
    assert impact["changed_nodes"] == []


def test_builtin_graph_incremental_build_reparses_only_changed_files(tmp_path: Path, monkeypatch):
    _write(tmp_path / "src" / "a.py", "def one():\n    return 1\n")
    _write(tmp_path / "src" / "b.py", "def two():\n    return 2\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)

    _write(tmp_path / "src" / "a.py", "def one():\n    return 11\n\n\ndef one_more():\n    return 1\n")
    monkeypatch.setattr(
        builtin_module, "git_changed_files", lambda repo_root, base="HEAD~1": ["src/a.py"]
    )
    build = adapter.build_or_update()
    summary = adapter.query("file_summary", "src/a.py")

    assert build["status"] == "ok"
    assert build["build_type"] == "incremental"
    assert build["files_updated"] == 1
    assert "src/a.py:one_more" in {item["qualified_name"] for item in summary["results"]}


def test_builtin_graph_drops_stale_files_from_index(tmp_path: Path, monkeypatch):
    _write(tmp_path / "src" / "a.py", "def one():\n    return 1\n")
    _write(tmp_path / "src" / "b.py", "def two():\n    return 2\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)

    (tmp_path / "src" / "b.py").unlink()
    monkeypatch.setattr(builtin_module, "git_changed_files", lambda repo_root, base="HEAD~1": [])
    build = adapter.build_or_update()
    stats = adapter.stats()

    assert build["status"] == "ok"
    assert build["stale_files"] == ["src/b.py"]
    assert stats["files"] == 1


def test_builtin_graph_rebuilds_after_corrupted_cache(tmp_path: Path):
    _write(tmp_path / "src" / "app.py", "def run():\n    return 1\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)

    adapter.files_cache_path.write_text("{not valid json", encoding="utf-8")
    rebuilt = BuiltinGraphAdapter(tmp_path)
    build = rebuilt.build_or_update(full=True)
    stats = rebuilt.stats()

    assert build["status"] == "ok"
    assert build["files_updated"] == 1
    assert stats["files"] == 1
    assert json.loads(rebuilt.files_cache_path.read_text(encoding="utf-8"))["version"] == 4


def test_builtin_graph_falls_back_to_legacy_cache(tmp_path: Path):
    _write(tmp_path / "src" / "app.py", "def run():\n    return 1\n")
    adapter = BuiltinGraphAdapter(tmp_path)
    adapter.build_or_update(full=True)
    files_payload = json.loads(adapter.files_cache_path.read_text(encoding="utf-8"))
    adapter.files_cache_path.unlink()
    adapter.index_cache_path.unlink()
    adapter.legacy_cache_path.write_text(json.dumps(files_payload), encoding="utf-8")

    migrated = BuiltinGraphAdapter(tmp_path)
    stats = migrated.stats()

    assert stats["status"] == "ok"
    assert stats["files"] == 1


def test_builtin_graph_analyze_file_reports_language_and_symbols(tmp_path: Path):
    _write(tmp_path / "src" / "app.py", "def run():\n    return 1\n")
    _write(tmp_path / "README.md", "# demo\n")
    adapter = BuiltinGraphAdapter(tmp_path)

    parsed = adapter.analyze_file("src/app.py")
    unsupported = adapter.analyze_file("README.md")
    missing = adapter.analyze_file("src/ghost.py")

    assert parsed["status"] == "ok"
    assert parsed["language"] == "python"
    assert [item["qualified_name"] for item in parsed["symbols"]] == ["src/app.py:run"]
    assert unsupported["status"] == "unsupported"
    assert missing["status"] == "not_found"


def test_builtin_graph_honors_ignore_patterns_and_binary_files(tmp_path: Path):
    _write(tmp_path / "src" / "ok.py", "def ok():\n    return 1\n")
    _write(tmp_path / "vendor" / "lib.py", "def vendored():\n    return 2\n")
    _write(tmp_path / "node_modules" / "dep.py", "function dep() {}\n")
    (tmp_path / "src" / "blob.py").write_bytes(b"def broken(): ...\n\x00\x00\x00")
    (tmp_path / ".code-review-graphignore").write_text("vendor/**\n", encoding="utf-8")

    adapter = BuiltinGraphAdapter(tmp_path)
    build = adapter.build_or_update(full=True)
    stats = adapter.stats()

    assert build["status"] == "ok"
    assert stats["files"] == 1
    assert build["languages"] == ["python"]

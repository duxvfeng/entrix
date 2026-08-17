"""Tests for entrix.structure.adapter."""

from pathlib import Path

from entrix.structure.adapter import CodeReviewGraphAdapter


class FakeTools:
    def __init__(self) -> None:
        self.calls = []

    def query_graph(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "ok"}


def test_adapter_query_uses_pattern_keyword():
    repo_root = Path("/tmp/repo")
    adapter = CodeReviewGraphAdapter(repo_root)
    fake_tools = FakeTools()
    adapter._tools = fake_tools

    result = adapter.query("tests_for", "foo.Bar.run")

    assert result == {"status": "ok"}
    assert fake_tools.calls == [
        {
            "pattern": "tests_for",
            "target": "foo.Bar.run",
            "repo_root": str(repo_root),
        }
    ]

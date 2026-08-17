"""Generic JSON and evidence/v1 parser tests."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from entrix.harness.conditions import WhenContext
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.parsers import get_parser
from entrix.harness.parsers.base import ParserContext
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.command import CommandProducer


def parse_with(parser_type: str, repo_root: Path, config: dict[str, object]):
    process = subprocess.CompletedProcess("test-command", 0, "", "")
    return get_parser(parser_type).parse(ParserContext(repo_root, config, process))


def test_json_parser_maps_status_and_summary(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        '{"result":{"status":"success"},"stats":{"total":4,"failed":0}}',
        encoding="utf-8",
    )
    config = {
        "type": "json",
        "path": "result.json",
        "status_path": "result.status",
        "status_map": {"success": "pass", "failed": "fail"},
        "summary": {"total": "stats.total", "failed": "stats.failed"},
    }

    result = parse_with("json", tmp_path, config)

    assert result.status == "pass"
    assert result.summary == {"total": 4, "failed": 0}
    assert [(artifact.type, artifact.path) for artifact in result.artifacts] == [
        ("json", "result.json")
    ]


def test_json_parser_reads_list_indexes(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        '{"runs":[{"status":"failed"}]}', encoding="utf-8"
    )

    result = parse_with(
        "json",
        tmp_path,
        {
            "path": "result.json",
            "status_path": "runs.0.status",
            "status_map": {"failed": "fail"},
            "summary": {},
        },
    )

    assert result.status == "fail"


def test_json_parser_missing_mapped_field_returns_error(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text("{}", encoding="utf-8")

    result = parse_with(
        "json",
        tmp_path,
        {"path": "result.json", "status_path": "result.status", "status_map": {}},
    )

    assert result.status == "error"
    assert "result.status" in str(result.raw["error"])


def test_json_parser_malformed_document_returns_error(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text("{", encoding="utf-8")

    result = parse_with(
        "json",
        tmp_path,
        {"path": "result.json", "status_path": "status", "status_map": {}},
    )

    assert result.status == "error"


@pytest.mark.parametrize("payload", ["[]", '"pass"'])
def test_json_parser_rejects_non_object_root(tmp_path: Path, payload: str) -> None:
    (tmp_path / "result.json").write_text(payload, encoding="utf-8")

    result = parse_with(
        "json",
        tmp_path,
        {"path": "result.json", "status_path": "status", "status_map": {}},
    )

    assert result.status == "error"
    assert "object" in str(result.raw["error"]).lower()


def test_json_parser_rejects_unmapped_status(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text('{"status":"unknown"}', encoding="utf-8")

    result = parse_with(
        "json",
        tmp_path,
        {"path": "result.json", "status_path": "status", "status_map": {}},
    )

    assert result.status == "error"
    assert "unknown" in str(result.raw["error"])


def test_evidence_json_cannot_override_harness_identity(tmp_path: Path) -> None:
    (tmp_path / "evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "evidence/v1",
                "id": "forged",
                "type": "forged",
                "producer": "forged",
                "task_id": "forged",
                "status": "pass",
                "summary": {"passed": 3},
                "artifacts": [],
                "raw": {"source": "trusted-tool"},
            }
        ),
        encoding="utf-8",
    )
    producer = CommandProducer(
        EvidenceProducerConfig(
            id="trusted-id",
            type="test",
            name="Trusted evidence",
            producer="trusted-producer",
            command="echo complete",
            parser={"type": "evidence_json", "path": "evidence.json"},
        )
    )
    context = ProducerContext(
        task_id="trusted-task",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    evidence = producer.run(context)

    assert evidence.id == "trusted-id"
    assert evidence.type == "test"
    assert evidence.producer == "trusted-producer"
    assert evidence.task_id == "trusted-task"
    assert evidence.status == "pass"
    assert evidence.summary == {"passed": 3}


def test_evidence_json_rejects_invalid_schema(tmp_path: Path) -> None:
    (tmp_path / "evidence.json").write_text(
        '{"schema_version":"evidence/v2","status":"pass"}', encoding="utf-8"
    )

    result = parse_with("evidence_json", tmp_path, {"path": "evidence.json"})

    assert result.status == "error"
    assert "schema_version" in str(result.raw["error"])


def test_evidence_json_normalizes_artifacts(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "details.txt").write_text("details", encoding="utf-8")
    (tmp_path / "evidence.json").write_text(
        json.dumps(
            {
                "schema_version": "evidence/v1",
                "status": "pass",
                "summary": {},
                "raw": {},
                "artifacts": [
                    {
                        "type": "log",
                        "path": "reports/details.txt",
                        "metadata": {"format": "text"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = parse_with("evidence_json", tmp_path, {"path": "evidence.json"})

    assert result.status == "pass"
    assert [(item.type, item.path) for item in result.artifacts] == [
        ("evidence_json", "evidence.json"),
        ("log", "reports/details.txt"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "evidence/v1", "status": "unknown"},
        {"schema_version": "evidence/v1", "status": "pass", "summary": []},
        {"schema_version": "evidence/v1", "status": "pass", "raw": []},
        {"schema_version": "evidence/v1", "status": "pass", "artifacts": {}},
    ],
)
def test_evidence_json_rejects_invalid_evidence_fields(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    (tmp_path / "evidence.json").write_text(json.dumps(payload), encoding="utf-8")

    result = parse_with("evidence_json", tmp_path, {"path": "evidence.json"})

    assert result.status == "error"

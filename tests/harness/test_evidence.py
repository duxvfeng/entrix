import dataclasses
import json

import pytest

from entrix.harness.evidence import Evidence, EvidenceBundle, Artifact


def test_evidence_dataclass_creation():
    """测试包含所有字段的 Evidence 数据类"""
    evidence = Evidence(
        id="test-1",
        type="test",
        name="单元测试",
        status="pass",
        producer="pytest",
        task_id="task-123",
        started_at="2026-08-16T10:30:00Z",
        duration_ms=1500,
        summary={"passed": 10, "failed": 0},
        artifacts=[Artifact(type="junit", path="junit.xml")],
        raw={"exit_code": 0}
    )

    assert evidence.id == "test-1"
    assert evidence.type == "test"
    assert evidence.status == "pass"
    assert evidence.summary["passed"] == 10
    assert len(evidence.artifacts) == 1


def test_evidence_defaults():
    """测试 Evidence 具有正确的默认值"""
    evidence = Evidence()

    assert evidence.schema_version == "evidence/v1"
    assert evidence.id == ""
    assert evidence.type == ""
    assert evidence.status == ""


def test_evidence_rejects_unknown_status() -> None:
    with pytest.raises(ValueError, match="status"):
        Evidence(id="tests", status="unknown")


def test_bundle_defaults_include_audit_metadata() -> None:
    bundle = EvidenceBundle(task_id="task", attempt_id="attempt")

    assert bundle.collected_at.endswith("Z")
    assert bundle.active is True
    assert bundle.revision == ""
    assert bundle.workspace_fingerprint == ""


def test_evidence_bundle_creation():
    """测试包含多个证据项的 EvidenceBundle"""
    bundle = EvidenceBundle(
        task_id="task-123",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:35:00Z",
        evidence=[
            Evidence(id="test-1", type="test", name="测试"),
            Evidence(id="lint-1", type="lint", name="代码检查")
        ],
        collection_errors=[]
    )

    assert bundle.schema_version == "evidence-bundle/v1"
    assert len(bundle.evidence) == 2
    assert bundle.task_id == "task-123"


def test_evidence_bundle_serialization():
    """测试 EvidenceBundle 可以序列化为 JSON"""
    bundle = EvidenceBundle(
        task_id="task-123",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:35:00Z",
        evidence=[Evidence(id="test-1", type="test", name="测试")]
    )

    # 应该可以 JSON 序列化
    json_str = json.dumps(dataclasses.asdict(bundle))
    assert "task-123" in json_str

    # 应该反序列化回来
    data = json.loads(json_str)
    assert data["task_id"] == "task-123"

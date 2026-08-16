"""EvidenceStore persistence layer tests."""
from pathlib import Path

from entrix.harness.evidence import Artifact, Evidence, EvidenceBundle
from entrix.harness.store import EvidenceStore


def test_save_evidence_bundle(tmp_path: Path) -> None:
    """Saving a bundle creates a JSON file under the task directory."""
    bundle = EvidenceBundle(
        task_id="test-task",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:00:00Z",
        evidence=[Evidence(id="test-1", type="test", name="测试", status="pass")],
    )

    store = EvidenceStore(root_dir=tmp_path)
    saved_path = store.save(bundle)

    assert saved_path.exists()
    assert saved_path.name.endswith("-bundle.json")
    assert saved_path.relative_to(tmp_path)
    assert ".harness" in str(saved_path)
    assert "evidence" in str(saved_path)
    assert "test-task" in str(saved_path)


def test_load_evidence_bundle(tmp_path: Path) -> None:
    """A saved bundle can be loaded back with identical data and types."""
    bundle = EvidenceBundle(
        task_id="test-task",
        attempt_id="attempt-1",
        collected_at="2026-08-16T10:00:00Z",
        evidence=[
            Evidence(
                id="test-1",
                type="test",
                name="测试",
                status="pass",
                artifacts=[Artifact(type="junit", path="junit.xml")],
                raw={"exit_code": 0},
            )
        ],
    )

    store = EvidenceStore(root_dir=tmp_path)
    saved_path = store.save(bundle)

    loaded_bundle = store.load(saved_path)

    assert loaded_bundle is not None
    assert loaded_bundle.task_id == bundle.task_id
    assert loaded_bundle.attempt_id == bundle.attempt_id
    assert loaded_bundle.collected_at == bundle.collected_at
    assert len(loaded_bundle.evidence) == 1
    assert loaded_bundle.evidence[0].id == "test-1"
    assert loaded_bundle.evidence[0].type == "test"
    assert loaded_bundle.evidence[0].status == "pass"
    assert isinstance(loaded_bundle.evidence[0], Evidence)
    assert len(loaded_bundle.evidence[0].artifacts) == 1
    assert isinstance(loaded_bundle.evidence[0].artifacts[0], Artifact)
    assert loaded_bundle.evidence[0].artifacts[0].type == "junit"


def test_save_creates_task_directory(tmp_path: Path) -> None:
    """Saving creates the task-specific evidence directory automatically."""
    bundle = EvidenceBundle(task_id="test-task-123", attempt_id="attempt-1", evidence=[])

    store = EvidenceStore(root_dir=tmp_path)
    saved_path = store.save(bundle)

    assert "test-task-123" in str(saved_path)
    assert saved_path.parent.exists()


def test_save_multiple_bundles_same_task(tmp_path: Path) -> None:
    """Multiple saves for the same task create distinct files."""
    bundle1 = EvidenceBundle(task_id="task-1", evidence=[])
    bundle2 = EvidenceBundle(task_id="task-1", evidence=[])

    store = EvidenceStore(root_dir=tmp_path)
    path1 = store.save(bundle1)
    path2 = store.save(bundle2)

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()


def test_save_uses_explicit_task_id(tmp_path: Path) -> None:
    """An explicit task_id parameter overrides the bundle's own task_id."""
    bundle = EvidenceBundle(task_id="bundle-task", evidence=[])

    store = EvidenceStore(root_dir=tmp_path)
    saved_path = store.save(bundle, task_id="explicit-task")

    assert "explicit-task" in str(saved_path)
    assert "bundle-task" not in str(saved_path)


def test_load_missing_file_returns_none(tmp_path: Path) -> None:
    """Loading a non-existent file returns None instead of raising."""
    store = EvidenceStore(root_dir=tmp_path)
    result = store.load(tmp_path / "missing" / "bundle.json")

    assert result is None


def test_load_corrupt_json_returns_none(tmp_path: Path) -> None:
    """Loading a malformed JSON file returns None."""
    bad_file = tmp_path / "bad-bundle.json"
    bad_file.write_text("not json")

    store = EvidenceStore(root_dir=tmp_path)
    result = store.load(bad_file)

    assert result is None

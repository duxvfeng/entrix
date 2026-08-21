"""Evidence collection engine tests."""
from pathlib import Path
from threading import Event, Lock

import pytest

from entrix.harness.conditions import WhenContext
from entrix.harness.config import EvidenceProducerConfig, HarnessConfig
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.store import EvidenceStore
from entrix.model import Dimension, Metric
from entrix.review_trigger import ReviewTriggerRule


def test_collect_evidence_with_command_producer():
    """测试使用命令生产者收集证据"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试生产者",
                command="echo 'passed=10, failed=0'",
                producer="test",
                parser={"type": "regex", "pattern": r"passed=(?P<passed>\d+), failed=(?P<failed>\d+)"},
            )
        ],
        gate_policies=[],
    )

    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd()),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    assert bundle.task_id == "task-1"
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "test-1"
    assert bundle.evidence[0].status == "pass"


def test_collect_with_global_when_filter(tmp_path):
    """测试带有全局 when 条件的证据收集"""
    # 创建存在的临时文件
    temp_file = tmp_path / "test_marker.txt"
    temp_file.write_text("marker", encoding="utf-8")

    config = HarnessConfig(
        version="harness/v1",
        when={"files_exist": [temp_file.name]},
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试",
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"},
            )
        ],
        gate_policies=[],
    )

    context = HarnessRunContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    # 应该执行，因为全局 when 条件满足
    assert len(bundle.evidence) == 1


def test_collect_with_producer_when_filter(tmp_path):
    """测试带有生产者特定 when 条件的证据收集"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试",
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"},
                when={"files_exist": ["does_not_exist.txt"]},  # 应该跳过
            ),
            EvidenceProducerConfig(
                id="test-2",
                type="test",
                name="测试 2",
                command="echo 'test2'",
                producer="test",
                parser={"type": "exit_code"},  # 没有 when 条件 - 应该运行
            ),
        ],
        gate_policies=[],
    )

    context = HarnessRunContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    evidence_by_id = {item.id: item for item in bundle.evidence}
    assert set(evidence_by_id) == {"test-1", "test-2"}
    assert evidence_by_id["test-1"].status == "skipped"
    assert evidence_by_id["test-1"].raw == {"reason": "when condition not met"}
    assert evidence_by_id["test-2"].status == "pass"


def test_inactive_harness_saves_inactive_bundle_without_running_producer(
    tmp_path: Path,
) -> None:
    config = HarnessConfig(
        version="harness/v1",
        when={"changed_any": ["frontend/**"]},
        evidence_producers=[
            EvidenceProducerConfig(
                id="tests",
                type="test",
                name="Tests",
                command="pytest",
            )
        ],
        gate_policies=[],
    )
    store = EvidenceStore(tmp_path / "runtime")
    engine = EvidenceEngine(config)
    engine._create_producer = lambda _config: pytest.fail("producer must not run")
    context = HarnessRunContext(
        task_id="task-1",
        attempt_id="attempt-1",
        repo_root=tmp_path,
        when_context=WhenContext(
            repo_root=tmp_path,
            changed_files=["docs/readme.md"],
        ),
        store=store,
    )

    bundle = engine.collect(context)

    assert bundle.active is False
    assert bundle.evidence == []
    assert bundle.collection_errors == []
    assert list((store.evidence_dir / "task-1").glob("*-bundle.json"))


def test_collect_propagates_storage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="tests", type="test", name="Tests", command="echo passed"
            )
        ],
        gate_policies=[],
    )
    store = EvidenceStore(tmp_path / "runtime")
    monkeypatch.setattr(
        store,
        "save",
        lambda _bundle: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    context = HarnessRunContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
        store=store,
        parallel_producers=False,
    )

    with pytest.raises(OSError, match="disk unavailable"):
        EvidenceEngine(config).collect(context)


def test_collect_with_builtin_producer():
    """测试使用内置生产者收集证据"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(id="diff-1", type="diff", name="差异统计", builtin="diff-stats"),
        ],
        gate_policies=[],
    )

    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd(), changed_files=["README.md", "src/main.py"]),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "diff-1"
    assert bundle.evidence[0].type == "diff"


def test_create_builtin_producers_injects_inline_harness_rules():
    """EvidenceEngine passes parsed Harness rules to builtin producers."""
    dimensions = [Dimension(name="quality", weight=100, metrics=[Metric(name="lint", command="true")])]
    rules = [ReviewTriggerRule(name="sensitive", type="sensitive_file_change")]
    config = HarnessConfig(
        version="harness/v1",
        fitness_dimensions=dimensions,
        review_trigger_rules=rules,
        gate_policies=[],
    )
    engine = EvidenceEngine(config)

    fitness = engine._create_producer(
        EvidenceProducerConfig(id="fitness", type="fitness", name="Fitness", builtin="entrix-fitness")
    )
    review = engine._create_producer(
        EvidenceProducerConfig(
            id="review", type="review-trigger", name="Review", builtin="entrix-review-trigger"
        )
    )

    assert fitness.dimensions == dimensions
    assert review.rules == rules


def test_collect_handles_producer_errors():
    """测试生产者错误不阻止收集"""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="failing-1",
                type="test",
                name="失败测试",
                command="exit 1",
                producer="test",
                parser={"type": "exit_code"},
            ),
            EvidenceProducerConfig(
                id="passing-1",
                type="test",
                name="通过测试",
                command="echo 'success'",
                producer="test",
                parser={"type": "exit_code"},
            ),
        ],
        gate_policies=[],
    )

    context = HarnessRunContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd()),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    # 应该收集两个证据
    assert len(bundle.evidence) == 2

    # 检查有一个失败和一个通过，不管顺序
    statuses = {e.status for e in bundle.evidence}
    assert "fail" in statuses
    assert "pass" in statuses


def test_collect_with_storage():
    """测试带存储的证据收集"""
    from tempfile import TemporaryDirectory

    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(
                id="test-1",
                type="test",
                name="测试",
                command="echo 'test'",
                producer="test",
                parser={"type": "exit_code"},
            )
        ],
        gate_policies=[],
    )

    with TemporaryDirectory() as tmpdir:
        context = HarnessRunContext(
            task_id="task-1",
            repo_root=Path.cwd(),
            when_context=WhenContext(repo_root=Path.cwd()),
            store=EvidenceStore(Path(tmpdir)),
        )

        engine = EvidenceEngine(config)
        bundle = engine.collect(context)

        # 应该保存包
        assert bundle.task_id == "task-1"
        assert len(bundle.evidence) == 1

        # 验证文件已创建
        evidence_dir = Path(tmpdir) / ".harness" / "evidence" / "task-1"
        assert evidence_dir.exists()
        assert len(list(evidence_dir.glob("*.json"))) == 1


def test_collect_defaults_to_serial_producer_execution(tmp_path):
    """Manual collection must not start independent heavy producers by default."""
    config = HarnessConfig(
        version="harness/v1",
        evidence_producers=[
            EvidenceProducerConfig(id="first", type="test", name="first", command="true"),
            EvidenceProducerConfig(id="second", type="test", name="second", command="true"),
        ],
        gate_policies=[],
    )
    started = Event()
    release = Event()
    lock = Lock()
    active = 0
    max_active = 0

    class Producer:
        def __init__(self, producer_id: str) -> None:
            self.producer_id = producer_id

        def run(self, _context):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            if self.producer_id == "first":
                started.set()
                release.wait(timeout=1)
            else:
                started.wait(timeout=1)
                release.set()
            with lock:
                active -= 1
            return type("Evidence", (), {"id": self.producer_id})()

    engine = EvidenceEngine(config)
    engine._create_producer = lambda producer_config: Producer(producer_config.id)
    context = HarnessRunContext(
        task_id="stop-gate",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    bundle = engine.collect(context)

    assert [evidence.id for evidence in bundle.evidence] == ["first", "second"]
    assert max_active == 1


def test_collect_caps_parallel_producers_at_configured_limit(tmp_path):
    """An explicit parallel request must never exceed the YAML producer cap."""
    config = HarnessConfig(
        version="harness/v1",
        max_parallel_producers=2,
        evidence_producers=[
            EvidenceProducerConfig(id="first", type="test", name="first", command="true"),
            EvidenceProducerConfig(id="second", type="test", name="second", command="true"),
            EvidenceProducerConfig(id="third", type="test", name="third", command="true"),
        ],
        gate_policies=[],
    )
    release = Event()
    lock = Lock()
    active = 0
    max_active = 0

    class Producer:
        def __init__(self, producer_id: str) -> None:
            self.producer_id = producer_id

        def run(self, _context):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            release.wait(timeout=0.1)
            with lock:
                active -= 1
            return type("Evidence", (), {"id": self.producer_id})()

    engine = EvidenceEngine(config)
    engine._create_producer = lambda producer_config: Producer(producer_config.id)
    context = HarnessRunContext(
        task_id="manual-run",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
        parallel_producers=True,
        max_parallel_producers=4,
    )

    bundle = engine.collect(context)

    assert len(bundle.evidence) == 3
    assert max_active == 2

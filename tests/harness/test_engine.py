"""Evidence collection engine tests."""
import pytest
from pathlib import Path
from entrix.harness.engine import EvidenceEngine, HarnessRunContext
from entrix.harness.config import HarnessConfig, EvidenceProducerConfig
from entrix.harness.conditions import WhenContext
from entrix.harness.store import EvidenceStore


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


def test_collect_with_global_when_filter():
    """测试带有全局 when 条件的证据收集"""
    import tempfile

    # 创建存在的临时文件
    temp_file = Path("/tmp/test_marker.txt")
    temp_file.write_text("marker")

    config = HarnessConfig(
        version="harness/v1",
        when={"files_exist": ["/tmp/test_marker.txt"]},
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
        repo_root=Path("/tmp"),
        when_context=WhenContext(repo_root=Path("/tmp")),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    # 应该执行，因为全局 when 条件满足
    assert len(bundle.evidence) == 1


def test_collect_with_producer_when_filter():
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
                when={"files_exist": ["/tmp/does_not_exist.txt"]},  # 应该跳过
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
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd()),
    )

    engine = EvidenceEngine(config)
    bundle = engine.collect(context)

    # 应该只执行 test-2
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].id == "test-2"


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
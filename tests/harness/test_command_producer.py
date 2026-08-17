"""CommandProducer execution tests."""
import sys
import subprocess

from pathlib import Path
from entrix.harness.producers.base import ProducerContext
from entrix.harness.producers.command import CommandProducer
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.conditions import WhenContext
import entrix.harness.producers.command as command_module


def test_command_producer_exit_code_success():
    """测试 exit_code 解析器在成功时的命令生产者"""
    config = EvidenceProducerConfig(
        id="test-success",
        type="test",
        name="退出码测试",
        command="echo 'test'",
        producer="test",
        parser={"type": "exit_code"}
    )

    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )

    evidence = producer.run(context)

    assert evidence.id == "test-success"
    assert evidence.status == "pass"
    assert evidence.producer == "test"


def test_command_producer_exit_code_failure():
    """测试 exit_code 解析器在失败时的命令生产者"""
    config = EvidenceProducerConfig(
        id="test-fail",
        type="test",
        name="失败测试",
        command="exit 1",
        producer="test",
        parser={"type": "exit_code"}
    )

    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )

    evidence = producer.run(context)

    assert evidence.status == "fail"


def test_command_producer_regex_parser():
    """测试 regex 解析器的命令生产者"""
    config = EvidenceProducerConfig(
        id="regex-test",
        type="test",
        name="正则测试",
        command='echo "passed=10, failed=2"',
        producer="test",
        parser={"type": "regex", "pattern": r'passed=(?P<passed>\d+), failed=(?P<failed>\d+)'}
    )

    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )

    evidence = producer.run(context)

    assert evidence.status == "pass"
    assert evidence.summary["passed"] == 10
    assert evidence.summary["failed"] == 2


def test_command_producer_timeout():
    """测试命令生产者超时处理"""
    config = EvidenceProducerConfig(
        id="timeout-test",
        type="test",
        name="超时测试",
        command=f'"{sys.executable}" -c "import time; time.sleep(10)"',
        producer="test",
        timeout_seconds=1,
        parser={"type": "exit_code"}
    )

    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )

    evidence = producer.run(context)

    assert evidence.status == "timeout"


def test_command_producer_timeout_terminates_process_tree(tmp_path, monkeypatch):
    config = EvidenceProducerConfig(
        id="timeout-test",
        type="test",
        name="Timeout",
        command="slow-command",
        producer="test",
        timeout_seconds=1,
        parser={"type": "exit_code"},
    )
    process = type("Process", (), {"pid": 12345, "returncode": None})()

    def communicate(timeout=None):
        if timeout is not None:
            raise subprocess.TimeoutExpired("slow-command", timeout)
        return "", ""

    process.communicate = communicate
    process.kill = lambda: None
    terminated = []
    monkeypatch.setattr(command_module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        command_module,
        "terminate_process_tree",
        lambda candidate: terminated.append(candidate),
    )
    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    evidence = CommandProducer(config).run(context)

    assert evidence.status == "timeout"
    assert terminated == [process]


def test_command_producer_regex_parse_error():
    """测试正则解析失败处理"""
    config = EvidenceProducerConfig(
        id="regex-error",
        type="test",
        name="正则错误测试",
        command='echo "no match here"',
        producer="test",
        parser={"type": "regex", "pattern": r'passed=(?P<passed>\d+)'}
    )

    producer = CommandProducer(config)
    context = ProducerContext(
        task_id="task-1",
        repo_root=Path.cwd(),
        when_context=WhenContext(repo_root=Path.cwd())
    )

    evidence = producer.run(context)

    assert evidence.status == "error"
    assert "regex" in str(evidence.raw.get("error", "")).lower()


def test_command_producer_attaches_declared_artifacts(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text("<testsuite />", encoding="utf-8")
    config = EvidenceProducerConfig(
        id="artifact-test",
        type="test",
        name="Artifact test",
        command="echo passed",
        parser={"type": "exit_code"},
        artifacts=[{"type": "junit", "path": "report.xml"}],
    )
    context = ProducerContext(
        task_id="task-1",
        repo_root=tmp_path,
        when_context=WhenContext(repo_root=tmp_path),
    )

    evidence = CommandProducer(config).run(context)

    assert [(artifact.type, artifact.path) for artifact in evidence.artifacts] == [
        ("junit", "report.xml")
    ]

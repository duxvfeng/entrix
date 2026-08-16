"""CommandProducer execution tests."""
import pytest
from pathlib import Path
from entrix.harness.producers.base import Producer, ProducerContext
from entrix.harness.producers.command import CommandProducer
from entrix.harness.config import EvidenceProducerConfig
from entrix.harness.conditions import WhenContext


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
    assert evidence.summary["passed"] == "10"
    assert evidence.summary["failed"] == "2"


def test_command_producer_timeout():
    """测试命令生产者超时处理"""
    config = EvidenceProducerConfig(
        id="timeout-test",
        type="test",
        name="超时测试",
        command="sleep 10",
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
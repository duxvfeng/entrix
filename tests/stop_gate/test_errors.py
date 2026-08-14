from entrix.stop_gate.errors import (
    ConfigurationError,
    EvidenceCollectionError,
    ExecutionError,
    FitnessCheckError,
    RecoverableError,
    StopGateError,
    SystemError,
    TimeoutError,
)


def test_stop_gate_error_base():
    """测试基础错误类"""
    error = StopGateError("Test error", recoverable=True)
    assert error.message == "Test error"
    assert error.recoverable is True
    assert error.timestamp is not None


def test_system_error_not_recoverable():
    """测试系统错误默认不可恢复"""
    error = SystemError("System failure")
    assert error.recoverable is False


def test_execution_error_with_details():
    """测试执行错误包含详细信息"""
    error = FitnessCheckError("pytest_pass", 1, "Test failed")
    assert error.metric_name == "pytest_pass"
    assert error.exit_code == 1
    assert "Test failed" in error.output


def test_timeout_error():
    """测试超时错误"""
    error = TimeoutError("fitness_check", 300)
    assert error.operation == "fitness_check"
    assert error.timeout_seconds == 300


def test_configuration_error_not_recoverable():
    """测试配置错误不可恢复"""
    error = ConfigurationError("Bad config")
    assert error.recoverable is False


def test_recoverable_error_recoverable():
    """测试可恢复错误默认可恢复"""
    error = RecoverableError("Retry later")
    assert error.recoverable is True


def test_evidence_collection_error_is_execution_error():
    """测试证据收集错误是执行错误子类"""
    error = EvidenceCollectionError("environment", "git failed")
    assert isinstance(error, ExecutionError)
    assert "git failed" in error.message

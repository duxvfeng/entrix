"""Tests for the shared exception hierarchy."""

import pytest

from entrix.errors import ConfigError, EntrexError
from entrix.harness.config import load_harness_config
from entrix.harness.profiles import ProfileDetectionError


def test_config_error_is_compatible_with_value_error_handlers():
    assert issubclass(ConfigError, EntrexError)
    assert issubclass(ConfigError, ValueError)
    assert issubclass(ProfileDetectionError, ConfigError)


def test_harness_config_validation_raises_config_error(tmp_path):
    config_path = tmp_path / "harness.yaml"
    config_path.write_text("settings: {}\n", encoding="utf-8")

    with pytest.raises(ConfigError) as config_error:
        load_harness_config(config_path)

    # 历史调用点按 ValueError 捕获的契约不被破坏
    with pytest.raises(ValueError):
        raise config_error.value

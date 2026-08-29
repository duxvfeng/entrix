"""环境变量读取的兼容层：ENTRIX_* 为规范前缀，历史 ROUTA_* 前缀继续生效。"""

from __future__ import annotations

import os

CANONICAL_PREFIX = "ENTRIX_"
LEGACY_PREFIX = "ROUTA_"


def env_setting(name: str, default: str | None = None) -> str | None:
    """读取 ``ENTRIX_<name>``；未设置时回退到历史 ``ROUTA_<name>``，再回退到默认值。"""
    value = os.environ.get(f"{CANONICAL_PREFIX}{name}")
    if value is None:
        value = os.environ.get(f"{LEGACY_PREFIX}{name}")
    return default if value is None else value

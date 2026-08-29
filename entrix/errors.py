"""Entrix 异常体系。

让调用方能程序化地区分配置错误与基础设施故障：CLI、Stop Gate 和 MCP
入口目前对同类失败暴露不同的容错行为，共享的异常类型是统一这些契约的
前置条件。
"""

from __future__ import annotations


class EntrexError(Exception):
    """Entrix 所有自定义异常的基类。"""


class ConfigError(EntrexError, ValueError):
    """Harness / review-trigger 配置加载或校验失败。

    继承 ``ValueError`` 以保持与既有调用点 ``except ValueError`` 的兼容。
    """

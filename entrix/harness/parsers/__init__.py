"""Controlled evidence parser registry."""
from __future__ import annotations

from entrix.harness.parsers.base import EvidenceParser
from entrix.harness.parsers.evidence_json import EvidenceJsonParser
from entrix.harness.parsers.json_report import JsonReportParser
from entrix.harness.parsers.junit import JUnitParser
from entrix.harness.parsers.process import ExitCodeParser, RegexParser
from entrix.harness.parsers.sarif import SarifParser

_PARSERS: dict[str, EvidenceParser] = {
    "exit_code": ExitCodeParser(),
    "regex": RegexParser(),
    "junit": JUnitParser(),
    "json": JsonReportParser(),
    "evidence_json": EvidenceJsonParser(),
    "sarif": SarifParser(),
}


def get_parser(parser_type: str) -> EvidenceParser:
    """Return one registered parser or reject unknown executable behavior."""
    try:
        return _PARSERS[parser_type]
    except KeyError as error:
        raise ValueError(f"不支持的 parser type：{parser_type}") from error


__all__ = ["get_parser"]

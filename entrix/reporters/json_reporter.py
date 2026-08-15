"""JSON reporter — 为 CI pipelines 提供机器可读的输出。"""

from __future__ import annotations

import sys

from entrix.model import FitnessReport
from entrix.reporting import report_to_dict


class JsonReporter:
    """将 fitness report 以 JSON 格式输出到 stdout 或文件。"""

    def report(self, report: FitnessReport, *, file=None) -> None:
        """将 fitness report 序列化为 JSON。

        Args:
            report: 要序列化的 fitness report。
            file: 要写入的类文件对象（默认为 stdout）。
        """
        out = file or sys.stdout
        import json

        json.dump(report_to_dict(report), out, indent=2, ensure_ascii=False)
        out.write("\n")

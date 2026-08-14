"""Feedback Formatter - 生成 Claude 可执行的反馈"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from entrix.stop_gate.model import Verdict


@dataclass
class FormattedFeedback:
    """格式化后的反馈"""

    user_readable: str  # Markdown 格式，用户可读
    structured: dict  # JSON 格式，机器可解析
    artifact_path: Path | None = None


class FeedbackFormatter:
    """将裁决结果转换为 Claude 可执行的反馈格式"""

    def __init__(self, output_dir: Path | None = None):
        if output_dir is None:
            output_dir = Path.cwd() / ".claude" / "stop-gate" / "feedback"
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def format_feedback(self, verdict: Verdict) -> FormattedFeedback:
        """格式化裁决结果为混合格式"""
        # 生成用户可读的 Markdown
        user_readable = self._format_markdown(verdict)

        # 生成结构化 JSON
        structured = self._format_structured(verdict)

        # 保存 artifact
        artifact_path = self._save_artifact(verdict, user_readable, structured)

        return FormattedFeedback(
            user_readable=user_readable,
            structured=structured,
            artifact_path=artifact_path,
        )

    def _format_markdown(self, verdict: Verdict) -> str:
        """生成 Markdown 格式反馈"""
        if verdict.verdict == "PASS":
            return self._pass_markdown(verdict)
        if verdict.verdict == "FAIL":
            return self._fail_markdown(verdict)
        return self._blocked_markdown(verdict)

    def _pass_markdown(self, verdict: Verdict) -> str:
        """生成通过场景的 Markdown"""
        return f"""✅ 质量门禁检查通过

{verdict.summary}

**检查结果:**
- 所有必需质量检查已通过
- 无硬门禁失败
- 无人工审查要求

🎉 可以安全结束任务。

---
*Attempt ID: {verdict.attempt_id}*
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*"""

    def _fail_markdown(self, verdict: Verdict) -> str:
        """生成失败场景的 Markdown"""
        findings_text = ""

        if verdict.findings:
            for i, finding in enumerate(verdict.findings, 1):
                severity_icon = "🔴" if finding.severity == "hard_gate" else "🟡"
                findings_text += f"""
{severity_icon} **发现 {i}: {finding.source}.{finding.metric}**
   - 严重级别: {finding.severity}
   - 问题: {finding.message}
"""

        return f"""❌ {verdict.summary}

## 失败详情
{findings_text if findings_text else "_详细信息请查看 artifact_"}

## 建议修复步骤
1. 根据上述失败项进行修复
2. 运行对应检查验证修复效果
3. 确认所有检查通过后再次请求 stop

🔄 下一步: 修复问题后再次请求 stop，系统将重新检查

---
*Attempt ID: {verdict.attempt_id}*
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*
*状态: 需要修复后重试*"""

    def _blocked_markdown(self, verdict: Verdict) -> str:
        """生成阻塞场景的 Markdown"""
        return f"""🚫 {verdict.summary}

## 阻塞原因
{verdict.reason}

## 需要的干预
此情况需要人工干预或环境修复后才能继续。

🚨 **系统状态: BLOCKED**
📋 建议检查系统状态或联系支持

---
*Attempt ID: {verdict.attempt_id}*
*检查时间: {verdict.decided_at.strftime('%Y-%m-%d %H:%M:%S')} UTC*"""

    def _format_structured(self, verdict: Verdict) -> dict:
        """生成结构化 JSON 格式"""
        structured = {
            "schema_version": "gate-feedback.v1",
            "attempt_id": verdict.attempt_id,
            "verdict": verdict.verdict,
            "decided_at": verdict.decided_at.isoformat(),
            "summary": verdict.summary,
            "reason": verdict.reason,
            "block_termination": verdict.verdict != "PASS",
            "next_action": self._get_next_action(verdict.verdict),
        }

        if verdict.findings:
            structured["findings"] = [
                {
                    "source": finding.source,
                    "metric": finding.metric,
                    "severity": finding.severity,
                    "message": finding.message,
                    "suggestions": finding.suggestions,
                }
                for finding in verdict.findings
            ]

        return structured

    def _get_next_action(self, verdict: str) -> str:
        """获取下一步行动指导"""
        actions = {
            "PASS": "allow_stop",
            "FAIL": "fix_issues_and_retry",
            "BLOCKED": "manual_intervention",
        }
        return actions.get(verdict, "unknown")

    def _save_artifact(self, verdict: Verdict, markdown: str, structured: dict) -> Path:
        """保存反馈 artifact"""
        artifact_file = self.output_dir / f"{verdict.attempt_id}.md"

        # 保存 Markdown 版本
        artifact_file.write_text(markdown, encoding="utf-8")

        # 同时保存 JSON 版本
        json_file = self.output_dir / f"{verdict.attempt_id}.json"
        json_file.write_text(json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")

        return artifact_file

"""纯格式化:终端展示与 Markdown 导出,不访问文件/模型。"""

from __future__ import annotations

from datetime import datetime, timezone

from prompt_gen.domain.models import OptimizationRecord


def _as_utc(value: datetime) -> datetime:
    """排序/展示前统一为 aware UTC,避免 naive/aware 混比崩溃。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _truncate(text: str, max_len: int) -> str:
    """单行预览,超长用省略号截断。"""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_history_rows(
    items: list[OptimizationRecord],
) -> list[tuple[str, str, str, str]]:
    """返回 (id, raw_preview, optimized_preview, created_at) 行,供 Rich Table 使用。"""
    rows: list[tuple[str, str, str, str]] = []
    for record in items:
        ts = _as_utc(record.created_at).strftime("%Y-%m-%d %H:%M")
        raw_preview = _truncate(record.raw_prompt, 40)
        opt_preview = _truncate(record.optimized_prompt, 40)
        rows.append((record.id, raw_preview, opt_preview, ts))
    return rows


def format_export_markdown(record: OptimizationRecord) -> str:
    """导出为对话式 Markdown:原始 / 优化后 / 说明。"""
    ts = _as_utc(record.created_at).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        f"# 提示词优化记录 {record.id}",
        "",
        "## 元信息",
        "",
        f"- id: `{record.id}`",
        f"- created_at: {ts}",
    ]
    if record.model:
        lines.append(f"- model: {record.model}")
    lines.extend(
        [
            "",
            "## 原始提示词",
            "",
            record.raw_prompt,
            "",
            "## 优化后提示词",
            "",
            record.optimized_prompt,
        ]
    )
    if record.rationale:
        lines.extend(
            [
                "",
                "## 优化说明",
                "",
                record.rationale,
            ]
        )
    lines.append("")
    return "\n".join(lines)

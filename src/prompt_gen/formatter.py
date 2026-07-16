"""纯格式化：终端展示与 Markdown 导出，不访问文件/模型。"""

from __future__ import annotations

from datetime import datetime, timezone

from prompt_gen.models import StoredPrompt


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_list_line(stored: StoredPrompt) -> str:
    ts = _as_utc(stored.created_at).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{stored.id}  {stored.template.name}  {ts}"


def format_list_rows(items: list[StoredPrompt]) -> list[tuple[str, str, str]]:
    """返回 (id, name, created_at) 行，供 Rich Table 使用。"""
    return [
        (
            stored.id,
            stored.template.name,
            _as_utc(stored.created_at).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        for stored in items
    ]


def format_export_markdown(stored: StoredPrompt) -> str:
    template = stored.template
    source = stored.source
    audience = source.audience or "（未指定）"
    constraints = ", ".join(source.constraints) if source.constraints else "（无）"
    lines = [
        f"# {template.name}",
        "",
        "## Meta",
        "",
        f"- id: `{stored.id}`",
        f"- created_at: {_as_utc(stored.created_at).isoformat()}",
        f"- scenario: {source.scenario}",
        f"- goal: {source.goal}",
        f"- audience: {audience}",
        f"- constraints: {constraints}",
        f"- language: {source.language}",
        "",
        "## System Prompt",
        "",
        template.system_prompt,
        "",
        "## User Prompt Template",
        "",
        template.user_prompt_template,
        "",
        "## Variables",
        "",
    ]
    if template.variables:
        lines.extend(f"- {name}" for name in template.variables)
    else:
        lines.append("- （无）")
    if template.notes:
        lines.extend(["", "## Notes", "", template.notes])
    lines.append("")
    return "\n".join(lines)


def format_detail_text(stored: StoredPrompt) -> str:
    """详情展示与导出共用同一 Markdown 结构。"""
    return format_export_markdown(stored)

"""格式化与导出测试。"""

from datetime import datetime, timezone

from prompt_gen.formatter import (
    format_export_markdown,
    format_list_line,
    format_list_rows,
)
from prompt_gen.models import PromptRequest, PromptTemplate, StoredPrompt


def _stored(*, notes: str | None) -> StoredPrompt:
    return StoredPrompt(
        id="abcdef123456",
        created_at=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        source=PromptRequest(scenario="学习笔记", goal="提炼要点"),
        template=PromptTemplate(
            name="笔记总结",
            system_prompt="你是学习助手。",
            user_prompt_template="总结笔记：\n{notes_text}",
            variables=["notes_text"],
            notes=notes,
        ),
    )


def test_export_contains_sections() -> None:
    md = format_export_markdown(_stored(notes="先列要点"))
    assert "# 笔记总结" in md
    assert "## Meta" in md
    assert "scenario: 学习笔记" in md
    assert "## System Prompt" in md
    assert "## User Prompt Template" in md
    assert "## Variables" in md
    assert "- notes_text" in md
    assert "## Notes" in md
    assert "先列要点" in md


def test_export_omits_empty_notes_section() -> None:
    md = format_export_markdown(_stored(notes=None))
    assert "## Notes" not in md


def test_list_line() -> None:
    line = format_list_line(_stored(notes=None))
    assert "abcdef123456" in line
    assert "笔记总结" in line
    assert "UTC" in line


def test_list_rows() -> None:
    rows = format_list_rows([_stored(notes=None)])
    assert rows == [("abcdef123456", "笔记总结", "2026-07-13 12:00:00 UTC")]

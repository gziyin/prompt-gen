"""formatter 测试:历史列表行与 Markdown 导出。"""

from __future__ import annotations

from datetime import datetime, timezone

from prompt_gen.domain.models import OptimizationRecord
from prompt_gen.formatter import format_export_markdown, format_history_rows


def _record(**overrides) -> OptimizationRecord:
    defaults = {
        "id": "abcdef123456",
        "created_at": datetime(2026, 7, 19, 8, 0, tzinfo=timezone.utc),
        "raw_prompt": "原始提示词",
        "optimized_prompt": "优化后提示词",
        "rationale": "补了角色",
        "model": "deepseek-v4-flash",
    }
    defaults.update(overrides)
    return OptimizationRecord(**defaults)


def test_format_history_rows_returns_tuples() -> None:
    items = [_record(), _record(id="9876543210ab")]
    rows = format_history_rows(items)
    assert len(rows) == 2
    assert rows[0][0] == "abcdef123456"
    assert rows[0][1] == "原始提示词"
    assert rows[0][2] == "优化后提示词"
    assert "2026" in rows[0][3]


def test_format_history_rows_truncates_long_prompts() -> None:
    long_text = "x" * 100
    items = [_record(raw_prompt=long_text, optimized_prompt=long_text)]
    rows = format_history_rows(items, preview_width=40)
    assert len(rows[0][1]) <= 40
    assert "…" in rows[0][1]


def test_format_export_markdown_contains_all_sections() -> None:
    record = _record()
    md = format_export_markdown(record)
    assert "# 提示词优化记录 abcdef123456" in md
    assert "## 原始提示词" in md
    assert "原始提示词" in md
    assert "## 优化后提示词" in md
    assert "优化后提示词" in md
    assert "## 优化说明" in md
    assert "补了角色" in md
    assert "deepseek-v4-flash" in md


def test_format_export_markdown_omits_rationale_section_when_none() -> None:
    record = _record(rationale=None)
    md = format_export_markdown(record)
    assert "## 优化说明" not in md


def test_format_export_markdown_omits_model_when_none() -> None:
    record = _record(model=None)
    md = format_export_markdown(record)
    assert "model:" not in md

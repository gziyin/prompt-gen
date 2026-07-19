"""OptimizationRecord 领域模型测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from prompt_gen.domain.models import OptimizationRecord


def _valid_record(**overrides) -> OptimizationRecord:
    defaults = {
        "id": "abcdef123456",
        "created_at": "2026-07-19T08:00:00Z",
        "raw_prompt": "帮我写代码",
        "optimized_prompt": "你是资深工程师,请帮我写...",
        "rationale": "补充了角色定义",
        "model": "deepseek-v4-flash",
    }
    defaults.update(overrides)
    return OptimizationRecord(**defaults)


def test_valid_record_builds() -> None:
    record = _valid_record()
    assert record.id == "abcdef123456"
    assert record.schema_version == 1


def test_rejects_empty_raw_prompt() -> None:
    with pytest.raises(ValidationError):
        _valid_record(raw_prompt="   ")


def test_rejects_empty_optimized_prompt() -> None:
    with pytest.raises(ValidationError):
        _valid_record(optimized_prompt="")


def test_rejects_invalid_id_length() -> None:
    with pytest.raises(ValidationError):
        _valid_record(id="short")


def test_rejects_non_hex_id() -> None:
    with pytest.raises(ValidationError):
        _valid_record(id="ghijkl123456")


def test_strips_whitespace_in_prompts() -> None:
    record = _valid_record(raw_prompt="  帮我写代码  ")
    assert record.raw_prompt == "帮我写代码"


def test_none_rationale_allowed() -> None:
    record = _valid_record(rationale=None)
    assert record.rationale is None


def test_blank_rationale_becomes_none() -> None:
    record = _valid_record(rationale="   ")
    assert record.rationale is None


def test_none_model_allowed() -> None:
    record = _valid_record(model=None)
    assert record.model is None


def test_blank_model_becomes_none() -> None:
    record = _valid_record(model="   ")
    assert record.model is None

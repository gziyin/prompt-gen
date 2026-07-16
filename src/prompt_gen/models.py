"""领域模型：生成请求、提示词模板与持久化记录。"""

from __future__ import annotations

from datetime import datetime
from string import Formatter
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _extract_placeholders(template: str) -> list[str]:
    """用 string.Formatter 提取简单占位符；拒绝属性/索引访问。"""
    names: list[str] = []
    seen: set[str] = set()
    for literal_text, field_name, format_spec, conversion in Formatter().parse(template):
        del literal_text, format_spec, conversion
        if field_name is None:
            continue
        if not field_name:
            raise ValueError("不允许空占位符 {}")
        if "." in field_name or "[" in field_name:
            raise ValueError(
                f"拒绝属性或索引式占位符 {{{field_name}}}，仅允许简单变量名"
            )
        if not field_name.isidentifier():
            raise ValueError(
                f"占位符 {{{field_name}}} 不是合法标识符，仅允许 Python 标识符"
            )
        if field_name not in seen:
            seen.add(field_name)
            names.append(field_name)
    return names


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class PromptRequest(BaseModel):
    scenario: str
    goal: str
    audience: str | None = None
    constraints: list[str] = Field(default_factory=list)
    language: str = "zh-CN"

    @field_validator("scenario", "goal", "language", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("不能为空")
        return value

    @field_validator("audience", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("constraints", mode="before")
    @classmethod
    def normalize_constraints(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("constraints 必须是列表")
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return _dedupe_preserve_order(cleaned)


class PromptTemplate(BaseModel):
    name: str
    system_prompt: str
    user_prompt_template: str
    variables: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("name", "system_prompt", "user_prompt_template", mode="before")
    @classmethod
    def strip_required_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("不能为空")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("variables", mode="before")
    @classmethod
    def normalize_variables(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("variables 必须是列表")
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                raise ValueError("变量名不能为空")
            if "." in text or "[" in text or not text.isidentifier():
                raise ValueError(f"非法变量名: {text}")
            cleaned.append(text)
        return _dedupe_preserve_order(cleaned)

    @model_validator(mode="after")
    def variables_must_match_placeholders(self) -> PromptTemplate:
        placeholders = _extract_placeholders(self.user_prompt_template)
        declared = list(self.variables)
        if set(placeholders) != set(declared):
            raise ValueError(
                "variables 必须与 user_prompt_template 中的占位符一致："
                f"模板={placeholders}, 声明={declared}"
            )
        # 以模板中出现顺序为准，保证确定性
        self.variables = placeholders
        return self


class StoredPrompt(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    created_at: datetime
    source: PromptRequest
    template: PromptTemplate

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value or len(value) != 12 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("id 必须是 12 位小写十六进制字符串")
        return value

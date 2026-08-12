"""领域模型:优化记录。

一次"优化对话" = 用户原始 prompt + LLM 优化后 prompt + 优化说明。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class OptimizationRecord(BaseModel):
    """一次提示词优化的完整记录。

    持久化到 history/<id>.json,可列表/查看/导出。
    """

    schema_version: Literal[1] = 1
    id: str  # 12 位小写 hex
    created_at: datetime
    raw_prompt: str  # 用户原始输入
    optimized_prompt: str  # 优化后的完整 prompt
    rationale: str | None = None  # 优化说明(为什么这样改)
    model: str | None = None  # 使用的模型(元数据,便于回溯)

    @field_validator("raw_prompt", "optimized_prompt", mode="before")
    @classmethod
    def strip_and_check_nonempty(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("prompt 不能为空")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if (
            not value
            or len(value) != 12
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("id 必须是 12 位小写十六进制字符串")
        return value

    @field_validator("rationale", "model", mode="before")
    @classmethod
    def strip_optional(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class RepoPrompt(BaseModel):
    """prompt 仓库中的一条常用提示词。

    手动记录的可复用提示词，可归入可选的分组（group），也可直接
    存在默认路径下（group 为 None）。持久化到 repo/<id>.json。
    """

    schema_version: Literal[1] = 1
    id: str  # 12 位小写 hex
    name: str  # 显示名，非空，参与搜索
    content: str  # 提示词正文，非空
    group: str | None = None  # 可选分组；空白→None，不强制层级
    description: str | None = None  # 可选备注，参与搜索
    created_at: datetime
    updated_at: datetime  # 创建时等于 created_at，update 时刷新

    @field_validator("name", "content", mode="before")
    @classmethod
    def strip_and_check_nonempty(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("prompt 不能为空")
        return value

    @field_validator("group", "description", mode="before")
    @classmethod
    def strip_optional(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if (
            not value
            or len(value) != 12
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ValueError("id 必须是 12 位小写十六进制字符串")
        return value

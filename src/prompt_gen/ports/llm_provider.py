"""LLM 提供方端口:统一的 LLM 调用接口。

参考 grok-build 的 ChatCompletionRequest 类型化请求思想,
简化为同步、单轮、文本优先,匹配 CLI 工具场景。
所有 LLM 调用通过此端口,用例不感知具体后端。
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class Message(BaseModel):
    """单条消息(OpenAI 风格 role/content)。"""

    role: str  # "system" | "user" | "assistant"
    content: str

    model_config = {"extra": "forbid"}


class LLMRequest(BaseModel):
    """类型化 LLM 请求。

    参考 grok-build ChatCompletionRequest,保留 CLI 场景需要的字段。
    response_format: None=自由文本, "json_object"=强制 JSON 输出。
    """

    messages: list[Message]
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    response_format: str | None = None

    model_config = {"extra": "forbid"}


class LLMResponse(BaseModel):
    """LLM 响应。

    content 为解析后的文本内容;raw 保留原始响应对象供调试。
    """

    content: str
    raw: Any | None = None


class LLMProvider(Protocol):
    """LLM 提供方端口。

    用例(PromptOptimizer 等)通过此端口调用 LLM,不感知具体后端。
    切换 DeepSeek -> OpenAI 只需新增一个 Provider 实现,用例零改动。
    """

    def complete(self, request: LLMRequest) -> LLMResponse: ...

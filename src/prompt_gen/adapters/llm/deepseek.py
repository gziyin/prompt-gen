"""DeepSeek LLM 适配器:实现 LLMProvider 端口。

封装 langchain-deepseek 的调用细节:
- 关闭 thinking mode(deepseek-v4-* 默认开 thinking,会拒绝部分参数)
- 根据 response_format 选择 json_object 模式或自由文本
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from prompt_gen.ports.llm_provider import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
)


class DeepSeekProvider:
    """DeepSeek LLM 适配器。

    实现 LLMProvider Protocol,但不是 Protocol 的子类
    (Python Protocol 是结构化类型,鸭子匹配即可)。
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, request: LLMRequest) -> LLMResponse:
        chat = ChatDeepSeek(
            model=request.model or self._model,
            api_key=self._api_key,
            temperature=request.temperature,
            max_tokens=request.max_tokens or 4096,
            extra_body={"thinking": {"type": "disabled"}},
        )

        if request.response_format == "json_object":
            chat = chat.bind(response_format={"type": "json_object"})

        messages = _to_langchain_messages(request.messages)
        result = chat.invoke(messages)
        content = _extract_content(result)
        return LLMResponse(content=content, raw=result)


def _to_langchain_messages(messages) -> list[BaseMessage]:
    """转换端口 Message 列表为 langchain 消息对象。"""
    result: list[BaseMessage] = []
    for m in messages:
        if m.role == "system":
            result.append(SystemMessage(content=m.content))
        elif m.role == "assistant":
            result.append(AIMessage(content=m.content))
        else:
            result.append(HumanMessage(content=m.content))
    return result


def _extract_content(result: object) -> str:
    """从 langchain 响应中提取文本内容。"""
    if isinstance(result, BaseMessage):
        return str(result.content)
    return str(result)


def build_deepseek_provider(api_key: str, model: str) -> LLMProvider:
    """工厂函数:构建 DeepSeekProvider 实例。

    返回类型标注为 LLMProvider(Protocol),便于上层依赖抽象而非具体。
    """
    return DeepSeekProvider(api_key=api_key, model=model)  # type: ignore[arg-type]

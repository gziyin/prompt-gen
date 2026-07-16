"""LLM 结构化生成：依赖注入隔离真实 API。"""

from __future__ import annotations

import json
from typing import Protocol

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import ValidationError

from prompt_gen.config import Settings
from prompt_gen.exceptions import PromptGenerationError
from prompt_gen.models import PromptRequest, PromptTemplate

SYSTEM_INSTRUCTIONS = """你是提示词工程助手。根据用户给出的场景、目标、受众与约束，
生成一份可复用的结构化提示词模板，并只输出合法 JSON（不要 Markdown 代码块）。

硬性要求：
1. 输出 JSON 字段：name, system_prompt, user_prompt_template, variables, notes。
2. name 简短明确，体现场景。
3. system_prompt 必须体现角色、受众（若有）和目标；把可复用约束写进 system_prompt。
4. user_prompt_template 只放当次输入占位，使用简单占位符，例如 {code}、{draft}。
5. 禁止属性或索引式占位符，例如 {user.name}、{items[0]}。
6. variables 必须恰好等于 user_prompt_template 中出现的全部占位符，不能多也不能少。
7. notes 必须是非空字符串：说明用法、推荐变量填什么、输出应关注什么；不要写 null。
8. 文案语言遵循请求中的 language 字段。

EXAMPLE JSON OUTPUT:
{
  "name": "Python 代码审查",
  "system_prompt": "你是资深 Python 审查者，服务对象是 Python 开发者。只评代码本身，给出可复现步骤。",
  "user_prompt_template": "请审查以下代码：\\n{code}",
  "variables": ["code"],
  "notes": "将待审代码填入 {code}；重点看异常路径与边界条件。"
}
"""

_MAX_ATTEMPTS = 2


class StructuredPromptModel(Protocol):
    def invoke(self, input: object) -> PromptTemplate: ...


class PromptGenerator:
    def __init__(self, model: StructuredPromptModel) -> None:
        self._model = model

    def generate(self, request: PromptRequest) -> PromptTemplate:
        messages = [
            SystemMessage(content=SYSTEM_INSTRUCTIONS),
            HumanMessage(content=_build_human_message(request)),
        ]
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return self._invoke_once(messages)
            except PromptGenerationError as exc:
                last_error = exc
                if attempt >= _MAX_ATTEMPTS:
                    break
        assert last_error is not None
        raise last_error

    def _invoke_once(self, messages: list[object]) -> PromptTemplate:
        try:
            result = self._model.invoke(messages)
        except ValidationError as exc:
            raise PromptGenerationError(f"模型输出未通过校验: {exc}") from exc
        except OutputParserException as exc:
            raise PromptGenerationError(
                "模型输出无法解析为结构化 PromptTemplate，请重试或更换模型"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise PromptGenerationError(_safe_api_error(exc)) from exc

        if isinstance(result, PromptTemplate):
            return _ensure_notes(result)
        try:
            return _ensure_notes(PromptTemplate.model_validate(result))
        except ValidationError as exc:
            raise PromptGenerationError(f"模型输出未通过校验: {exc}") from exc


def _build_human_message(request: PromptRequest) -> str:
    payload = {
        "scenario": request.scenario,
        "goal": request.goal,
        "audience": request.audience,
        "constraints": request.constraints,
        "language": request.language,
    }
    return (
        "请根据以下需求生成提示词模板 JSON：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _ensure_notes(template: PromptTemplate) -> PromptTemplate:
    """模型偶发返回 null notes 时，补一条可用说明，避免空 Notes。"""
    if template.notes:
        return template
    vars_hint = (
        "、".join(f"{{{name}}}" for name in template.variables)
        if template.variables
        else "（无变量）"
    )
    return template.model_copy(
        update={"notes": f"使用时填入变量 {vars_hint}；按 system_prompt 中的角色与约束执行。"}
    )


def build_deepseek_generator(settings: Settings) -> PromptGenerator:
    # deepseek-v4-* 默认 thinking mode，会拒绝 function_calling 的 tool_choice。
    # 关闭 thinking，并用 json_mode 做结构化输出，避免 400。
    chat = ChatDeepSeek(
        model=settings.model,
        api_key=settings.api_key,
        temperature=0,
        max_tokens=4096,
        extra_body={"thinking": {"type": "disabled"}},
    )
    structured = chat.with_structured_output(PromptTemplate, method="json_mode")
    return PromptGenerator(structured)  # type: ignore[arg-type]


def _safe_api_error(exc: Exception) -> str:
    """转换为可读错误，避免泄露 API Key 或完整响应体。"""
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered or "authentication" in lowered:
        return f"模型鉴权失败 ({name})：请检查 DEEPSEEK_API_KEY"
    if "429" in text or "rate" in lowered:
        return f"模型请求过于频繁 ({name})：请稍后重试"
    if "timeout" in lowered or "timed out" in lowered:
        return f"模型请求超时 ({name})"
    if "connection" in lowered or "network" in lowered:
        return f"网络连接失败 ({name})"
    if "tool_choice" in lowered or "thinking mode" in lowered:
        return (
            f"模型不支持当前结构化调用方式 ({name})："
            "请升级 prompt-gen，或确认已关闭 thinking / 使用 json_mode"
        )
    snippet = text.replace("\n", " ").strip()
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    if "sk-" in snippet:
        snippet = "（详情已隐藏）"
    return f"模型调用失败 ({name}): {snippet}"

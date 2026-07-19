"""提示词优化器用例:输入粗糙 prompt,输出优化后 prompt + 说明。

通过 LLMProvider 端口调用 LLM,不感知具体后端。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from prompt_gen.exceptions import PromptGenerationError
from prompt_gen.ports.llm_provider import LLMProvider, LLMRequest, Message

OPTIMIZE_INSTRUCTIONS = """你是提示词优化专家。用户会给你一段提示词(prompt),你需要:

1. 分析原提示词的问题(模糊、缺失角色、缺输出格式、冗长等)
2. 输出优化后的完整提示词,使其更清晰、更可复现、更易得到高质量回答
3. 说明你做了哪些优化(为什么这样改)

硬性要求:
- 输出合法 JSON,不要 Markdown 代码块
- JSON 字段:optimized_prompt, rationale
- optimized_prompt 是优化后的完整提示词,用户可直接复制使用
- rationale 是优化说明,简明扼要列出主要改动(分条,不超过 5 条)
- 保持原意,不要改变用户的核心诉求
- 语言跟随用户输入的语言

EXAMPLE JSON OUTPUT:
{
  "optimized_prompt": "你是资深 Python 审查者。请审查以下代码,重点找出:\\n1. 异常路径未处理\\n2. 边界条件缺失\\n3. 资源未释放\\n\\n请按问题严重性排序,每个问题给出:位置、原因、修复建议、可复现步骤。\\n\\n代码:\\n{code}",
  "rationale": "1. 补充了角色定义(资深 Python 审查者)\\n2. 明确了审查重点(3 类问题)\\n3. 规定了输出结构(位置/原因/建议/步骤)\\n4. 保留 {code} 占位符"
}
"""

_MAX_ATTEMPTS = 2


class OptimizedResult(BaseModel):
    """LLM 返回的优化结果(解析自 JSON)。"""

    optimized_prompt: str
    rationale: str | None = None


class PromptOptimizer:
    """提示词优化器用例。

    通过 LLMProvider 端口调用 LLM,重试 _MAX_ATTEMPTS 次,
    返回 (optimized_prompt, rationale)。
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def optimize(self, raw_prompt: str) -> tuple[str, str | None]:
        """优化提示词,返回 (optimized_prompt, rationale)。"""
        request = LLMRequest(
            messages=[
                Message(role="system", content=OPTIMIZE_INSTRUCTIONS),
                Message(role="user", content=raw_prompt),
            ],
            response_format="json_object",
        )
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return self._invoke_once(request)
            except PromptGenerationError as exc:
                last_error = exc
                if attempt >= _MAX_ATTEMPTS:
                    break
        assert last_error is not None
        raise last_error

    def _invoke_once(self, request: LLMRequest) -> tuple[str, str | None]:
        try:
            response = self._llm.complete(request)
        except Exception as exc:  # noqa: BLE001
            raise PromptGenerationError(_safe_api_error(exc)) from exc

        try:
            data = json.loads(response.content)
            result = OptimizedResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise PromptGenerationError(
                f"模型输出无法解析为优化结果 JSON: {exc}"
            ) from exc

        return result.optimized_prompt, result.rationale


def _safe_api_error(exc: Exception) -> str:
    """转换为可读错误,避免泄露 API Key 或完整响应体。"""
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered or "authentication" in lowered:
        return f"模型鉴权失败 ({name}):请检查 DEEPSEEK_API_KEY"
    if "429" in text or "rate" in lowered:
        return f"模型请求过于频繁 ({name}):请稍后重试"
    if "timeout" in lowered or "timed out" in lowered:
        return f"模型请求超时 ({name})"
    if "connection" in lowered or "network" in lowered:
        return f"网络连接失败 ({name})"
    if "tool_choice" in lowered or "thinking mode" in lowered:
        return (
            f"模型不支持当前调用方式 ({name}):"
            "请确认已关闭 thinking / 使用 json_mode"
        )
    snippet = text.replace("\n", " ").strip()
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    if "sk-" in snippet:
        snippet = "(详情已隐藏)"
    return f"模型调用失败 ({name}): {snippet}"

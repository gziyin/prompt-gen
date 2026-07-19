"""PromptOptimizer 用例测试(假 LLM,不消耗 Token)。"""

from __future__ import annotations

import json

import pytest

from prompt_gen.domain.optimizer import PromptOptimizer, _safe_api_error
from prompt_gen.exceptions import PromptGenerationError
from prompt_gen.ports.llm_provider import LLMRequest, LLMResponse


class FakeLLM:
    """假 LLM Provider,模拟 LLMProvider Protocol。"""

    def __init__(self, result: str | Exception | list[str | Exception]) -> None:
        if isinstance(result, list):
            self._queue: list[str | Exception] = list(result)
        else:
            self._queue = [result]
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if not self._queue:
            raise RuntimeError("FakeLLM 队列已空")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(content=item)


def _ok_json(optimized: str = "优化后", rationale: str = "说明") -> str:
    return json.dumps(
        {"optimized_prompt": optimized, "rationale": rationale},
        ensure_ascii=False,
    )


def test_optimize_returns_tuple() -> None:
    fake = FakeLLM(_ok_json(optimized="你是专家...", rationale="补了角色"))
    optimizer = PromptOptimizer(fake)
    optimized, rationale = optimizer.optimize("帮我写代码")
    assert optimized == "你是专家..."
    assert rationale == "补了角色"


def test_optimize_sends_system_and_user_messages() -> None:
    fake = FakeLLM(_ok_json())
    optimizer = PromptOptimizer(fake)
    optimizer.optimize("原始 prompt")
    assert len(fake.calls) == 1
    request = fake.calls[0]
    assert len(request.messages) == 2
    assert request.messages[0].role == "system"
    assert request.messages[1].role == "user"
    assert request.messages[1].content == "原始 prompt"


def test_optimize_uses_json_response_format() -> None:
    fake = FakeLLM(_ok_json())
    optimizer = PromptOptimizer(fake)
    optimizer.optimize("test")
    assert fake.calls[0].response_format == "json_object"


def test_optimize_retries_once_then_succeeds() -> None:
    fake = FakeLLM([RuntimeError("connection reset"), _ok_json()])
    optimizer = PromptOptimizer(fake)
    optimized, _ = optimizer.optimize("test")
    assert optimized == "优化后"
    assert len(fake.calls) == 2


def test_optimize_raises_after_max_attempts() -> None:
    fake = FakeLLM(
        [RuntimeError("connection reset"), RuntimeError("connection reset")]
    )
    optimizer = PromptOptimizer(fake)
    with pytest.raises(PromptGenerationError, match="网络|失败|connection"):
        optimizer.optimize("test")
    assert len(fake.calls) == 2


def test_optimize_raises_on_invalid_json() -> None:
    fake = FakeLLM(["not a json", "not a json"])  # 两次重试都返回无效 JSON
    optimizer = PromptOptimizer(fake)
    with pytest.raises(PromptGenerationError, match="无法解析"):
        optimizer.optimize("test")


def test_optimize_raises_on_missing_optimized_prompt_field() -> None:
    bad_json = json.dumps({"rationale": "缺 optimized_prompt"})
    fake = FakeLLM([bad_json, bad_json])
    optimizer = PromptOptimizer(fake)
    with pytest.raises(PromptGenerationError, match="无法解析"):
        optimizer.optimize("test")


def test_optimize_none_rationale_allowed() -> None:
    fake = FakeLLM(json.dumps({"optimized_prompt": "ok", "rationale": None}))
    optimizer = PromptOptimizer(fake)
    optimized, rationale = optimizer.optimize("test")
    assert optimized == "ok"
    assert rationale is None


def test_safe_api_error_maps_auth_failure() -> None:
    msg = _safe_api_error(RuntimeError("401 unauthorized"))
    assert "鉴权" in msg


def test_safe_api_error_maps_rate_limit() -> None:
    msg = _safe_api_error(RuntimeError("429 rate limit"))
    assert "频繁" in msg


def test_safe_api_error_maps_timeout() -> None:
    msg = _safe_api_error(RuntimeError("request timed out"))
    assert "超时" in msg


def test_safe_api_error_hides_api_key() -> None:
    msg = _safe_api_error(RuntimeError("error with sk-abc123 in it"))
    assert "隐藏" in msg

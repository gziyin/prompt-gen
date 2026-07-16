"""生成层测试（假模型，不消耗 Token）。"""

import pytest

from prompt_gen.exceptions import PromptGenerationError
from prompt_gen.generator import PromptGenerator
from prompt_gen.models import PromptRequest, PromptTemplate


class FakeModel:
    def __init__(self, result: object | Exception | list[object | Exception]) -> None:
        self._queue: list[object | Exception]
        if isinstance(result, list):
            self._queue = list(result)
        else:
            self._queue = [result]
        self.calls: list[object] = []

    def invoke(self, input: object) -> object:
        self.calls.append(input)
        if not self._queue:
            raise RuntimeError("FakeModel 队列已空")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _request() -> PromptRequest:
    return PromptRequest(
        scenario="代码审查",
        goal="找 bug",
        audience="Python 开发者",
        constraints=["只评代码"],
    )


def _template(*, notes: str | None = "关注异常") -> PromptTemplate:
    return PromptTemplate(
        name="审查模板",
        system_prompt="你是审查者",
        user_prompt_template="审查：\n{code}",
        variables=["code"],
        notes=notes,
    )


def test_generate_passes_request_and_returns_template() -> None:
    fake = FakeModel(_template())
    gen = PromptGenerator(fake)
    result = gen.generate(_request())
    assert result.name == "审查模板"
    assert fake.calls  # 收到过调用
    human = fake.calls[0][1].content
    assert "请根据以下需求生成提示词模板 JSON" in human
    assert "代码审查" in human


def test_generate_fills_missing_notes() -> None:
    fake = FakeModel(_template(notes=None))
    gen = PromptGenerator(fake)
    result = gen.generate(_request())
    assert result.notes
    assert "{code}" in result.notes


def test_generate_retries_once_then_succeeds() -> None:
    fake = FakeModel([RuntimeError("connection reset"), _template()])
    gen = PromptGenerator(fake)
    result = gen.generate(_request())
    assert result.name == "审查模板"
    assert len(fake.calls) == 2


def test_model_exception_becomes_generation_error() -> None:
    fake = FakeModel(
        [RuntimeError("connection reset"), RuntimeError("connection reset")]
    )
    gen = PromptGenerator(fake)
    with pytest.raises(PromptGenerationError, match="网络|失败|connection"):
        gen.generate(_request())
    assert len(fake.calls) == 2


def test_output_parser_exception_becomes_generation_error() -> None:
    from langchain_core.exceptions import OutputParserException

    fake = FakeModel(
        [OutputParserException("bad json"), OutputParserException("bad json")]
    )
    gen = PromptGenerator(fake)
    with pytest.raises(PromptGenerationError, match="无法解析"):
        gen.generate(_request())

def test_inconsistent_placeholder_rejected() -> None:
    class BadModel:
        def invoke(self, input: object) -> object:
            return {
                "name": "坏",
                "system_prompt": "sys",
                "user_prompt_template": "用 {a}",
                "variables": ["b"],
                "notes": None,
            }

    gen = PromptGenerator(BadModel())
    with pytest.raises(PromptGenerationError, match="校验"):
        gen.generate(_request())


def test_build_deepseek_disables_thinking_and_uses_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    from prompt_gen.config import Settings
    from prompt_gen.generator import build_deepseek_generator

    captured: dict[str, object] = {}

    class FakeChat:
        def __init__(self, **kwargs: object) -> None:
            captured["init"] = kwargs

        def with_structured_output(self, schema: object, **kwargs: object) -> object:
            captured["schema"] = schema
            captured["wso"] = kwargs
            return FakeModel(_template())

    monkeypatch.setattr("prompt_gen.generator.ChatDeepSeek", FakeChat)
    settings = Settings(
        api_key="sk-test",
        model="deepseek-v4-flash",
        data_dir=Path("."),
        export_dir=Path("."),
    )
    gen = build_deepseek_generator(settings)
    assert isinstance(gen, PromptGenerator)
    assert captured["init"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured["wso"]["method"] == "json_mode"
    assert captured["schema"] is PromptTemplate


def test_safe_api_error_maps_tool_choice() -> None:
    from prompt_gen.generator import _safe_api_error

    msg = _safe_api_error(
        RuntimeError("Thinking mode does not support this tool_choice")
    )
    assert "结构化调用" in msg

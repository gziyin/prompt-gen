"""领域模型校验测试。"""

import pytest
from pydantic import ValidationError

from prompt_gen.models import PromptRequest, PromptTemplate, StoredPrompt


def test_valid_request_and_template() -> None:
    request = PromptRequest(
        scenario="代码审查",
        goal="找出可靠性问题",
        audience="Python 开发者",
        constraints=["只评代码", "给出示例"],
    )
    template = PromptTemplate(
        name="Python 审查",
        system_prompt="你是资深审查者。",
        user_prompt_template="请审查以下代码：\n{code}",
        variables=["code"],
        notes="关注异常路径",
    )
    assert request.scenario == "代码审查"
    assert template.variables == ["code"]


def test_strips_and_rejects_empty_fields() -> None:
    with pytest.raises(ValidationError):
        PromptRequest(scenario="  ", goal="目标")
    with pytest.raises(ValidationError):
        PromptTemplate(
            name="x",
            system_prompt="s",
            user_prompt_template="  ",
            variables=[],
        )


def test_constraints_dedupe_preserve_order() -> None:
    request = PromptRequest(
        scenario="场景",
        goal="目标",
        constraints=["A", " B ", "A", "C", ""],
    )
    assert request.constraints == ["A", "B", "C"]


def test_rejects_attribute_placeholders() -> None:
    with pytest.raises(ValidationError, match="属性或索引|非法变量名"):
        PromptTemplate(
            name="坏模板",
            system_prompt="sys",
            user_prompt_template="Hello {user.name}",
            variables=["user"],
        )
    with pytest.raises(ValidationError, match="属性或索引|非法变量名"):
        PromptTemplate(
            name="坏模板2",
            system_prompt="sys",
            user_prompt_template="Hello {items[0]}",
            variables=["items"],
        )


def test_rejects_missing_or_extra_variables() -> None:
    with pytest.raises(ValidationError, match="一致"):
        PromptTemplate(
            name="缺变量",
            system_prompt="sys",
            user_prompt_template="分析 {topic}",
            variables=[],
        )
    with pytest.raises(ValidationError, match="一致"):
        PromptTemplate(
            name="多变量",
            system_prompt="sys",
            user_prompt_template="分析 {topic}",
            variables=["topic", "extra"],
        )


def test_stored_prompt_id_format() -> None:
    template = PromptTemplate(
        name="t",
        system_prompt="s",
        user_prompt_template="x {a}",
        variables=["a"],
    )
    request = PromptRequest(scenario="s", goal="g")
    with pytest.raises(ValidationError):
        StoredPrompt(
            id="NOT-HEX",
            created_at="2026-01-01T00:00:00Z",
            source=request,
            template=template,
        )

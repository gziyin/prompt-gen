"""对抗性回归：脚本模式、配置根路径、序列化与占位符。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from prompt_gen import config as config_mod
from prompt_gen.cli import app
from prompt_gen.generator import PromptGenerator
from prompt_gen.models import PromptRequest, PromptTemplate
from prompt_gen.store import PromptStore

runner = CliRunner()


class OkModel:
    def __init__(self) -> None:
        self.last_input: object | None = None

    def invoke(self, input: object) -> PromptTemplate:
        self.last_input = input
        return PromptTemplate(
            name="脚本模板",
            system_prompt="sys",
            user_prompt_template="内容：{content}",
            variables=["content"],
        )


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "prompts"
    exports = tmp_path / "exports"
    data.mkdir()
    exports.mkdir()
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(data))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(exports))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv",
        lambda *args, **kwargs: None,
    )
    return tmp_path


def test_generate_with_flags_does_not_prompt_audience(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """脚本传入 scenario/goal 时，不应再交互询问受众。"""
    model = OkModel()
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_generator",
        lambda settings: PromptGenerator(model),
    )
    # 不提供 input；若仍 prompt 受众，CliRunner 会失败或带上提示文案
    result = runner.invoke(
        app,
        ["generate", "--scenario", "代码审查", "--goal", "找问题"],
    )
    assert result.exit_code == 0, result.output
    assert "受众" not in result.output
    stored = PromptStore(cli_env / "prompts").list_all()[0]
    assert stored.source.audience is None
    assert stored.source.scenario == "代码审查"


def test_json_written_with_lf_and_unicode(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    saved = store.save(
        PromptRequest(scenario="邮件润色", goal="更专业"),
        PromptTemplate(
            name="润色",
            system_prompt="助手",
            user_prompt_template="润色：{draft}",
            variables=["draft"],
        ),
    )
    raw = (tmp_path / f"{saved.id}.json").read_bytes()
    assert b"\r\n" not in raw
    assert "邮件润色".encode("utf-8") in raw
    data = json.loads(raw.decode("utf-8"))
    assert data["source"]["scenario"] == "邮件润色"


def test_rejects_non_identifier_placeholders() -> None:
    with pytest.raises(ValidationError):
        PromptTemplate(
            name="n",
            system_prompt="s",
            user_prompt_template="值 {0}",
            variables=["0"],
        )


def test_generator_sends_json_payload() -> None:
    model = OkModel()
    gen = PromptGenerator(model)
    gen.generate(PromptRequest(scenario="学习笔记", goal="提炼要点", language="zh-CN"))
    assert model.last_input is not None
    human = model.last_input[1]
    assert "请根据以下需求生成提示词模板 JSON" in human.content
    assert '"scenario": "学习笔记"' in human.content
    assert '"goal": "提炼要点"' in human.content


def test_default_data_dir_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROMPT_GEN_DATA_DIR", raising=False)
    monkeypatch.delenv("PROMPT_GEN_EXPORT_DIR", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(config_mod, "_find_project_root", lambda: None)
    monkeypatch.chdir(tmp_path)
    settings = config_mod.load_settings(require_api_key=False)
    assert settings.data_dir == (tmp_path / "prompts").resolve()
    assert settings.export_dir == (tmp_path / "exports").resolve()


def test_script_missing_scenario_exits_2(cli_env: Path) -> None:
    result = runner.invoke(app, ["generate", "--goal", "找问题"])
    assert result.exit_code == 2
    assert "--scenario" in result.output


def test_script_blank_scenario_exits_2(cli_env: Path) -> None:
    result = runner.invoke(
        app,
        ["generate", "--scenario", "   ", "--goal", "找问题"],
    )
    assert result.exit_code == 2
    assert "场景" in result.output


def test_rich_markup_in_template_not_eaten(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MarkupModel:
        def invoke(self, input: object) -> PromptTemplate:
            return PromptTemplate(
                name="含[bold]标题",
                system_prompt="保留 [red]标记[/red]",
                user_prompt_template="输入 {content}",
                variables=["content"],
            )

    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_generator",
        lambda settings: PromptGenerator(MarkupModel()),
    )
    result = runner.invoke(
        app,
        ["generate", "--scenario", "测试", "--goal", "保留标记"],
    )
    assert result.exit_code == 0, result.output
    assert "[red]标记[/red]" in result.output
    assert "[bold]" in result.output


def test_list_ignores_non_id_json(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    store.save(
        PromptRequest(scenario="s", goal="g"),
        PromptTemplate(
            name="n",
            system_prompt="s",
            user_prompt_template="{a}",
            variables=["a"],
        ),
    )
    (tmp_path / "notes.json").write_text('{"hello": 1}\n', encoding="utf-8")
    items = store.list_all()
    assert len(items) == 1


def test_list_sorts_mixed_naive_and_aware_datetimes(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    older = store.save(
        PromptRequest(scenario="old", goal="g"),
        PromptTemplate(
            name="old",
            system_prompt="s",
            user_prompt_template="{a}",
            variables=["a"],
        ),
    )
    newer = store.save(
        PromptRequest(scenario="new", goal="g"),
        PromptTemplate(
            name="new",
            system_prompt="s",
            user_prompt_template="{a}",
            variables=["a"],
        ),
    )
    path = tmp_path / f"{older.id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["created_at"] = "2020-01-01T00:00:00"  # naive
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    items = store.list_all()
    assert [item.id for item in items] == [newer.id, older.id]


def test_export_strips_id_whitespace(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = PromptStore(cli_env / "prompts")
    saved = store.save(
        PromptRequest(scenario="s", goal="g"),
        PromptTemplate(
            name="n",
            system_prompt="s",
            user_prompt_template="{a}",
            variables=["a"],
        ),
    )
    result = runner.invoke(app, ["export", f"  {saved.id}  "])
    assert result.exit_code == 0, result.output
    assert (cli_env / "exports" / f"{saved.id}.md").exists()
    assert not list((cli_env / "exports").glob("* *"))

"""CLI 命令测试（Mock LLM，不消耗 API）。"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_gen.cli import app
from prompt_gen.generator import PromptGenerator
from prompt_gen.models import PromptRequest, PromptTemplate
from prompt_gen.store import PromptStore

runner = CliRunner()


class OkModel:
    def invoke(self, input: object) -> PromptTemplate:
        return PromptTemplate(
            name="演示模板",
            system_prompt="系统提示",
            user_prompt_template="输入：{content}",
            variables=["content"],
            notes="测试笔记",
        )


@pytest.fixture()
def env_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "prompts"
    exports = tmp_path / "exports"
    data.mkdir()
    exports.mkdir()
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(data))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(exports))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-not-real")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    return tmp_path


def test_generate_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(tmp_path / "prompts"))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(tmp_path / "exports"))
    # 避免读到用户真实 .env
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv",
        lambda *args, **kwargs: None,
    )
    result = runner.invoke(
        app,
        [
            "generate",
            "--scenario",
            "代码审查",
            "--goal",
            "找问题",
            "--audience",
            "开发者",
        ],
    )
    assert result.exit_code == 2
    assert "DEEPSEEK_API_KEY" in result.output


def test_list_works_without_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "prompts"
    data.mkdir()
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(data))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv",
        lambda *args, **kwargs: None,
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "暂无模板" in result.output


def test_generate_list_show_export(env_dirs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_generator",
        lambda settings: PromptGenerator(OkModel()),
    )
    gen = runner.invoke(
        app,
        [
            "generate",
            "--scenario",
            "代码审查",
            "--goal",
            "找可靠性问题",
            "--audience",
            "Python 开发者",
            "--constraint",
            "只评代码",
        ],
    )
    assert gen.exit_code == 0, gen.output
    assert "已生成" in gen.output or "演示模板" in gen.output

    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "演示模板" in listed.output

    prompt_id = PromptStore(env_dirs / "prompts").list_all()[0].id

    shown = runner.invoke(app, ["show", prompt_id])
    assert shown.exit_code == 0
    assert "代码审查" in shown.output
    assert "演示模板" in shown.output

    out_file = env_dirs / "custom.md"
    exported = runner.invoke(app, ["export", prompt_id, "--output", str(out_file)])
    assert exported.exit_code == 0
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    assert "## System Prompt" in text
    assert "{content}" in text


def test_show_invalid_id_exit_code(env_dirs: Path) -> None:
    result = runner.invoke(app, ["show", "../secret"])
    assert result.exit_code == 3


def test_show_missing_id_exit_code(env_dirs: Path) -> None:
    result = runner.invoke(app, ["show", "aaaaaaaaaaaa"])
    assert result.exit_code == 3


def test_menu_exits_on_zero(env_dirs: Path) -> None:
    result = runner.invoke(app, [], input="0\n")
    assert result.exit_code == 0
    assert "欢迎" in result.output or "prompt-gen" in result.output
    assert "已退出" in result.output


def test_doctor_ok_with_key(env_dirs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv",
        lambda *args, **kwargs: None,
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "环境检查" in result.output
    assert "环境就绪" in result.output


def test_doctor_fails_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(tmp_path / "prompts"))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv",
        lambda *args, **kwargs: None,
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 2
    assert "API Key" in result.output


def test_interactive_generate_shows_guidance(
    env_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_generator",
        lambda settings: PromptGenerator(OkModel()),
    )
    result = runner.invoke(
        app,
        ["generate"],
        input="代码审查\n找问题\n开发者\n只评代码\n",
    )
    assert result.exit_code == 0, result.output
    assert "交互生成" in result.output
    assert "已生成" in result.output or "演示模板" in result.output

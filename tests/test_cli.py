"""CLI 测试:optimize / history / export / doctor。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.cli import _resolve_choice, app
from prompt_gen.ports.llm_provider import LLMRequest, LLMResponse

runner = CliRunner()


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self._content)


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "history"
    exports = tmp_path / "exports"
    data.mkdir()
    exports.mkdir()
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(data))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(exports))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv", lambda *args, **kwargs: None
    )
    return tmp_path


def _ok_json(optimized: str = "你是专家,请...", rationale: str = "补了角色") -> str:
    return json.dumps(
        {"optimized_prompt": optimized, "rationale": rationale}, ensure_ascii=False
    )


def test_optimize_with_prompt_flag_does_not_interact(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--prompt 参数模式不应交互询问。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "帮我写代码"])
    assert result.exit_code == 0, result.output
    assert "你是专家" in result.output
    assert "补了角色" in result.output


def test_optimize_saves_to_history(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "test prompt"])
    assert result.exit_code == 0, result.output
    store = HistoryStore(cli_env / "history")
    items = store.list_all()
    assert len(items) == 1
    assert items[0].raw_prompt == "test prompt"


def test_optimize_empty_prompt_exits_2(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--prompt 传空白应退出码 2。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "   "])
    assert result.exit_code == 2
    assert "不能为空" in result.output


def test_history_empty(cli_env: Path) -> None:
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0, result.output
    assert "暂无" in result.output


def test_history_lists_saved_records(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json(optimized="优化内容")),
    )
    runner.invoke(app, ["optimize", "--prompt", "原始内容"])
    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0, result.output
    assert "原始内容" in result.output
    assert "优化内容" in result.output


def test_export_writes_markdown(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "原始"])
    assert result.exit_code == 0, result.output

    store = HistoryStore(cli_env / "history")
    record_id = store.list_all()[0].id

    result = runner.invoke(app, ["export", record_id])
    assert result.exit_code == 0, result.output
    export_path = cli_env / "exports" / f"{record_id}.md"
    assert export_path.exists()
    content = export_path.read_text(encoding="utf-8")
    assert "## 原始提示词" in content
    assert "## 优化后提示词" in content


def test_export_strips_id_whitespace(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    runner.invoke(app, ["optimize", "--prompt", "test"])
    store = HistoryStore(cli_env / "history")
    record_id = store.list_all()[0].id

    result = runner.invoke(app, ["export", f"  {record_id}  "])
    assert result.exit_code == 0, result.output
    assert (cli_env / "exports" / f"{record_id}.md").exists()


def test_export_nonexistent_id_exits_3(cli_env: Path) -> None:
    result = runner.invoke(app, ["export", "abcdef123456"])
    assert result.exit_code == 3


def test_doctor_reports_env(cli_env: Path) -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "环境就绪" in result.output


def test_doctor_missing_api_key_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "history"
    exports = tmp_path / "exports"
    data.mkdir()
    exports.mkdir()
    monkeypatch.setenv("PROMPT_GEN_DATA_DIR", str(data))
    monkeypatch.setenv("PROMPT_GEN_EXPORT_DIR", str(exports))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "prompt_gen.config.load_dotenv", lambda *args, **kwargs: None
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 2


# -- _resolve_choice:菜单输入多形式解析 --


def test_resolve_choice_digit_shortcut() -> None:
    assert _resolve_choice("1") == ["optimize"]
    assert _resolve_choice("2") == ["history"]
    assert _resolve_choice("3") == ["export"]
    assert _resolve_choice("4") == ["doctor"]


def test_resolve_choice_exit() -> None:
    assert _resolve_choice("0") == ["__exit__"]
    assert _resolve_choice("q") == ["__exit__"]
    assert _resolve_choice("quit") == ["__exit__"]
    assert _resolve_choice("退出") == ["__exit__"]


def test_resolve_choice_chinese_keyword() -> None:
    assert _resolve_choice("优化") == ["optimize"]
    assert _resolve_choice("历史") == ["history"]
    assert _resolve_choice("导出") == ["export"]
    assert _resolve_choice("检查") == ["doctor"]


def test_resolve_choice_command_name() -> None:
    assert _resolve_choice("optimize") == ["optimize"]
    assert _resolve_choice("history") == ["history"]
    assert _resolve_choice("export") == ["export"]
    assert _resolve_choice("doctor") == ["doctor"]


def test_resolve_choice_full_command_with_prompt_gen_prefix() -> None:
    assert _resolve_choice("prompt-gen optimize") == ["optimize"]
    assert _resolve_choice("prompt-gen history") == ["history"]
    assert _resolve_choice("prompt-gen doctor") == ["doctor"]


def test_resolve_choice_full_command_with_args() -> None:
    assert _resolve_choice("prompt-gen export abc123") == ["export", "abc123"]
    assert _resolve_choice("export abc123") == ["export", "abc123"]


def test_resolve_choice_empty_returns_none() -> None:
    assert _resolve_choice("") is None
    assert _resolve_choice("   ") is None


def test_resolve_choice_invalid_returns_none() -> None:
    assert _resolve_choice("invalid") is None
    assert _resolve_choice("abc") is None
    assert _resolve_choice("prompt-gen") is None
    assert _resolve_choice("prompt-gen unknown") is None


def test_resolve_choice_strips_whitespace() -> None:
    assert _resolve_choice("  1  ") == ["optimize"]
    assert _resolve_choice("  optimize  ") == ["optimize"]


# -- doctor:命令可用性检查 --


def test_doctor_reports_command_available(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """shutil.which 找到 prompt-gen 时,doctor 应报告命令可用。"""
    monkeypatch.setattr(
        "prompt_gen.cli.shutil.which", lambda cmd: "/fake/path/prompt-gen"
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "命令可用性" in result.output
    assert "PATH" in result.output


def test_doctor_reports_command_missing_with_hint(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """shutil.which 找不到 prompt-gen 时,doctor 应提示 PATH 配置方法。"""
    monkeypatch.setattr("prompt_gen.cli.shutil.which", lambda cmd: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "命令可用性" in result.output
    assert "PATH" in result.output
    assert "永久方案" in result.output or "Activate" in result.output

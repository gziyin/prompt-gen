"""CLI 测试:optimize / history / export / doctor。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.cli import app
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

"""对抗性回归:序列化、配置根路径、ID 校验、旧格式兼容。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_gen import config as config_mod
from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.cli import app
from prompt_gen.ports.llm_provider import LLMRequest, LLMResponse

runner = CliRunner()


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


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self._content)


def test_default_data_dir_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无环境变量时,data_dir 默认到 cwd/prompts。"""
    monkeypatch.delenv("PROMPT_GEN_DATA_DIR", raising=False)
    monkeypatch.delenv("PROMPT_GEN_EXPORT_DIR", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(config_mod, "_find_project_root", lambda: None)
    monkeypatch.chdir(tmp_path)
    settings = config_mod.load_settings(require_api_key=False)
    assert settings.data_dir == (tmp_path / "prompts").resolve()
    assert settings.export_dir == (tmp_path / "exports").resolve()


def test_history_store_atomic_write_uses_lf(tmp_path: Path) -> None:
    """JSON 文件用 LF 换行,而非 CRLF。"""
    store = HistoryStore(tmp_path)
    saved = store.save(
        raw_prompt="中文测试",
        optimized_prompt="优化版",
        rationale=None,
        model=None,
    )
    raw = (tmp_path / f"{saved.id}.json").read_bytes()
    assert b"\r\n" not in raw
    assert "中文测试".encode("utf-8") in raw


def test_history_store_list_ignores_non_id_json(tmp_path: Path) -> None:
    """list_all 忽略不符合 ID 格式的 JSON 文件。"""
    store = HistoryStore(tmp_path)
    store.save("raw", "opt", None, None)
    (tmp_path / "notes.json").write_text('{"hello": 1}\n', encoding="utf-8")
    items = store.list_all()
    assert len(items) == 1


def test_history_store_list_skips_corrupted_legacy_files(tmp_path: Path) -> None:
    """旧模板格式文件(不符合 OptimizationRecord schema)应跳过,不崩溃。"""
    store = HistoryStore(tmp_path)
    store.save("raw", "opt", "说明", "model")
    legacy_path = tmp_path / "deadbeefdead.json"
    legacy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "deadbeefdead",
                "created_at": "2026-01-01T00:00:00Z",
                "source": {"scenario": "旧", "goal": "格式"},
                "template": {
                    "name": "旧",
                    "system_prompt": "s",
                    "user_prompt_template": "{a}",
                    "variables": ["a"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    items = store.list_all()
    assert len(items) == 1


def test_optimize_with_prompt_flag_no_interactive_prompt(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--prompt 模式不应触发交互输入提示。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(
            json.dumps(
                {"optimized_prompt": "优化", "rationale": "说明"},
                ensure_ascii=False,
            )
        ),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "test"])
    assert result.exit_code == 0, result.output
    assert "输入提示词" not in result.output


def test_rich_markup_in_optimized_not_eaten(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """优化后 prompt 中的 Rich 标记应保留显示。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(
            json.dumps(
                {
                    "optimized_prompt": "保留 [red]标记[/red] 和 [bold]标题",
                    "rationale": "测试",
                },
                ensure_ascii=False,
            )
        ),
    )
    result = runner.invoke(app, ["optimize", "--prompt", "test"])
    assert result.exit_code == 0, result.output
    assert "[red]标记[/red]" in result.output
    assert "[bold]" in result.output

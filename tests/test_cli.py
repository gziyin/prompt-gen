"""CLI 测试:optimize / history / export / doctor。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.adapters.storage.repo_store import RepoStore
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
    assert "#1" in result.output
    assert "输入序号=查看详情" in result.output


def test_history_pagination(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超过一页时，回车翻到下一页，q 退出。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json(optimized="优化内容")),
    )
    for i in range(20):
        runner.invoke(app, ["optimize", "--prompt", f"原始内容{i:02d}"])
    result = runner.invoke(app, ["history"], input="\nq\n")
    assert result.exit_code == 0, result.output
    assert "原始内容19" in result.output  # 第一页（最新）
    assert "原始内容00" in result.output  # 第二页（最旧）


def test_history_detail_view(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """输入序号查看详情，显示完整优化后内容。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json(optimized="优化后的完整内容")),
    )
    runner.invoke(app, ["optimize", "--prompt", "原始内容"])
    result = runner.invoke(app, ["history"], input="1\n")
    assert result.exit_code == 0, result.output
    assert "原始内容" in result.output
    assert "优化后的完整内容" in result.output
    assert "记录详情" in result.output


def test_history_quit_exits_cleanly(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """q 正常退出 history 分页。"""
    monkeypatch.setattr(
        "prompt_gen.cli.build_deepseek_provider",
        lambda api_key, model: FakeLLM(_ok_json()),
    )
    runner.invoke(app, ["optimize", "--prompt", "原始内容"])
    result = runner.invoke(app, ["history"], input="q\n")
    assert result.exit_code == 0, result.output


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
    assert _resolve_choice("5") == ["repo"]


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
    assert _resolve_choice("仓库") == ["repo"]


def test_resolve_choice_command_name() -> None:
    assert _resolve_choice("optimize") == ["optimize"]
    assert _resolve_choice("history") == ["history"]
    assert _resolve_choice("export") == ["export"]
    assert _resolve_choice("doctor") == ["doctor"]
    assert _resolve_choice("repo") == ["repo"]
    assert _resolve_choice("repo list") == ["repo", "list"]


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


# -- _read_line_or_escape:交互输入行编辑(ESC/Ctrl+C 取消) --


def test_read_line_returns_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """prompt_toolkit 正常返回字符串。"""
    import prompt_toolkit

    monkeypatch.setattr(prompt_toolkit, "prompt", lambda *a, **kw: "hello world")
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") == "hello world"


def test_read_line_esc_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """ESC 时 prompt() 返回 None(表示取消)。

    真实行为:ESC 触发 event.app.exit(result=None),prompt() 干净
    返回 None(不在 handler 里抛异常)。这里直接模拟该返回值。
    """
    import prompt_toolkit

    monkeypatch.setattr(prompt_toolkit, "prompt", lambda *a, **kw: None)
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") is None


def test_read_line_ctrl_c_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl+C(KeyboardInterrupt)返回 None。"""
    import prompt_toolkit

    def _raise_ki(*a, **kw):  # noqa: ANN002, ANN003
        raise KeyboardInterrupt

    monkeypatch.setattr(prompt_toolkit, "prompt", _raise_ki)
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") is None


def test_read_line_eof_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl+D(EOFError)返回 None。"""
    import prompt_toolkit

    def _raise_eof(*a, **kw):  # noqa: ANN002, ANN003
        raise EOFError

    monkeypatch.setattr(prompt_toolkit, "prompt", _raise_eof)
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") is None


def test_read_line_fallback_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """prompt_toolkit 不可用时退化回 input()。"""
    import sys

    monkeypatch.setitem(sys.modules, "prompt_toolkit", None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "fallback-value")
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") == "fallback-value"


def test_read_line_fallback_ctrl_c_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """回退分支中 Ctrl+C 同样返回 None。"""
    import sys

    monkeypatch.setitem(sys.modules, "prompt_toolkit", None)

    def _raise_ki(prompt=""):  # noqa: ANN001
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _raise_ki)
    from prompt_gen.cli import _read_line_or_escape

    assert _read_line_or_escape("x: ") is None


# -- prompt 仓库 --

REPO_DIR_HINT = "history"  # cli_env 中 PROMPT_GEN_DATA_DIR 的子目录名


def _repo_store(cli_env: Path) -> RepoStore:
    return RepoStore(cli_env / "history")


def test_repo_add_with_all_params_saves(cli_env: Path) -> None:
    result = runner.invoke(
        app,
        ["repo", "add", "--name", "代码审查", "--content", "请审查",
         "--group", "项目A"],
    )
    assert result.exit_code == 0, result.output
    assert "已保存" in result.output
    store = _repo_store(cli_env)
    items = store.list_all()
    assert len(items) == 1
    assert items[0].name == "代码审查"
    assert items[0].group == "项目A"


def test_repo_add_missing_name_exits_2(cli_env: Path) -> None:
    result = runner.invoke(
        app, ["repo", "add", "--content", "正文"]
    )
    assert result.exit_code == 2


def test_repo_list_empty(cli_env: Path) -> None:
    result = runner.invoke(app, ["repo", "list"])
    assert result.exit_code == 0, result.output
    assert "暂无" in result.output


def test_repo_list_lists_records(cli_env: Path) -> None:
    runner.invoke(
        app, ["repo", "add", "--name", "代码审查", "--content", "审查正文",
              "--group", "项目A"]
    )
    result = runner.invoke(app, ["repo", "list"])
    assert result.exit_code == 0, result.output
    assert "代码审查" in result.output
    assert "项目A" in result.output


def test_repo_list_group_filter(cli_env: Path) -> None:
    runner.invoke(
        app, ["repo", "add", "--name", "A", "--content", "x", "--group", "组1"]
    )
    runner.invoke(
        app, ["repo", "add", "--name", "B", "--content", "y", "--group", "组2"]
    )
    result = runner.invoke(app, ["repo", "list", "--group", "组1"])
    assert result.exit_code == 0, result.output
    assert "A" in result.output
    assert "B" not in result.output


def test_repo_search_finds_match(cli_env: Path) -> None:
    runner.invoke(
        app, ["repo", "add", "--name", "代码审查", "--content", "检查质量"]
    )
    result = runner.invoke(app, ["repo", "search", "审查"])
    assert result.exit_code == 0, result.output
    assert "代码审查" in result.output


def test_repo_search_no_match(cli_env: Path) -> None:
    result = runner.invoke(app, ["repo", "search", "不存在词"])
    assert result.exit_code == 0, result.output
    assert "未找到" in result.output


def test_repo_groups_lists_empty_group(cli_env: Path) -> None:
    result = runner.invoke(app, ["repo", "group", "add", "项目A"])
    assert result.exit_code == 0, result.output
    assert "已创建分组" in result.output
    out = runner.invoke(app, ["repo", "groups"])
    assert out.exit_code == 0, out.output
    assert "项目A" in out.output


def test_repo_show_and_delete(cli_env: Path) -> None:
    runner.invoke(
        app, ["repo", "add", "--name", "代码审查", "--content", "正文"]
    )
    store = _repo_store(cli_env)
    repo_id = store.list_all()[0].id
    show = runner.invoke(app, ["repo", "show", repo_id])
    assert show.exit_code == 0, show.output
    assert "代码审查" in show.output
    dele = runner.invoke(app, ["repo", "delete", repo_id])
    assert dele.exit_code == 0, dele.output
    assert store.list_all() == []


def test_repo_show_nonexistent_exits_3(cli_env: Path) -> None:
    result = runner.invoke(app, ["repo", "show", "abcdef123456"])
    assert result.exit_code == 3


def test_repo_group_rename_updates(cli_env: Path) -> None:
    runner.invoke(
        app, ["repo", "add", "--name", "A", "--content", "x", "--group", "旧组"]
    )
    result = runner.invoke(app, ["repo", "group", "rename", "旧组", "新组"])
    assert result.exit_code == 0, result.output
    store = _repo_store(cli_env)
    assert store.list_all()[0].group == "新组"
    assert "新组" in store.list_groups()


def test_repo_interactive_browse_add(cli_env: Path) -> None:
    """交互浏览:分组屏选 1(全部,空)→ 提示无 → n 新增 → q 退出。"""
    result = runner.invoke(app, ["repo"], input="1\nq\n")
    assert result.exit_code == 0, result.output
    assert "prompt 仓库" in result.output

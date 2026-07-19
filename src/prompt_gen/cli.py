"""Typer CLI:optimize / history / export / doctor + 交互菜单。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_gen import __version__
from prompt_gen.adapters.llm.deepseek import build_deepseek_provider
from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.config import _find_project_root, load_settings
from prompt_gen.domain.optimizer import PromptOptimizer
from prompt_gen.exceptions import (
    ConfigurationError,
    PromptDataError,
    PromptGenerationError,
    PromptNotFoundError,
)
from prompt_gen.formatter import format_export_markdown, format_history_rows
from prompt_gen.ui_theme import PANEL_STYLE, THEME

PLACEHOLDER_KEYS = frozenset({"sk-your-key-here", "your-key-here", ""})


def _configure_stdio() -> None:
    """尽量让 Windows 终端正确显示中文。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass


_configure_stdio()

app = typer.Typer(
    name="prompt-gen",
    help="本地提示词优化器:输入 prompt,输出优化后 prompt + 说明。",
    no_args_is_help=False,
    add_completion=False,
)
console = Console(theme=THEME)
err_console = Console(stderr=True, theme=THEME)


def _exit_config(message: str) -> None:
    err_console.print(f"[red]配置错误:[/red] {message}")
    _print_setup_hint()
    raise typer.Exit(code=2)


def _exit_input(message: str) -> None:
    err_console.print(f"[red]输入错误:[/red] {message}")
    raise typer.Exit(code=2)


def _exit_data(message: str) -> None:
    err_console.print(f"[red]数据错误:[/red] {message}")
    raise typer.Exit(code=3)


def _exit_api(message: str) -> None:
    err_console.print(f"[red]模型错误:[/red] {message}")
    raise typer.Exit(code=4)


def _print_setup_hint() -> None:
    root = _find_project_root() or Path.cwd()
    err_console.print(
        Panel(
            "\n".join(
                [
                    "快速配置:",
                    f"  1. 复制环境文件: Copy-Item .env.example .env",
                    f"     (项目目录: {root})",
                    "  2. 编辑 .env,填入真实 DEEPSEEK_API_KEY",
                    "  3. 运行: prompt-gen doctor   # 检查环境",
                    "  4. 运行: prompt-gen          # 打开引导菜单",
                    "  或双击: start.bat / 执行 .\\start.ps1",
                ]
            ),
            title="上手提示",
            border_style="yellow",
            style=PANEL_STYLE,
        )
    )


def _store_from_settings(require_api_key: bool = False) -> tuple[HistoryStore, Path]:
    try:
        settings = load_settings(require_api_key=require_api_key)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        raise  # pragma: no cover
    return HistoryStore(settings.data_dir), settings.export_dir


def _print_welcome() -> None:
    body = Text()
    body.append("本地提示词优化器 · 终端工作台\n", style="subtitle")
    body.append("流程:", style="workflow")
    body.append("输入 prompt → DeepSeek 优化 → 存入历史 → 导出\n", style="flow")
    body.append("只需一段提示词,LLM 帮你优化并说明改动\n", style="text")
    console.print(
        Panel(
            body,
            title=f"[brand]✦ prompt-gen v{__version__}[/brand]",
            border_style="cyan",
            style=PANEL_STYLE,
        )
    )


def _print_menu() -> None:
    items = [
        ("1", "优化提示词"),
        ("2", "历史记录"),
        ("3", "导出为 Markdown"),
        ("4", "检查环境配置 (doctor)"),
        ("0", "退出"),
    ]
    lines: list[Text] = []
    for key, label in items:
        line = Text()
        line.append(f"[{key}] ", style="key")
        line.append(label, style="text")
        lines.append(line)
    console.print(Group(*lines))
    console.print(
        "[muted]也可直接: prompt-gen optimize | history | export <id> | doctor[/muted]"
    )


def _render_optimized(raw_prompt: str, optimized: str, rationale: str | None) -> Panel:
    """优化结果面板:原始 / 优化后 / 说明。"""
    raw_block = Panel(
        Text(raw_prompt, style="user_text"),
        border_style="muted",
        padding=(1, 1),
        style=PANEL_STYLE,
    )
    opt_block = Panel(
        Text(optimized, style="sys_text"),
        border_style="muted",
        padding=(1, 1),
        style=PANEL_STYLE,
    )

    content_parts: list = [
        Text("原始提示词", style="user_label"),
        raw_block,
        Text(),
        Text("优化后提示词", style="sys_label"),
        opt_block,
    ]

    if rationale:
        content_parts.append(Text())
        content_parts.append(Text("优化说明", style="sys_label"))
        content_parts.append(
            Panel(
                Text(rationale, style="text"),
                border_style="muted",
                padding=(1, 1),
                style=PANEL_STYLE,
            )
        )

    title = Text()
    title.append("✓ 已优化", style="cyan")
    return Panel(Group(*content_parts), title=title, border_style="cyan", style=PANEL_STYLE)


def run_interactive_menu() -> None:
    """无子命令时进入引导菜单。"""
    _print_welcome()
    console.print()
    while True:
        _print_menu()
        choice = typer.prompt("请选择", default="1").strip()
        if choice in {"0", "q", "quit", "exit"}:
            console.print("已退出。下次可运行 [bold]prompt-gen[/bold] 或 [bold].\\start.ps1[/bold]。")
            return
        if choice == "1":
            _typer_invoke(["optimize"])
            continue
        if choice == "2":
            _typer_invoke(["history"])
            continue
        if choice == "3":
            record_id = typer.prompt("记录 ID(可先 history 查看)").strip()
            if record_id:
                _typer_invoke(["export", record_id])
            continue
        if choice == "4":
            _typer_invoke(["doctor"])
            continue
        err_console.print("[yellow]无效选项,请输入 0-4。[/yellow]")


def _typer_invoke(args: list[str]) -> None:
    """菜单内调用子命令;捕获 Exit 以免打断菜单循环。"""
    try:
        app(args, standalone_mode=False)
    except typer.Exit as exc:
        if exc.exit_code not in (0, None):
            err_console.print(f"[dim]命令结束,退出码 {exc.exit_code}[/dim]")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        if code not in (0, None):
            err_console.print(f"[dim]命令结束,退出码 {code}[/dim]")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """本地提示词优化器。无参数时打开引导菜单。"""
    if ctx.invoked_subcommand is None:
        run_interactive_menu()


@app.command()
def optimize(
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="要优化的提示词(不传则交互输入)",
    ),
) -> None:
    """优化提示词:输入一段 prompt,输出优化后 prompt + 说明。"""
    if prompt is None:
        console.print(
            Panel(
                "请输入要优化的提示词(单行,回车提交):\n"
                "LLM 会分析问题、输出优化版、说明改动。",
                title="优化提示词",
                border_style="green",
                style=PANEL_STYLE,
            )
        )
        console.print()
        prompt = typer.prompt("输入提示词").strip()
    else:
        # 参数模式:strip 后由统一校验处理
        prompt = prompt.strip()

    # 统一校验(交互或参数模式):空白视为空
    if not prompt:
        _exit_input("提示词不能为空")
        return

    try:
        settings = load_settings(require_api_key=True)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        return

    provider = build_deepseek_provider(settings.api_key, settings.model)
    optimizer = PromptOptimizer(provider)

    try:
        with console.status(
            "[cyan]正在调用 DeepSeek 优化提示词…[/cyan]", spinner="dots"
        ):
            optimized, rationale = optimizer.optimize(prompt)
    except PromptGenerationError as exc:
        _exit_api(str(exc))
        return

    store = HistoryStore(settings.data_dir)
    try:
        record = store.save(
            raw_prompt=prompt,
            optimized_prompt=optimized,
            rationale=rationale,
            model=settings.model,
        )
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    console.print(_render_optimized(prompt, optimized, rationale))
    console.print()
    console.print(f"[muted]已保存:[/muted] {store.data_dir / f'{record.id}.json'}")
    console.print()
    console.print(
        f"下一步: [brand]prompt-gen history[/brand]  ·  "
        f"[brand]prompt-gen export {record.id}[/brand]"
    )
    console.print()


@app.command("history")
def history_cmd() -> None:
    """按创建时间倒序列出优化历史。"""
    store, _ = _store_from_settings(require_api_key=False)
    try:
        items = store.list_all()
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    if not items:
        console.print(
            Panel(
                "暂无优化记录。\n\n"
                "开始优化:\n"
                "  · [bold]prompt-gen optimize[/bold]  交互输入\n"
                "  · [bold]prompt-gen[/bold]            打开引导菜单\n"
                "  · [bold].\\start.ps1[/bold]          一键启动",
                title="空列表",
                border_style="yellow",
                style=PANEL_STYLE,
            )
        )
        return

    rows = format_history_rows(items)
    table = Table(
        title=f"[brand]优化历史[/brand]  [muted]({len(items)})[/muted]",
        show_header=True,
        header_style="bold",
        title_justify="left",
    )
    table.add_column("ID", style="key", no_wrap=True)
    table.add_column("原始提示词", style="user_text", no_wrap=True)
    table.add_column("优化后提示词", style="sys_text", no_wrap=True)
    table.add_column("创建时间", style="muted", no_wrap=True)
    for record_id, raw_preview, opt_preview, ts in rows:
        table.add_row(record_id, raw_preview, opt_preview, ts)
    console.print(table)
    console.print()
    console.print("[muted]导出: prompt-gen export <id>[/muted]")
    console.print()


@app.command()
def export(
    record_id: str = typer.Argument(..., help="优化记录 ID(可用 history 查看)"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="导出路径;默认 exports/<id>.md",
    ),
) -> None:
    """导出指定优化记录为对话式 Markdown。"""
    store, export_dir = _store_from_settings(require_api_key=False)
    try:
        record = store.load(record_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    text = format_export_markdown(record)
    target = output if output is not None else (export_dir / f"{record.id}.md")
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    console.print(f"[green]已导出:[/green] {target}")
    console.print()
    console.print("[dim]可用编辑器打开该 Markdown,或继续 prompt-gen history[/dim]")
    console.print()


@app.command()
def doctor() -> None:
    """检查 .env、API Key、数据目录与优化记录数量。"""
    root = _find_project_root() or Path.cwd()
    env_path = root / ".env"
    example_path = root / ".env.example"

    try:
        settings = load_settings(require_api_key=False)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        return

    api_key = (os.getenv("DEEPSEEK_API_KEY") or settings.api_key or "").strip()
    key_ok = bool(api_key) and api_key not in PLACEHOLDER_KEYS

    rows: list[tuple[str, str, str]] = []
    rows.append(("项目目录", "OK" if root.exists() else "缺", str(root)))
    rows.append(
        (
            ".env 文件",
            "OK" if env_path.is_file() else "缺",
            str(env_path) if env_path.is_file() else f"请复制 {example_path.name}",
        )
    )
    rows.append(
        (
            "API Key",
            "OK" if key_ok else "缺",
            "已配置" if key_ok else "请在 .env 填写 DEEPSEEK_API_KEY",
        )
    )
    rows.append(("模型", "OK", settings.model))

    store = HistoryStore(settings.data_dir)
    try:
        count = len(store.list_all())
        data_status = "OK"
        data_detail = f"{settings.data_dir}({count} 条记录)"
    except PromptDataError as exc:
        data_status = "损"
        data_detail = str(exc)
        count = -1

    rows.append(("数据目录", data_status, data_detail))
    rows.append(("导出目录", "OK", str(settings.export_dir)))

    table = Table(title="[brand]环境检查[/brand]", show_header=True, header_style="bold")
    table.add_column("项目")
    table.add_column("状态", width=4, justify="center")
    table.add_column("说明")
    for name, status, detail in rows:
        ok = status == "OK"
        style = "ok" if ok else "bad"
        glyph = "✓" if ok else "✗"
        table.add_row(name, Text(glyph, style=style), f"[{style}]{status}[/]  {detail}")
    console.print(table)
    console.print()

    if not key_ok:
        console.print(
            "\n[yellow]优化功能需要 API Key。[/yellow] 配置完成后运行:"
            " [bold]prompt-gen optimize[/bold] 或 [bold]prompt-gen[/bold]"
        )
        raise typer.Exit(code=2)

    console.print(
        "\n[green]环境就绪。[/green] 下一步:"
        " [bold]prompt-gen[/bold] 打开菜单,或 [bold]prompt-gen optimize[/bold] 开始优化"
    )


if __name__ == "__main__":
    app()

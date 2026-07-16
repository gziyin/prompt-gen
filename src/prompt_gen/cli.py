"""Typer CLI：generate / list / show / export + 交互菜单。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_gen import __version__
from prompt_gen.config import _find_project_root, load_settings
from prompt_gen.exceptions import (
    ConfigurationError,
    PromptDataError,
    PromptGenerationError,
    PromptNotFoundError,
)
from prompt_gen.formatter import (
    format_detail_text,
    format_export_markdown,
    format_list_rows,
)
from prompt_gen.generator import build_deepseek_generator
from prompt_gen.models import PromptRequest
from prompt_gen.store import PromptStore

PLACEHOLDER_KEYS = frozenset({"sk-your-key-here", "your-key-here", ""})

DEMO_EXAMPLES = (
    ("代码审查", "找出可靠性问题", "Python 开发者", "只评代码, 给出可复现步骤"),
    ("商务邮件", "语气更专业简洁", "职场同事", "保留原意, 不超过原文1.2倍"),
    ("学习笔记", "提炼要点与待办", "自己", "分条输出, 标注不确定处"),
)


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
    help="本地提示词生成器：根据场景生成结构化提示词模板。",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


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
                    "快速配置：",
                    f"  1. 复制环境文件: Copy-Item .env.example .env",
                    f"     （项目目录: {root}）",
                    "  2. 编辑 .env，填入真实 DEEPSEEK_API_KEY",
                    "  3. 运行: prompt-gen doctor   # 检查环境",
                    "  4. 运行: prompt-gen          # 打开引导菜单",
                    "  或双击: start.bat / 执行 .\\start.ps1",
                ]
            ),
            title="上手提示",
            border_style="yellow",
        )
    )


def _store_from_settings(require_api_key: bool = False) -> tuple[PromptStore, Path]:
    try:
        settings = load_settings(require_api_key=require_api_key)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        raise  # pragma: no cover
    return PromptStore(settings.data_dir), settings.export_dir


def _guided_prompt(
    label: str,
    *,
    example: str,
    required: bool = True,
    default: str = "",
) -> Optional[str]:
    hint = f"{label} [例: {example}]"
    if not required:
        entered = typer.prompt(hint, default=default, show_default=False)
        return entered.strip() or None
    while True:
        entered = typer.prompt(hint, default=default, show_default=bool(default))
        entered = entered.strip()
        if entered:
            return entered
        err_console.print(f"[yellow]{label} 不能为空，请重新输入。[/yellow]")


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", ()))
        msg = err.get("msg", "无效")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else str(exc)


def _print_welcome() -> None:
    lines = [
        f"prompt-gen v{__version__} · 本地提示词生成器",
        "",
        "流程：填写场景 → DeepSeek 生成模板 → 本地保存 → 查看/导出",
        "",
        "演示场景：",
    ]
    for scenario, goal, audience, constraints in DEMO_EXAMPLES:
        lines.append(f"  · {scenario} / {goal} / {audience}")
        lines.append(f"    约束: {constraints}")
    console.print(Panel("\n".join(lines), title="欢迎", border_style="cyan"))


def _print_menu() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", width=4)
    table.add_column()
    table.add_row("1", "交互生成模板（推荐新手）")
    table.add_row("2", "列出本地模板")
    table.add_row("3", "查看模板详情")
    table.add_row("4", "导出为 Markdown")
    table.add_row("5", "检查环境配置 (doctor)")
    table.add_row("0", "退出")
    console.print(table)
    console.print("[dim]也可直接: prompt-gen generate | list | show | export | doctor[/dim]")


def run_interactive_menu() -> None:
    """无子命令时进入引导菜单。"""
    _print_welcome()
    while True:
        _print_menu()
        choice = typer.prompt("请选择", default="1").strip()
        if choice in {"0", "q", "quit", "exit"}:
            console.print("已退出。下次可运行 [bold]prompt-gen[/bold] 或 [bold].\\start.ps1[/bold]。")
            return
        if choice == "1":
            _typer_invoke(["generate"])
            continue
        if choice == "2":
            _typer_invoke(["list"])
            continue
        if choice == "3":
            prompt_id = typer.prompt("模板 ID（可先 list 查看）").strip()
            if prompt_id:
                _typer_invoke(["show", prompt_id])
            continue
        if choice == "4":
            prompt_id = typer.prompt("模板 ID（可先 list 查看）").strip()
            if prompt_id:
                _typer_invoke(["export", prompt_id])
            continue
        if choice == "5":
            _typer_invoke(["doctor"])
            continue
        err_console.print("[yellow]无效选项，请输入 0-5。[/yellow]")


def _typer_invoke(args: list[str]) -> None:
    """菜单内调用子命令；捕获 Exit 以免打断菜单循环。"""
    try:
        app(args, standalone_mode=False)
    except typer.Exit as exc:
        if exc.exit_code not in (0, None):
            err_console.print(f"[dim]命令结束，退出码 {exc.exit_code}[/dim]")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        if code not in (0, None):
            err_console.print(f"[dim]命令结束，退出码 {code}[/dim]")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """本地提示词生成器。无参数时打开引导菜单。"""
    if ctx.invoked_subcommand is None:
        run_interactive_menu()


@app.command()
def doctor() -> None:
    """检查 .env、API Key、数据目录与模板数量。"""
    root = _find_project_root() or Path.cwd()
    env_path = root / ".env"
    example_path = root / ".env.example"

    # 加载但不强制 Key
    try:
        settings = load_settings(require_api_key=False)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        return

    api_key = (os.getenv("DEEPSEEK_API_KEY") or settings.api_key or "").strip()
    key_ok = bool(api_key) and api_key not in PLACEHOLDER_KEYS

    rows: list[tuple[str, str, str]] = []
    rows.append(
        (
            "项目目录",
            "OK" if root.exists() else "缺",
            str(root),
        )
    )
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

    store = PromptStore(settings.data_dir)
    try:
        count = len(store.list_all())
        data_status = "OK"
        data_detail = f"{settings.data_dir}（{count} 个模板）"
    except PromptDataError as exc:
        data_status = "损"
        data_detail = str(exc)
        count = -1

    rows.append(("数据目录", data_status, data_detail))
    rows.append(
        (
            "导出目录",
            "OK",
            str(settings.export_dir),
        )
    )

    table = Table(title="环境检查", show_header=True, header_style="bold")
    table.add_column("项目")
    table.add_column("状态", width=4)
    table.add_column("说明")
    for name, status, detail in rows:
        style = "green" if status == "OK" else "red"
        table.add_row(name, f"[{style}]{status}[/{style}]", detail)
    console.print(table)

    if not key_ok:
        console.print(
            "\n[yellow]生成功能需要 API Key。[/yellow] 配置完成后运行："
            " [bold]prompt-gen generate[/bold] 或 [bold]prompt-gen[/bold]"
        )
        raise typer.Exit(code=2)

    console.print(
        "\n[green]环境就绪。[/green] 下一步："
        " [bold]prompt-gen[/bold] 打开菜单，或 [bold]prompt-gen generate[/bold] 开始生成"
    )


@app.command()
def generate(
    scenario: Optional[str] = typer.Option(None, "--scenario", "-s", help="使用场景"),
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="生成目标"),
    audience: Optional[str] = typer.Option(None, "--audience", "-a", help="目标受众"),
    constraint: list[str] = typer.Option(
        [],
        "--constraint",
        "-c",
        help="约束条件，可重复传入",
    ),
    language: str = typer.Option("zh-CN", "--language", "-l", help="输出语言"),
) -> None:
    """交互或参数方式生成提示词模板并保存。"""
    interactive = scenario is None and goal is None and audience is None and not constraint

    if interactive:
        console.print(
            Panel(
                "\n".join(
                    [
                        "请按提示填写（可直接参考示例）：",
                        *(
                            f"  · {s} → {g} → {a}"
                            for s, g, a, _ in DEMO_EXAMPLES
                        ),
                        "",
                        "受众与约束可留空；约束多个时用英文逗号分隔。",
                    ]
                ),
                title="交互生成",
                border_style="green",
            )
        )
        scenario_v = _guided_prompt("场景", example="代码审查")
        goal_v = _guided_prompt("目标", example="找出可靠性问题")
        audience_v = _guided_prompt(
            "受众",
            example="Python 开发者",
            required=False,
        )
        raw = _guided_prompt(
            "约束",
            example="只评代码, 给出可复现步骤",
            required=False,
            default="",
        )
        constraints = (
            [part.strip() for part in (raw or "").split(",") if part.strip()]
            if raw
            else []
        )
    else:
        if scenario is None or not scenario.strip():
            _exit_input("请使用 --scenario 指定场景（不能为空）")
        if goal is None or not goal.strip():
            _exit_input("请使用 --goal 指定目标（不能为空）")
        scenario_v = scenario.strip()
        goal_v = goal.strip()
        audience_v = audience.strip() if audience and audience.strip() else None
        constraints = list(constraint)

    try:
        request = PromptRequest(
            scenario=scenario_v or "",
            goal=goal_v or "",
            audience=audience_v,
            constraints=constraints,
            language=language,
        )
    except ValidationError as exc:
        _exit_input(_format_validation_error(exc))
        return
    except Exception as exc:  # noqa: BLE001
        _exit_input(str(exc))
        return

    try:
        settings = load_settings(require_api_key=True)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        return

    console.print("[dim]正在调用 DeepSeek 生成结构化模板…[/dim]")
    gen = build_deepseek_generator(settings)
    try:
        template = gen.generate(request)
    except PromptGenerationError as exc:
        _exit_api(str(exc))
        return

    store = PromptStore(settings.data_dir)
    try:
        stored = store.save(request, template)
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    console.print(
        Panel(
            Text(format_export_markdown(stored).rstrip()),
            title=Text(f"已生成 · {stored.id}"),
            border_style="green",
        )
    )
    console.print(f"已保存: {store.data_dir / f'{stored.id}.json'}")
    console.print(
        f"下一步: [bold]prompt-gen show {stored.id}[/bold]  ·  "
        f"[bold]prompt-gen export {stored.id}[/bold]  ·  "
        f"[bold]prompt-gen list[/bold]"
    )


@app.command("list")
def list_prompts() -> None:
    """按创建时间倒序列出本地模板。"""
    store, _ = _store_from_settings(require_api_key=False)
    try:
        items = store.list_all()
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    if not items:
        console.print(
            Panel(
                "暂无模板。\n\n"
                "开始生成：\n"
                "  · [bold]prompt-gen generate[/bold]  交互填写\n"
                "  · [bold]prompt-gen[/bold]           打开引导菜单\n"
                "  · [bold].\\start.ps1[/bold]         一键启动",
                title="空列表",
                border_style="yellow",
            )
        )
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("名称")
    table.add_column("创建时间", style="dim", no_wrap=True)
    for prompt_id, name, created in format_list_rows(items):
        table.add_row(prompt_id, name, created)
    console.print(table)
    console.print(
        "[dim]查看: prompt-gen show <id>  ·  导出: prompt-gen export <id>[/dim]"
    )


@app.command()
def show(prompt_id: str = typer.Argument(..., help="模板 ID（可用 list 查看）")) -> None:
    """展示完整来源输入与模板内容。"""
    store, _ = _store_from_settings(require_api_key=False)
    try:
        stored = store.load(prompt_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    console.print(
        Panel(
            Text(format_detail_text(stored).rstrip()),
            title=Text(stored.template.name),
            border_style="cyan",
        )
    )
    console.print(
        f"[dim]导出: prompt-gen export {stored.id}[/dim]"
    )


@app.command("export")
def export_prompt(
    prompt_id: str = typer.Argument(..., help="模板 ID（可用 list 查看）"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="导出路径；默认 exports/<id>.md",
    ),
) -> None:
    """导出为 Markdown 文本。"""
    store, export_dir = _store_from_settings(require_api_key=False)
    try:
        stored = store.load(prompt_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    text = format_export_markdown(stored)
    target = output if output is not None else (export_dir / f"{stored.id}.md")
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    console.print(f"[green]已导出:[/green] {target}")
    console.print("[dim]可用编辑器打开该 Markdown，或继续 prompt-gen list[/dim]")


if __name__ == "__main__":
    app()

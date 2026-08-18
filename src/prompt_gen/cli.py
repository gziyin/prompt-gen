"""Typer CLI:optimize / history / export / doctor + 交互菜单。"""

from __future__ import annotations

import os
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import typer
from rich import box
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_gen import __version__
from prompt_gen.adapters.llm.deepseek import build_deepseek_provider
from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.adapters.storage.repo_store import RepoStore
from prompt_gen.config import _find_project_root, load_settings
from prompt_gen.domain.models import OptimizationRecord, RepoPrompt
from prompt_gen.domain.optimizer import PromptOptimizer
from prompt_gen.exceptions import (
    ConfigurationError,
    PromptDataError,
    PromptGenerationError,
    PromptNotFoundError,
)
from prompt_gen.formatter import format_export_markdown
from prompt_gen.ui_theme import PANEL_STYLE, THEME

PLACEHOLDER_KEYS = frozenset({"sk-your-key-here", "your-key-here", ""})

_HISTORY_PAGE_SIZE = 15  # 历史记录每页条数


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
                    "  或双击: scripts\\start.bat / 执行 .\\scripts\\start.ps1",
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


def _repo_store_from_settings(
    require_api_key: bool = False,
) -> tuple[RepoStore, Path]:
    try:
        settings = load_settings(require_api_key=require_api_key)
    except ConfigurationError as exc:
        _exit_config(str(exc))
        raise  # pragma: no cover
    return RepoStore(settings.data_dir), settings.export_dir


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
        ("5", "提示词仓库"),
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
        "[muted]也可直接: prompt-gen optimize | history | export <id> | doctor | repo[/muted]"
    )


def _render_optimized(raw_prompt: str, optimized: str, rationale: str | None) -> Panel:
    """优化结果面板:原始 / 优化后 / 说明。

    复制友好设计:内部文本区域不用 Panel 框线包裹(鼠标选中复制
    不带入 │ ╭ ╰ 等字符),改用"标签 + 左缩进内容"的纯文本排版;
    外层容器用 box.HORIZONTALS(仅顶/底 ─ 横线)保留视觉起止边界。
    """
    content_parts: list = [
        Text("原始提示词", style="user_label"),
        Padding(Text(raw_prompt, style="user_text"), (0, 0, 0, 2)),
        Text(),
        Text("优化后提示词", style="sys_label"),
        Padding(Text(optimized, style="sys_text"), (0, 0, 0, 2)),
    ]

    if rationale:
        content_parts.append(Text())
        content_parts.append(Text("优化说明", style="sys_label"))
        content_parts.append(Padding(Text(rationale, style="text"), (0, 0, 0, 2)))

    title = Text()
    title.append("✓ 已优化", style="cyan")
    return Panel(
        Group(*content_parts),
        title=title,
        border_style="cyan",
        box=box.HORIZONTALS,
        style=PANEL_STYLE,
    )


def _resolve_choice(choice: str) -> list[str] | None:
    """将菜单输入解析为子命令参数列表,无法识别返回 None。

    支持多种输入形式:
    - 数字快捷键:1/2/3/4/0
    - 中文:优化/历史/导出/检查/退出
    - 命令名:optimize/history/export/doctor
    - 完整命令:prompt-gen optimize / prompt-gen export <id>
    """
    choice = choice.strip()
    if not choice:
        return None

    # 退出
    if choice in {"0", "q", "quit", "exit", "退出"}:
        return ["__exit__"]

    # 数字 / 中文快捷键
    quick_map = {
        "1": ["optimize"],
        "2": ["history"],
        "3": ["export"],
        "4": ["doctor"],
        "5": ["repo"],
        "优化": ["optimize"],
        "历史": ["history"],
        "导出": ["export"],
        "检查": ["doctor"],
        "仓库": ["repo"],
    }
    if choice in quick_map:
        return quick_map[choice]

    # 去掉 prompt-gen 前缀(支持 "prompt-gen optimize" 形式)
    if choice.startswith("prompt-gen "):
        choice = choice[len("prompt-gen "):].strip()
    elif choice == "prompt-gen":
        return None

    # 解析 "命令 [参数...]" 形式
    parts = choice.split()
    if not parts:
        return None

    cmd_map = {
        "optimize": "optimize",
        "history": "history",
        "export": "export",
        "doctor": "doctor",
        "repo": "repo",
    }
    cmd = parts[0]
    if cmd in cmd_map:
        return [cmd_map[cmd]] + parts[1:]

    return None


def run_interactive_menu() -> None:
    """无子命令时进入引导菜单。

    支持数字快捷键、中文、命令名、完整命令(prompt-gen xxx)四种输入形式。
    子命令执行后暂停,按 ESC 或回车返回菜单。
    """
    _print_welcome()
    console.print()
    while True:
        _print_menu()
        choice = typer.prompt("请选择").strip()
        resolved = _resolve_choice(choice)
        if resolved is None:
            err_console.print(
                "[yellow]无效选项,请输入 0-5 或命令名(optimize/history/export/doctor/repo)。[/yellow]"
            )
            console.print()
            continue
        if resolved == ["__exit__"]:
            console.print("已退出。下次可运行 [bold]prompt-gen[/bold] 或 [bold].\\scripts\\start.ps1[/bold]。")
            return
        # export 需要 ID,若未提供则交互询问
        if resolved[0] == "export" and len(resolved) == 1:
            entered = _read_line_or_escape("记录 ID(可先 history 查看): ")
            if entered is None:
                console.print("[muted]已取消,返回菜单…[/muted]")
                console.print()
                continue
            record_id = entered.strip()
            if record_id:
                _typer_invoke(["export", record_id])
                _pause_for_menu()
            continue
        _typer_invoke(resolved)
        _pause_for_menu()


def _pause_for_menu(hint: str = "按 ESC 或回车返回菜单…") -> None:
    """按键暂停返回,默认提示返回菜单;history 详情后用"返回列表"。

    跨平台实现:Windows 用 msvcrt,Unix 用 termios+tty。
    非交互环境(管道/CI/重定向)用 input() 兜底,不卡住。
    """
    console.print()
    console.print(f"[muted]{hint}[/muted]", end="")
    if not sys.stdin.isatty():
        # 非交互环境(管道/CI/CliRunner):直接 input() 兜底,EOF 即返回,
        # 避免 msvcrt.getch() 在无控制台时阻塞。
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        console.print()
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.getch()  # 读取任意单键(ESC/回车/其他均返回)
        else:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        # 真终端下按键读取异常时,退化 input()
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    console.print()


_CSI_U_PATCHED = False


def _patch_csi_u_shift_enter() -> None:
    """把终端发来的 Shift+Enter 序列翻译为换行。

    Windows Terminal 等现代终端对 Shift+Enter 发送 CSI-u(Kitty)序列
    ``ESC [ 13 ; 2 u``,而 prompt_toolkit 3.0.x 不解析它,会把
    ``^[[13;2u`` 逐字插入输入框,导致换行失效。这里在解析前将其替换为
    ``\\n``,从而让 ``c-j`` 键绑定正常插入换行。
    对发送 ``\\n`` 的终端无副作用(不匹配则原样通过)。
    """
    global _CSI_U_PATCHED
    if _CSI_U_PATCHED:
        return
    try:
        import prompt_toolkit.input.vt100_parser as _vt100
    except Exception:  # noqa: BLE001
        return
    _orig_feed = _vt100.Vt100Parser.feed

    def _feed(self, data):  # noqa: ANN001
        data = data.replace("\x1b[13;2u", "\n")  # Shift+Enter
        return _orig_feed(self, data)

    _vt100.Vt100Parser.feed = _feed
    _CSI_U_PATCHED = True


def _read_line_or_escape(prompt: str) -> str | None:
    """读取一行输入,ESC / Ctrl+C / Ctrl+D 返回 None 表示取消。

    优先使用 prompt_toolkit:获得完整行编辑(退格、左右方向键、
    Delete、Home/End、历史)与中文输入法支持,ESC 一键取消;
    Enter 确认,Shift+Enter 换行。
    prompt_toolkit 不可用或处于非交互环境(管道/CI/重定向)时,
    自动退化回标准 input()(此时仅支持系统自带行编辑,ESC 不可用,
    改用 Ctrl+C 取消)。

    注意:ESC 通过 event.app.exit(result=None) 让 prompt() 直接
    返回 None,不在 handler 里抛异常(否则会冒泡到 prompt_toolkit
    事件循环报 "Unhandled exception")。
    """
    _patch_csi_u_shift_enter()
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys

        kb = KeyBindings()

        @kb.add(Keys.Escape)
        def _on_esc(event):  # noqa: ANN001, ANN202
            event.app.exit(result=None)

        @kb.add(Keys.Enter)
        def _on_enter(event):  # noqa: ANN001, ANN202
            event.current_buffer.validate_and_handle()

        @kb.add(Keys.ControlJ)
        def _on_shift_enter(event):  # noqa: ANN001, ANN202
            event.current_buffer.insert_text("\n")

        return pt_prompt(
            prompt,
            key_bindings=kb,
            multiline=True,
            prompt_continuation=lambda *_: "",  # 续行不缩进,避免被推到提示符右侧
        )
    except (KeyboardInterrupt, EOFError):
        return None
    except Exception:  # noqa: BLE001
        # prompt_toolkit 不可用或非 tty:退化回 input()
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return None


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
                "请输入要优化的提示词(回车提交,Ctrl+J 换行):\n"
                "LLM 会分析问题、输出优化版、说明改动。",
                title="优化提示词",
                border_style="green",
                style=PANEL_STYLE,
            )
        )
        console.print()
        entered = _read_line_or_escape("输入提示词(Ctrl+J 换行): ")
        if entered is None:
            console.print("[muted]已取消,返回菜单…[/muted]")
            console.print()
            return
        prompt = entered.strip()
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


def _fmt_ts(dt: datetime) -> str:
    """统一为 UTC 后格式化为 YYYY-MM-DD HH:MM。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _truncate_preview(text: str, max_len: int) -> str:
    """单行预览,超长用省略号截断。"""
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _render_record_detail(record: OptimizationRecord) -> Panel:
    """单条记录详情面板:元信息 + 原始 + 优化后 + 说明。

    复用"✓ 已优化"排版风格(HORIZONTALS + 标签 + 左缩进),复制友好。
    """
    ts = _fmt_ts(record.created_at) + " UTC"
    meta_parts: list = [
        ("id: ", "muted"),
        (record.id, "dim"),
        ("   created_at: ", "muted"),
        (ts, "dim"),
    ]
    if record.model:
        meta_parts.extend([("   model: ", "muted"), (record.model, "dim")])
    meta = Text.assemble(*meta_parts)

    content_parts: list = [
        meta,
        Text(),
        Text("原始提示词", style="user_label"),
        Padding(Text(record.raw_prompt, style="user_text"), (0, 0, 0, 2)),
        Text(),
        Text("优化后提示词", style="sys_label"),
        Padding(Text(record.optimized_prompt, style="sys_text"), (0, 0, 0, 2)),
    ]
    if record.rationale:
        content_parts.append(Text())
        content_parts.append(Text("优化说明", style="sys_label"))
        content_parts.append(Padding(Text(record.rationale, style="text"), (0, 0, 0, 2)))

    title = Text("记录详情", style="cyan")
    return Panel(
        Group(*content_parts),
        title=title,
        border_style="cyan",
        box=box.HORIZONTALS,
        style=PANEL_STYLE,
    )


@app.command("history")
def history_cmd() -> None:
    """按创建时间倒序分页浏览优化历史,输入序号查看详情。"""
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
                "  · [bold].\\scripts\\start.ps1[/bold]          一键启动",
                title="空列表",
                border_style="yellow",
                style=PANEL_STYLE,
            )
        )
        return

    total = len(items)
    term_width = console.width or 80
    # 序号(#123+空格) + 时间(16) + ID(12) + 间隔 ≈ 37,预览取剩余,保底 20、上限 60
    preview_width = max(20, min(term_width - 37, 60))

    console.print()
    console.print(
        f"[bold brand]优化历史[/bold brand]  "
        f"[muted]({total} 条,最新在前,每页 {_HISTORY_PAGE_SIZE} 条)[/muted]"
    )
    console.print()

    page = 0
    while True:
        start = page * _HISTORY_PAGE_SIZE
        page_items = items[start : start + _HISTORY_PAGE_SIZE]
        for offset, record in enumerate(page_items):
            idx = start + offset + 1
            line = Text.assemble(
                (f"#{idx:<4}", "key"),
                (_fmt_ts(record.created_at), "muted"),
                "  ",
                (record.id, "dim"),
                "  ",
                (_truncate_preview(record.raw_prompt, preview_width), "user_text"),
            )
            console.print(line)

        has_next = start + _HISTORY_PAGE_SIZE < total
        has_prev = page > 0
        console.print()
        hints: list[str] = []
        if has_next:
            hints.append("回车=下一页")
        if has_prev:
            hints.append("b=上一页")
        hints.append("输入序号=查看详情")
        hints.append("q=退出")
        console.print(f"[muted]{'  ·  '.join(hints)}[/muted]")

        choice = _read_line_or_escape("> ")
        if choice is None:
            break
        choice = choice.strip()
        if choice == "":
            if has_next:
                page += 1
                console.print()
                continue
            break
        lower = choice.lower()
        if lower in {"q", "quit", "退出"}:
            break
        if lower in {"b", "prev", "上一页"}:
            if has_prev:
                page -= 1
                console.print()
            continue
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= total:
                console.print()
                console.print(_render_record_detail(items[n - 1]))
                console.print()
                _pause_for_menu("按 ESC 或回车返回列表…")
                console.print()
                continue
            err_console.print(f"[yellow]序号超出范围 (1-{total})[/yellow]")
            continue
        err_console.print(
            "[yellow]无效输入:回车翻页 / b 上一页 / 序号查看 / q 退出[/yellow]"
        )


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

    # 检查 prompt-gen 命令是否全局可用(无需激活 venv 即可调用)
    cmd_path = shutil.which("prompt-gen")
    if cmd_path:
        rows.append(("命令可用性", "OK", "prompt-gen 在 PATH 中,可直接调用"))
    else:
        rows.append(
            (
                "命令可用性",
                "缺",
                "需激活 venv 或将 .venv/Scripts 加入 PATH",
            )
        )

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

    # 命令不可用时提示 PATH 配置方法
    if not cmd_path:
        console.print(
            "\n[yellow]提示:[/yellow] 当前 [bold]prompt-gen[/bold] 命令需激活 venv 才能使用。"
            "若想全局可用,任选其一:\n"
            "  · 永久方案:将项目 [bold].venv\\Scripts[/bold] 目录加入用户 PATH\n"
            "  · 临时方案:每次先运行 [bold].\\.venv\\Scripts\\Activate.ps1[/bold]\n"
            "  · 后备方案:用 [bold]python -m prompt_gen[/bold] 替代"
        )


# ── prompt 仓库 ──────────────────────────────────────────

_REPO_PAGE_SIZE = 15  # 仓库列表每页条数


def _display_width(text: str) -> int:
    """按终端显示宽度计数(中文字符按 2 列),用于列对齐。"""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in text
    )


def _repo_separator() -> None:
    """整行分隔线,区分区块,避免文字扎堆。"""
    console.rule(style="dim")


def _repo_header(title: str, meta: str) -> None:
    """居中区块标题:品牌标题 + 分隔点 + 元信息。"""
    console.print()
    console.print(
        Text.assemble(
            ("◇ ", "dim"),
            (title, "brand"),
            ("  ·  ", "muted"),
            (meta, "muted"),
        ),
        justify="center",
    )
    _repo_separator()


def _scope_loader(store: RepoStore, label: str) -> Callable[[], list[RepoPrompt]]:
    """返回按范围(label)实时拉取提示词列表的函数。

    用于列表循环每次渲染前刷新,删除后不再回显已删项。
    """
    if label == "全部":
        return store.list_all
    if label == "未分组":
        return store.list_ungrouped
    return lambda: store.list_by_group(label)


def _render_repo_detail(prompt: RepoPrompt) -> Panel:
    """单条提示词详情面板,复用记录详情排版(HORIZONTALS + 标签 + 缩进)。"""
    meta_parts: list = [
        ("id: ", "muted"),
        (prompt.id, "dim"),
        ("   name: ", "muted"),
        (prompt.name, "dim"),
    ]
    if prompt.group:
        meta_parts.extend([("   group: ", "muted"), (prompt.group, "dim")])
    meta_parts.extend(
        [
            ("   created: ", "muted"),
            (_fmt_ts(prompt.created_at), "dim"),
            ("   updated: ", "muted"),
            (_fmt_ts(prompt.updated_at), "dim"),
        ]
    )
    meta = Text.assemble(*meta_parts)

    content_parts: list = [
        meta,
        Text(),
        Text(prompt.name, style="user_label"),
        Padding(Text(prompt.content, style="user_text"), (0, 0, 0, 2)),
    ]
    if prompt.description:
        content_parts.append(Text())
        content_parts.append(Text("备注", style="sys_label"))
        content_parts.append(
            Padding(Text(prompt.description, style="text"), (0, 0, 0, 2))
        )
    title = Text(f"提示词 {prompt.id}", style="cyan")
    return Panel(
        Group(*content_parts),
        title=title,
        border_style="cyan",
        box=box.HORIZONTALS,
        style=PANEL_STYLE,
    )


def _repo_line(prompt: RepoPrompt, idx: int, preview_width: int) -> Text:
    """单行列表:序号 · 名称 · 分组 · 正文预览,列间用分隔符。"""
    group_tag = f"[{prompt.group}]" if prompt.group else "[未分组]"
    return Text.assemble(
        (f"  {idx:<2} ", "key"),
        ("▸ ", "dim"),
        (prompt.name, "user_text"),
        ("  ", "dim"),
        ("─", "dim"),
        ("  ", "dim"),
        (group_tag, "muted"),
        ("  ", "dim"),
        ("│", "dim"),
        ("  ", "dim"),
        (_truncate_preview(prompt.content, preview_width), "dim"),
    )


def _repo_do_add(
    store: RepoStore,
    *,
    name: str,
    content: str,
    group: str | None,
    description: str | None,
) -> None:
    prompt = store.save(
        name=name,
        content=content,
        group=group or None,
        description=description or None,
    )
    console.print(f"[green]已保存:[/green] {store.repo_dir / f'{prompt.id}.json'}")
    console.print()


def _repo_add_interactive(store: RepoStore, default_group: str | None = None) -> None:
    console.print(
        Panel(
            "名称、正文为必填,分组/备注可留空。",
            title="新增提示词",
            border_style="green",
            style=PANEL_STYLE,
        )
    )
    console.print()
    name = _read_line_or_escape("名称: ")
    if name is None:
        console.print("[muted]已取消。[/muted]")
        return
    name = name.strip()
    if not name:
        err_console.print("[yellow]名称不能为空[/yellow]")
        return
    content = _read_line_or_escape("正文(Ctrl+J 换行): ")
    if content is None:
        console.print("[muted]已取消。[/muted]")
        return
    content = content.strip()
    if not content:
        err_console.print("[yellow]正文不能为空[/yellow]")
        return
    hint = (
        f"分组(留空默认 {default_group}): "
        if default_group
        else "分组(留空跳过): "
    )
    group = _read_line_or_escape(hint)
    if group is None:
        console.print("[muted]已取消。[/muted]")
        return
    group = group.strip() or default_group or None
    description = _read_line_or_escape("备注(Ctrl+J 换行,留空跳过): ")
    if description is None:
        console.print("[muted]已取消。[/muted]")
        return
    description = description.strip() or None
    _repo_do_add(
        store,
        name=name,
        content=content,
        group=group,
        description=description,
    )


def _repo_edit_interactive(store: RepoStore, prompt: RepoPrompt) -> RepoPrompt | None:
    """交互编辑已有提示词,ESC 取消,回车保持原值。"""
    console.print(
        Panel(
            "回车保持原值;分组输入 !clear 可清除。",
            title=f"编辑提示词 {prompt.id}",
            border_style="cyan",
            style=PANEL_STYLE,
        )
    )
    console.print()

    name = _read_line_or_escape(f"名称 [{prompt.name}]: ")
    if name is None:
        console.print("[muted]已取消。[/muted]")
        return None
    name = name.strip()
    if not name:
        name = prompt.name

    content = _read_line_or_escape(f"正文 [{_truncate_preview(prompt.content, 30)}](Ctrl+J 换行): ")
    if content is None:
        console.print("[muted]已取消。[/muted]")
        return None
    content = content.strip()
    if not content:
        content = prompt.content

    group_hint = f"分组 [{prompt.group or '未分组'}](!clear=清除): "
    group = _read_line_or_escape(group_hint)
    if group is None:
        console.print("[muted]已取消。[/muted]")
        return None
    group = group.strip()
    if group == "!clear":
        group = ""
    elif not group:
        group = prompt.group or ""

    desc_hint = f"备注 [{prompt.description or '无'}](Ctrl+J 换行): "
    description = _read_line_or_escape(desc_hint)
    if description is None:
        console.print("[muted]已取消。[/muted]")
        return None
    description = description.strip()
    if not description:
        description = prompt.description

    updated = store.update(
        prompt.id,
        name=name,
        content=content,
        group=group,
        description=description,
    )
    console.print(f"[green]已更新:[/green] {store.repo_dir / f'{updated.id}.json'}")
    console.print()
    return updated


def _repo_new_group_interactive(store: RepoStore) -> None:
    name = _read_line_or_escape("新分组名(ESC 取消): ")
    if name is None:
        console.print("[muted]已取消。[/muted]")
        return
    name = name.strip()
    if not name:
        err_console.print("[yellow]分组名不能为空[/yellow]")
        return
    store.add_group(name)
    console.print(f"[green]已创建分组:[/green] {name}")
    console.print()


def _repo_list_loop(
    store: RepoStore, load_items: Callable[[], list[RepoPrompt]], title: str
) -> None:
    """进入某范围后的分页列表循环,每次渲染前重新拉取数据。

    详情里删除后列表会刷新(不再回显已删项);q 返回分组选择。
    """
    term_width = console.width or 80
    preview_width = max(20, min(term_width - 45, 60))
    default_group = title if title not in ("全部", "未分组") else None
    page = 0
    while True:
        items = load_items()
        total = len(items)
        if total == 0:
            console.print(
                Panel(
                    f"「{title}」下暂无提示词。",
                    title="空列表",
                    border_style="yellow",
                    style=PANEL_STYLE,
                )
            )
            return
        # 删除后条目变少,页码可能越界,夹回最后一页
        last_page = (total - 1) // _REPO_PAGE_SIZE
        if page > last_page:
            page = last_page
        start = page * _REPO_PAGE_SIZE
        page_items = items[start : start + _REPO_PAGE_SIZE]
        _repo_header(title, f"{total} 条 · 每页 {_REPO_PAGE_SIZE} 条")
        for offset, prompt in enumerate(page_items):
            console.print(
                _repo_line(prompt, start + offset + 1, preview_width)
            )
        has_next = start + _REPO_PAGE_SIZE < total
        has_prev = page > 0
        console.print()
        hints: list[str] = []
        if has_next:
            hints.append("回车=下一页")
        if has_prev:
            hints.append("b=上一页")
        hints.append("序号=详情")
        hints.append("n=新增")
        hints.append("q=返回分组")
        console.print("[muted]" + "  ·  ".join(hints) + "[/muted]", justify="center")
        console.print()

        choice = _read_line_or_escape("> ")
        if choice is None:
            return
        choice = choice.strip()
        if choice == "":
            if has_next:
                page += 1
                console.print()
                continue
            return
        lower = choice.lower()
        if lower in {"q", "quit", "退出"}:
            return
        if lower in {"b", "prev", "上一页"}:
            if has_prev:
                page -= 1
                console.print()
            continue
        if lower in {"n", "add", "新增"}:
            console.print()
            _repo_add_interactive(store, default_group=default_group)
            return  # 返回分组选择屏以刷新列表
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= total:
                console.print()
                console.print(_render_repo_detail(items[n - 1]))
                console.print()
                _repo_show_detail_actions(store, items[n - 1])
                console.print()
                continue
            err_console.print(f"[yellow]序号超出范围 (1-{total})[/yellow]")
            continue
        err_console.print("[yellow]无效输入[/yellow]")


def _repo_show_detail_actions(store: RepoStore, prompt: RepoPrompt) -> None:
    """详情后的动作:回车返回,e 编辑,d 删除。"""
    answer = _read_line_or_escape("回车=返回 · e=编辑 · d=删除: ")
    if answer is None:
        return
    lower = answer.strip().lower()
    if lower in {"e", "edit", "编辑"}:
        updated = _repo_edit_interactive(store, prompt)
        if updated is not None:
            console.print()
            console.print(_render_repo_detail(updated))
            console.print()
            _repo_show_detail_actions(store, updated)
        return
    if lower in {"d", "delete", "删除"}:
        store.delete(prompt.id)
        console.print(f"[green]已删除:[/green] {prompt.id}")
        console.print()


def repo_browse() -> None:
    """交互式浏览 prompt 仓库:搜索/分组选择 → 分页列表 → 详情。"""
    store, _ = _repo_store_from_settings(require_api_key=False)

    def _run_search(keyword: str) -> None:
        kw = keyword.strip()
        if not kw:
            return
        console.print()
        _repo_list_loop(
            store, lambda: store.search(kw), f"搜索: {kw}"
        )

    while True:
        all_items = store.list_all()
        choices: list[tuple[str, list[RepoPrompt] | None]] = [
            ("搜索", None),
            ("全部", all_items),
            ("未分组", store.list_ungrouped()),
        ]
        for group_name in store.list_groups():
            choices.append((group_name, store.list_by_group(group_name)))

        _repo_header("prompt 仓库", f"共 {len(all_items)} 条")
        name_w = max(_display_width(label) for label, _ in choices)
        for i, (label, items) in enumerate(choices, 1):
            pad = " " * (name_w - _display_width(label))
            count_text = f"({len(items)})" if items is not None else ""
            console.print(
                Text.assemble(
                    (f"  {i:<2} ", "key"),
                    ("▸ ", "dim"),
                    (label, "user_text"),
                    (pad + "  ", "dim"),
                    ("─", "dim"),
                    ("  ", "dim"),
                    (count_text, "muted"),
                )
            )
        console.print()
        console.print(
            "[muted]序号=进入 · s=搜索 · n=新增 · g=新建分组 · x=删除分组 · q=返回[/muted]",
            justify="center",
        )
        console.print()
        choice = _read_line_or_escape("> ")
        if choice is None:
            return
        choice = choice.strip()
        lower = choice.lower()
        if lower in {"q", "quit", "退出", "0"}:
            return
        if lower in {"s", "search", "查询"}:
            keyword = _read_line_or_escape("搜索关键词: ")
            if keyword is None:
                continue
            _run_search(keyword)
            continue
        if lower in {"n", "add", "新增"}:
            console.print()
            _repo_add_interactive(store)
            continue
        if lower in {"g", "group", "新建分组", "创建分组"}:
            console.print()
            _repo_new_group_interactive(store)
            continue
        if lower in {"x", "delgroup", "删除分组"}:
            gname = _read_line_or_escape("要删除的分组名: ")
            if gname is None:
                continue
            gname = gname.strip()
            if gname:
                store.delete_group(gname)
                console.print(f"[green]已移除分组:[/green] {gname}")
                console.print()
            continue
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(choices):
                label, items = choices[n - 1]
                console.print()
                if label == "搜索":
                    keyword = _read_line_or_escape("搜索关键词: ")
                    if keyword is None:
                        continue
                    _run_search(keyword)
                else:
                    _repo_list_loop(store, _scope_loader(store, label), label)
                console.print()
                continue
            err_console.print(f"[yellow]序号超出范围 (1-{len(choices)})[/yellow]")
            continue
        err_console.print(
            "[yellow]无效输入:序号进入 / s=搜索 / n=新增 / g=新建分组 / x=删除分组 / q=返回[/yellow]"
        )


def _print_repo_list(store: RepoStore, items: list[RepoPrompt], title: str) -> None:
    """非分页打印列表(repo list 命令用)。"""
    if not items:
        console.print(
            Panel(
                "暂无提示词。用 [bold]prompt-gen repo add[/bold] 新增。",
                title="空仓库",
                border_style="yellow",
                style=PANEL_STYLE,
            )
        )
        return
    term_width = console.width or 80
    preview_width = max(20, min(term_width - 45, 60))
    _repo_header(title, f"{len(items)} 条")
    for i, prompt in enumerate(items, 1):
        console.print(_repo_line(prompt, i, preview_width))
    console.print()


repo_app = typer.Typer(
    name="repo",
    help="提示词仓库:记录常用提示词并查询。",
    no_args_is_help=False,
    add_completion=False,
)


@repo_app.callback(invoke_without_command=True)
def _repo_main(ctx: typer.Context) -> None:
    """prompt 仓库。无子命令时进入交互浏览。"""
    if ctx.invoked_subcommand is None:
        repo_browse()


@repo_app.command("add")
def repo_add(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="提示词名称"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="提示词正文"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="分组名(可省略)"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="备注(可省略)"
    ),
) -> None:
    """新增一条常用提示词到仓库。

    未提供名称与正文时进入完整交互引导;只提供其一则报错;
    名称与正文齐备时直接保存(可选字段默认省略)。
    """
    store, _ = _repo_store_from_settings(require_api_key=False)
    if name is None and content is None:
        _repo_add_interactive(store, default_group=group)
        return
    if not name or not name.strip():
        _exit_input("缺少 --name 名称")
        return
    if not content or not content.strip():
        _exit_input("缺少 --content 正文")
        return
    _repo_do_add(
        store,
        name=name.strip(),
        content=content.strip(),
        group=(group.strip() or None) if group else None,
        description=(description.strip() or None) if description else None,
    )


@repo_app.command("update")
def repo_update(
    repo_id: str = typer.Argument(..., help="提示词 ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="新名称"),
    content: Optional[str] = typer.Option(None, "--content", "-c", help="新正文"),
    group: Optional[str] = typer.Option(
        None, "--group", "-g", help="新分组(传空串可清除分组)"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="新备注"
    ),
) -> None:
    """修改仓库中某条提示词。未传字段保持原值。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    try:
        prompt = store.load(repo_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return

    no_args = all(
        opt is None for opt in (name, content, group, description)
    )
    if no_args:
        updated = _repo_edit_interactive(store, prompt)
        if updated is None:
            return
    else:
        updated = store.update(
            prompt.id,
            name=(name.strip() or None) if name else None,
            content=(content.strip() or None) if content else None,
            group=(group.strip() or None) if group else None,
            description=(description.strip() or None) if description else None,
        )
        console.print(f"[green]已更新:[/green] {updated.id}")
        console.print()


@repo_app.command("list")
def repo_list(
    group: Optional[str] = typer.Option(None, "--group", "-g", help="按分组过滤"),
    ungrouped: bool = typer.Option(False, "--ungrouped", help="只看未分组"),
) -> None:
    """列出仓库中的提示词,可按分组过滤。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    if ungrouped:
        items = store.list_ungrouped()
        title = "未分组"
    elif group is not None:
        group = group.strip() or None
        items = store.list_by_group(group)
        title = group or "未分组"
    else:
        items = store.list_all()
        title = "全部提示词"
    _print_repo_list(store, items, title)


@repo_app.command("search")
def repo_search(
    query: str = typer.Argument(..., help="搜索关键词"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="按分组过滤"),
) -> None:
    """按关键词搜索提示词(匹配名称/正文/备注/分组)。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    group_val = (group.strip() or None) if group else None
    items = store.search(query, group=group_val)
    if not items:
        console.print(f"[yellow]未找到匹配「{query}」的提示词。[/yellow]")
        return
    _print_repo_list(store, items, f"搜索结果: {query}")


@repo_app.command("show")
def repo_show(
    repo_id: str = typer.Argument(..., help="提示词 ID"),
) -> None:
    """查看仓库中某条提示词的完整详情。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    try:
        prompt = store.load(repo_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return
    console.print()
    console.print(_render_repo_detail(prompt))
    console.print()


@repo_app.command("delete")
def repo_delete(
    repo_id: str = typer.Argument(..., help="提示词 ID"),
) -> None:
    """删除仓库中某条提示词。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    try:
        store.load(repo_id)
    except PromptNotFoundError as exc:
        _exit_data(str(exc))
        return
    except PromptDataError as exc:
        _exit_data(str(exc))
        return
    store.delete(repo_id)
    console.print(f"[green]已删除:[/green] {repo_id}")
    console.print()


@repo_app.command("groups")
def repo_groups() -> None:
    """列出仓库全部分组及各自条数(含空分组)。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    groups = store.list_groups()
    ungrouped = len(store.list_ungrouped())
    total = len(store.list_all())
    if not groups and ungrouped == 0:
        console.print("暂无分组与提示词。")
        return
    _repo_header("仓库分组", f"{total} 条 · 未分组 {ungrouped}")
    rows = [("未分组", ungrouped)] + [
        (g, len(store.list_by_group(g))) for g in groups
    ]
    name_w = max(_display_width(label) for label, _ in rows)
    for i, (label, count) in enumerate(rows, 1):
        pad = " " * (name_w - _display_width(label))
        console.print(
            Text.assemble(
                (f"  {i:<2} ", "key"),
                ("▸ ", "dim"),
                (label, "user_text"),
                (pad + "  ", "dim"),
                ("─", "dim"),
                ("  ", "dim"),
                (f"({count})", "muted"),
            )
        )
    console.print()


repo_group_app = typer.Typer(
    name="group", help="管理仓库分组。", no_args_is_help=False, add_completion=False
)
repo_app.add_typer(repo_group_app, name="group")


@repo_group_app.command("add")
def repo_group_add(name: str = typer.Argument(..., help="新分组名")) -> None:
    """新建一个分组(可先建空分组)。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    store.add_group(name.strip())
    console.print(f"[green]已创建分组:[/green] {name.strip()}")
    console.print()


@repo_group_app.command("rename")
def repo_group_rename(
    old: str = typer.Argument(..., help="旧分组名"),
    new: str = typer.Argument(..., help="新分组名"),
) -> None:
    """重命名分组(同步修改其下所有提示词)。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    try:
        store.rename_group(old, new)
    except PromptDataError as exc:
        _exit_data(str(exc))
        return
    console.print(f"[green]已重命名:[/green] {old} → {new}")
    console.print()


@repo_group_app.command("delete")
def repo_group_delete(name: str = typer.Argument(..., help="要删除的分组名")) -> None:
    """从清单移除分组(不删除其下提示词)。"""
    store, _ = _repo_store_from_settings(require_api_key=False)
    store.delete_group(name)
    console.print(f"[green]已移除分组:[/green] {name}")
    console.print()


app.add_typer(repo_app, name="repo")


if __name__ == "__main__":
    app()

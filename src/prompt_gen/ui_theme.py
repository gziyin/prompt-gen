"""终端 UI 设计令牌（Tokyo Night）与 rich 主题。

颜色取自 design/terminal-ui-inspiration.html 与 Ardot 画布稿
（prompt-gen-terminal-ui），集中在此处，避免散落的硬编码色值。
"""

from __future__ import annotations

from rich.theme import Theme

# ── 调色板 ──────────────────────────────────────────────
BG = "#1a1b26"          # 终端背景
PANEL = "#16161e"       # 面板背景
CYAN = "#39d3c3"        # 品牌 / 键帽 / 成功 / 竖线
PURPLE = "#bb9af7"      # 工作流标签 / System·User 分区标题
BLUE = "#7aa2f7"        # 工作流文本
YELLOW = "#e0af68"      # 小标题 / 菜单标题 / 演示标题
GREEN = "#9ece6a"       # 系统提示词 / 成功
RED = "#f7768e"         # 错误 / 缺失
GREY = "#565f89"        # 元信息键 / 次要文字
TEXT = "#c0caf5"        # 主文本

# ── rich 主题（仅自定义名，不覆盖内置样式）──────────────
THEME = Theme(
    {
        "brand": CYAN,
        "key": f"bold {CYAN}",
        "subtitle": PURPLE,
        "workflow": PURPLE,
        "flow": BLUE,
        "menu_title": YELLOW,
        "demo_title": YELLOW,
        "text": TEXT,
        "meta_key": GREY,
        "meta_val": CYAN,
        "sys_label": PURPLE,
        "sys_text": GREEN,
        "user_label": PURPLE,
        "user_text": TEXT,
        "ok": GREEN,
        "bad": RED,
        "muted": GREY,
    }
)

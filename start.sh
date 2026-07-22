#!/usr/bin/env bash
# 一键启动 prompt-gen（POSIX / macOS / Linux / Git Bash）
# 用法：bash start.sh   或   ./start.sh
# 首次运行会自动创建 .venv 并安装全局命令 `prompt-gen`。
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python)"

if [ ! -x ".venv/bin/python" ]; then
  echo "未找到 .venv，正在创建虚拟环境…"
  "$PY" -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -e ".[dev]"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "已创建 .env（来自 .env.example）。请编辑填入 DEEPSEEK_API_KEY。"
fi

echo
echo "启动 prompt-gen 引导菜单…"
echo

# 交由 bin/prompt-gen：自动安装全局命令并启动
exec bin/prompt-gen "$@"

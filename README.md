# 本地提示词优化器 CLI

输入一段提示词,调用 DeepSeek 优化并输出优化后版本 + 优化说明,自动存入历史,支持列表与导出。

## 一键启动（推荐）

```powershell
cd D:\code\Projects\prompt_gen
.\start.ps1
```

或资源管理器中双击 `start.bat`。

脚本会：设置 UTF-8 → 检查/创建 `.venv` → 若无 `.env` 则从示例复制并打开编辑 → 进入**引导菜单**。

无参数直接运行也会打开菜单：

```powershell
.\.venv\Scripts\Activate.ps1
prompt-gen
```

菜单选项：

| 键 | 作用 |
|----|------|
| 1 | 优化提示词(输入 prompt → 输出优化版 + 说明) |
| 2 | 历史记录(列出历次优化) |
| 3 | 导出为 Markdown(按 ID 导出某次对话) |
| 4 | 检查环境配置 (doctor) |
| 0 | 退出 |

## 功能

| 命令 | 说明 |
|------|------|
| `prompt-gen` | 打开引导菜单 |
| `prompt-gen doctor` | 检查 .env / API Key / 数据目录 |
| `prompt-gen optimize` | 交互优化(输入 prompt) |
| `prompt-gen optimize -p ...` | 脚本参数优化 |
| `prompt-gen history` | 按时间倒序列出优化历史 |
| `prompt-gen export <id>` | 导出某次对话为 Markdown |

不做：Agent、RAG、Web UI、多用户、云端同步。

## 终端界面风格

基于 [rich](https://rich.readthedocs.io/) 的 Tokyo Night 配色，统一视觉语言（配色集中在 `src/prompt_gen/ui_theme.py`，便于整体调整）：

- **欢迎 / 菜单**：青色品牌标题 `✦ prompt-gen`、紫色工作流说明,菜单为青色 `[1]`–`[0]` 键帽。
- **优化中**：调用 DeepSeek 时显示 cyan spinner 状态行。
- **结果面板**：左侧青色竖线面板,含 `原始提示词` 与 `优化后提示词` 深色代码块,以及可选的 `优化说明`。
- **环境检查 (`doctor`)**：`✓` / `✗` 配合绿 / 红着色。
- **历史 (`history`)**：青色 ID、原始/优化后预览与创建时间表格,标题带记录计数。

## 环境要求

- Python 3.13+
- DeepSeek API Key（仅 `generate` 需要）

## 安装

```powershell
cd D:\code\Projects\prompt_gen
E:\04Programming\CodingEnvironment\Python\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

也可直接 `.\start.ps1`（首次会自动建 venv 并安装）。

## 配置

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入真实 Key
prompt-gen doctor
```

`.env` 示例：

```text
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_MODEL=deepseek-v4-flash
```

可选：

```text
PROMPT_GEN_DATA_DIR=D:\data\prompt_gen\prompts
PROMPT_GEN_EXPORT_DIR=D:\data\prompt_gen\exports
```

## 命令示例

```powershell
# 引导菜单 / 环境检查
prompt-gen
prompt-gen doctor

# 交互优化（输入 prompt）
prompt-gen optimize

# 参数优化（脚本模式）
prompt-gen optimize --prompt "帮我写一段代码审查的提示词"

# 历史 / 导出
prompt-gen history
prompt-gen export <id>

# 等价入口
python -m prompt_gen
```

## 优化示例

输入:`帮我写代码`

输出(优化后提示词 + 优化说明):

- **优化后**:你是资深工程师,请按以下要求帮我写代码:1. 明确语言与版本 2. 说明输入输出 3. 标注关键边界条件 …
- **说明**:1. 补充了角色定义 2. 明确了输出要求 3. 规定了边界条件标注

## 测试

```powershell
pytest
```

中文乱码时可：`$env:PYTHONIOENCODING='utf-8'; chcp 65001`，或直接用 `.\start.ps1`。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 输入或配置错误 |
| 3 | 模板不存在或本地数据损坏 |
| 4 | 模型 API 调用失败 |

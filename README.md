# 本地提示词优化器 CLI

输入一段提示词,调用 DeepSeek 优化并输出优化后版本 + 优化说明,自动存入历史,支持列表与导出。

## 一键启动（推荐）

Windows：

```powershell
cd <项目根目录>
.\scripts\start.ps1
```

或资源管理器中双击 `scripts\start.bat`。

macOS / Linux（Git Bash / 终端）：

```bash
cd <项目根目录>
bash scripts/start.sh
```

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
| 2 | 历史记录(分页浏览,序号查看详情) |
| 3 | 导出为 Markdown(按 ID 导出某次对话) |
| 4 | 检查环境配置 (doctor) |
| 5 | 提示词仓库(记录常用提示词并查询) |
| 0 | 退出 |

## 功能

| 命令 | 说明 |
|------|------|
| `prompt-gen` | 打开引导菜单 |
| `prompt-gen doctor` | 检查 .env / API Key / 数据目录 |
| `prompt-gen optimize` | 交互优化(输入 prompt) |
| `prompt-gen optimize -p ...` | 脚本参数优化 |
| `prompt-gen history` | 分页浏览历史,输入序号查看详情 |
| `prompt-gen export <id>` | 导出某次对话为 Markdown |
| `prompt-gen repo` | 交互式浏览提示词仓库(分组选择/分页/详情) |
| `prompt-gen repo add --name 名称 --content 正文 [--group 分组]` | 新增常用提示词 |
| `prompt-gen repo list [--group 分组] [--ungrouped]` | 列出提示词,可按分组过滤 |
| `prompt-gen repo search <关键词> [--group 分组]` | 按关键词查询(匹配名称/正文/备注/分组) |
| `prompt-gen repo show <id>` | 查看某条提示词详情 |
| `prompt-gen repo delete <id>` | 删除某条提示词 |
| `prompt-gen repo groups` | 列出全部分组及条数 |
| `prompt-gen repo group add/rename/delete <分组名>` | 管理分组 |

不做：Agent、RAG、Web UI、多用户、云端同步。

## 终端界面风格

基于 [rich](https://rich.readthedocs.io/) 的 Tokyo Night 配色，统一视觉语言（配色集中在 `src/prompt_gen/ui_theme.py`，便于整体调整）：

- **欢迎 / 菜单**：青色品牌标题 `✦ prompt-gen`、紫色工作流说明,菜单为青色 `[1]`–`[0]` 键帽。
- **优化中**：调用 DeepSeek 时显示 cyan spinner 状态行。
- **结果面板**：左侧青色竖线面板,含 `原始提示词` 与 `优化后提示词` 深色代码块,以及可选的 `优化说明`。
- **环境检查 (`doctor`)**：`✓` / `✗` 配合绿 / 红着色。
- **历史 (`history`)**：精简单行列表（序号/时间/ID/原始预览），分页浏览（回车翻页 / b 上一页 / q 退出），输入序号查看完整详情。
- **仓库 (`repo`)**：分组选择屏（全部/未分组/各分组）→ 分页列表（序号看详情、n 新增、g 新建分组、q 返回）→ 详情面板；子命令 `repo add/list/search/show/delete/groups` 便于脚本调用。

## 环境要求

- Python 3.13+
- DeepSeek API Key（仅 `generate` 需要）

## 安装

Windows：

```powershell
cd <项目根目录>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

macOS / Linux：

```bash
cd <项目根目录>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

也可直接运行 `.\scripts\start.ps1` / `bash scripts/start.sh`（首次会自动建 venv 并安装）。

## 全局命令（任意目录直接 `prompt-gen`）

本项目内置「首次启动自动安装全局命令」能力，克隆/部署到任意机器后**无需手动配置 PATH**：

- 首次运行 `.\scripts\start.ps1` / `bash scripts/start.sh` 或 `python -m prompt_gen` 时，会自动把 `prompt-gen`
  全局命令安装到用户 PATH（Windows → `~/bin`，macOS/Linux → `~/.local/bin`）。
- 安装完成后**重开终端**，即可在任意目录直接输入 `prompt-gen` 启动（像 `claude` 一样）。
- 安装是幂等的，重复运行不会重复写入；全局命令通过"垫片"转发到仓库内启动器，逻辑只有一份。

手动安装 / 重装（例如仓库搬家后）：

```bash
python scripts/install.py          # Windows 下用 python 或 py
# 或
make install               # 等价于上面一行
```

可用环境变量 `PROMPT_GEN_HOME` 覆盖项目根目录（默认自动推导）。

运行 `prompt-gen doctor` 可检查命令是否已在 PATH 中。

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

输入:`这是你第一次接手这个项目，现在你要扫描和分析整个项目，为接下来的开发计划做准备，重点看.qoder和.workbuddy中的记录和spec`

输出(优化后提示词 + 优化说明)，优化后采用**六段式骨架**（Role / Task / Skills / Workflow / Rules / Output Format），任务需要时追加扩展段：

**优化后**:

```markdown
你是资深项目分析师，首次接手该项目，负责系统性扫描与深度分析，聚焦 `.qoder` 与 `.workbuddy` 目录下的记录与规范文档（spec），为后续开发计划提供可执行决策依据。

## 任务/目标
1. 扫描项目结构，识别关键组件与依赖关系
2. 审查 `.qoder` 与 `.workbuddy` 中所有 spec 与历史记录
3. 提炼核心业务逻辑、模块职责与潜在风险
4. 输出结构化分析报告，支撑后续开发规划

## 能力
- 系统级架构解读：快速理解模块间交互机制
- 文档语义挖掘：精准提取 spec 中的约束、接口、状态机
- 风险识别：发现不一致、冗余、过时或未定义的设计项

## 工作流程
1. 列出 `.qoder` 与 `.workbuddy` 下所有子目录与文件，标注类型与版本标识
2. 逐项读取 spec，提取模块功能、输入输出、状态转换、权限、依赖
3. 对比 spec 间冲突/重复，验证文档与实现是否对齐
4. 整合为含“模块概览/规范摘要/问题清单/优先级”的报告

## 约束
- 仅基于 `.qoder` 与 `.workbuddy` 内现有材料，不假设外部系统行为
- 文档模糊/缺失/矛盾处标注“待澄清项”并附原始文本片段
- 所有结论可追溯至具体文件路径与行号

## 输出格式
## 一、目录概览
- `.qoder/` -> [说明]
- `.workbuddy/` -> [说明]

## 二、关键发现
- ✅ 一致性良好：[例]
- ⚠️ 待澄清项：[例，附文件:行号]
- ❌ 潜在风险：[例]

## 三、建议与优先级
| 事项 | 建议 | 优先级 |
|------|------|--------|
| [事项] | [建议] | 高/中/低 |
```

**说明**:采用六段式骨架保证结构稳定可复用；1. 补充资深角色与职责边界 2. 任务拆解为 4 条可执行目标 3. 能力段匹配架构解读/语义挖掘/风险识别 4. 工作流程细化为 4 步 5. 约束强调可追溯性 6. 输出格式给出可直接套用的 Markdown 模板

## 测试

```powershell
pytest
```

中文乱码时可：`$env:PYTHONIOENCODING='utf-8'; chcp 65001`，或直接用 `.\scripts\start.ps1`。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 输入或配置错误 |
| 3 | 模板不存在或本地数据损坏 |
| 4 | 模型 API 调用失败 |

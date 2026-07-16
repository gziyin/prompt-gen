# 本地提示词生成器 CLI

根据场景、目标、受众和约束，调用 DeepSeek 生成结构化提示词模板，并支持本地保存、列表、查看与导出。

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
| 1 | 交互生成模板（带示例提示） |
| 2 | 列出本地模板 |
| 3 | 查看模板详情 |
| 4 | 导出 Markdown |
| 5 | 检查环境 (`doctor`) |
| 0 | 退出 |

## 功能

| 命令 | 说明 |
|------|------|
| `prompt-gen` | 打开引导菜单 |
| `prompt-gen doctor` | 检查 .env / API Key / 数据目录 |
| `prompt-gen generate` | 交互生成（含示例引导） |
| `prompt-gen generate -s ... -g ...` | 脚本参数生成 |
| `prompt-gen list` | 按时间倒序列出 |
| `prompt-gen show <id>` | 查看详情 |
| `prompt-gen export <id>` | 导出 Markdown |

不做：Agent、RAG、Web UI、多用户、云端同步。

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

# 交互生成（带示例）
prompt-gen generate

# 参数生成（脚本模式须同时提供 --scenario 与 --goal）
prompt-gen generate `
  --scenario "代码审查" `
  --goal "找出可靠性问题" `
  --audience "Python 开发者" `
  --constraint "只评代码" `
  --constraint "给出可复现步骤"

# 列表 / 查看 / 导出
prompt-gen list
prompt-gen show <id>
prompt-gen export <id>

# 等价入口
python -m prompt_gen
```

## 三种演示场景

1. **Python 代码审查** — 场景：代码审查；目标：找出可靠性问题；受众：Python 开发者  
2. **邮件润色** — 场景：商务邮件；目标：语气更专业简洁；受众：职场同事  
3. **学习笔记总结** — 场景：学习笔记；目标：提炼要点与待办；受众：自己  

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

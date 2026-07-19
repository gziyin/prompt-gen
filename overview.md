# prompt-gen v0.2.0 重构总结

## 做了什么

将 prompt-gen 从**模板生成器**转向**提示词优化器**,并引入端口适配器架构。

- **旧**:用户输入 scenario/goal/audience/constraints(4 步) → LLM 生成结构化模板(name/system/user/variables/notes) → 保存/列表/查看/导出
- **新**:用户输入一段 prompt(1 步) → LLM 优化并输出优化版 + 优化说明 → 自动存入历史 → 列表/按 ID 导出

## 新架构(端口适配器)

```
src/prompt_gen/
├── domain/              # 领域核心(零外部依赖)
│   ├── models.py        # OptimizationRecord
│   └── optimizer.py     # PromptOptimizer 用例
├── ports/
│   └── llm_provider.py  # LLMProvider Protocol(通用 LLM 端口)
├── adapters/
│   ├── llm/
│   │   └── deepseek.py  # DeepSeekProvider 实现 LLMProvider
│   └── storage/
│       └── history_store.py  # HistoryStore(从旧 store.py 改造)
├── cli.py               # 5 项菜单(从 663 行瘦身到 ~340 行)
├── formatter.py         # 对话式 Markdown 导出
├── config.py            # 保留
├── exceptions.py        # 保留(语义扩展)
├── ui_theme.py          # 保留
└── __main__.py          # 保留
```

**关键设计**:`LLMProvider.complete(LLMRequest) -> LLMResponse` 是通用端口,返回原始内容。用例(PromptOptimizer)负责 JSON 解析。切换 DeepSeek → OpenAI 只需新增一个 Provider 实现,用例零改动。

## 新菜单

```
[1] 优化提示词       (输入 prompt → 输出优化版 + 说明)
[2] 历史记录         (列出历次优化)
[3] 导出为 Markdown  (按 ID 导出某次对话)
[4] 检查环境配置     (doctor)
[0] 退出
```

命令:`prompt-gen optimize | history | export <id> | doctor`

## 数据模型

```python
class OptimizationRecord(BaseModel):
    schema_version: Literal[1] = 1
    id: str                          # 12 位 hex
    created_at: datetime
    raw_prompt: str                  # 用户原始输入
    optimized_prompt: str            # 优化后的 prompt
    rationale: str | None = None     # 优化说明
    model: str | None = None         # 使用的模型
```

存储:`<data_dir>/<id>.json`(原子写入,LF 换行)。旧模板文件因 schema 不匹配会被 `list_all` 跳过,不崩溃。

## 导出格式(对话式 Markdown)

```markdown
# 提示词优化记录 <id>

## 元信息
- id / created_at / model

## 原始提示词
<raw_prompt>

## 优化后提示词
<optimized_prompt>

## 优化说明
<rationale>
```

## 关键决策记录

1. **LLMProvider 端口通用化**:旧 `StructuredPromptModel.invoke() -> PromptTemplate` 返回类型绑死;新 `LLMProvider.complete() -> LLMResponse` 返回原始内容,用例负责解析。
2. **输出形态 = prompt + 优化说明**:用户主权,不强加结构(system/user 两段太像旧模板),但保留学习价值(说明为什么这样改)。
3. **history_store 跳过损坏文件**:兼容旧 prompts/ 目录中的模板文件,不崩溃。
4. **config.py 保留 PROMPT_GEN_DATA_DIR**:不破坏现有用户配置,语义上存 OptimizationRecord。

## 测试结果

**55 个测试全部通过**(1.42s):

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| test_models.py | 10 | OptimizationRecord 校验 |
| test_optimizer.py | 12 | PromptOptimizer + _safe_api_error |
| test_history_store.py | 12 | HistoryStore 增删改查 + 边界 |
| test_formatter.py | 5 | 历史列表行 + Markdown 导出 |
| test_cli.py | 10 | optimize/history/export/doctor |
| test_regressions.py | 6 | 序列化/配置/旧格式兼容/Rich 标记 |

## 如何运行

```powershell
cd D:\code\Projects\prompt_gen
.\.venv\Scripts\Activate.ps1
prompt-gen              # 打开菜单
prompt-gen optimize     # 优化提示词
prompt-gen history      # 查看历史
pytest                  # 运行测试
```

## 删除的旧文件

- `src/prompt_gen/generator.py`(被 domain/optimizer.py + adapters/llm/deepseek.py 替代)
- `src/prompt_gen/store.py`(被 adapters/storage/history_store.py 替代)
- `src/prompt_gen/models.py`(被 domain/models.py 替代)
- 旧测试文件(test_generator.py / test_store.py 等,被新测试替代)

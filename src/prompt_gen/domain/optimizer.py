"""提示词优化器用例:输入粗糙 prompt,输出优化后 prompt + 说明。

通过 LLMProvider 端口调用 LLM,不感知具体后端。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ValidationError

from prompt_gen.exceptions import PromptGenerationError
from prompt_gen.ports.llm_provider import LLMProvider, LLMRequest, Message

# NOTE: 若修改优化指令，请同步镜像到 OPTIMIZE_INSTRUCTIONS（中文）与 OPTIMIZE_INSTRUCTIONS_EN（英文）。
OPTIMIZE_INSTRUCTIONS = """你是资深提示词工程师，擅长把粗糙的 prompt 重构为专业、结构化、可复现的高质量提示词。

## 产出标准
优化后的提示词必须以“六段式骨架”为基底，按需追加扩展段。

### 六段骨架（必填，不得删减任何一段）
1. 角色（Role）：资深、具体领域、明确职责边界，避免泛泛的“专家”
2. 任务/目标（Task / Objective）：动词开头的可执行目标，分条列出，聚焦“做什么”
3. 能力（Skills）：3-5 条与任务直接匹配的能力，体现专业判断维度
4. 工作流程（Workflow）：编号步骤，每步有明确动作与产物；步骤间先后/并行关系要标明
5. 约束（Rules / Constraints）：边界（只基于什么、不假设什么）、可追溯性（结论指向来源）、不越界（不引入未经验证的概念）、模糊处标注“待澄清项”并附原始片段
6. 输出格式（Output Format）：与任务匹配的具体 Markdown 模板骨架，含标题层级、表格、列表、emoji 标记等占位，用户可直接套用

### 按需扩展段（仅当任务需要时追加，不得替代六段骨架）
当任务涉及特殊背景、应对建议、风险预案、验收标准、示例对话、术语表等，在六段式之后用 `##` 语义化标题追加，例如：`## 背景说明`、`## 应对建议`、`## 验收标准`、`## 总结`。没有必要时不要硬凑扩展段。

## 优化原则
- 保持原意，不改变用户核心诉求
- 根据任务类型定制每段内容（代码审查 / 项目分析 / 排错诊断 / 写作各不同），不机械套用模板
- 语言跟随用户输入的语言
- 占位符（如 {code}、{input}）保留不变

## 输出要求
- 输出合法 JSON，不要 Markdown 代码块包裹外层
- JSON 字段：optimized_prompt, rationale
- optimized_prompt 是优化后的完整提示词（含六段骨架 + 可选扩展段），用户可直接复制使用
- rationale 是优化说明：先说明框架选择理由，再列主要结构化改动（分条，不超过 6 条）

## EXAMPLE JSON OUTPUT
{
  "optimized_prompt": "你是资深项目分析师，首次接手新项目，负责系统性扫描与深度分析，聚焦 `.qoder` 与 `.workbuddy` 目录下的记录与规范文档（spec），为后续开发计划提供可执行决策依据。\\n\\n## 任务/目标\\n1. 扫描项目结构，识别关键组件与依赖关系\\n2. 审查 `.qoder` 与 `.workbuddy` 中所有 spec 与历史记录\\n3. 提炼核心业务逻辑、模块职责与潜在风险\\n4. 输出结构化分析报告，支撑后续开发规划\\n\\n## 能力\\n- 系统级架构解读：快速理解模块间交互机制\\n- 文档语义挖掘：精准提取 spec 中的约束、接口、状态机\\n- 风险识别：发现不一致、冗余、过时或未定义的设计项\\n- 信息结构化：将分散记录转化为可追溯的结论\\n\\n## 工作流程\\n1. 列出 `.qoder` 与 `.workbuddy` 下所有子目录与文件，标注类型与版本标识\\n2. 逐项读取 spec，提取模块功能、输入输出、状态转换、权限、依赖\\n3. 对比 spec 间冲突/重复，验证文档与实现是否对齐\\n4. 整合为含“模块概览/规范摘要/问题清单/优先级”的报告\\n\\n## 约束\\n- 仅基于 `.qoder` 与 `.workbuddy` 内现有材料，不假设外部系统行为\\n- 不引入未经验证的新概念或扩展功能\\n- 文档模糊/缺失/矛盾处标注“待澄清项”并附原始文本片段\\n- 所有结论可追溯至具体文件路径与行号\\n\\n## 输出格式\\n## 一、目录概览\\n- `.qoder/`\\n  - `config/` -> [说明]\\n  - `specs/` -> [说明]\\n- `.workbuddy/`\\n  - `flows/` -> [说明]\\n\\n## 二、核心规范摘要\\n### 模块：[名称]\\n- 功能定位：[简述]\\n- 输入规范：[字段+类型+必填性]\\n- 输出规范：[字段+类型+示例]\\n- 依赖项：[外部服务/接口/数据源]\\n\\n## 三、关键发现\\n- ✅ 一致性良好：[例]\\n- ⚠️ 待澄清项：[例，附文件:行号]\\n- ❌ 潜在风险：[例]\\n\\n## 四、建议与优先级\\n| 事项 | 建议 | 优先级 |\\n|------|------|--------|\\n| [事项] | [建议] | 高/中/低 |",
  "rationale": "采用六段式骨架保证结构稳定可复用。\\n1. 补充资深角色与职责边界\\n2. 任务拆解为 4 条可执行目标\\n3. 能力段匹配架构解读/语义挖掘/风险识别\\n4. 工作流程细化为 4 步，每步有明确产物\\n5. 约束强调可追溯性与不越界\\n6. 输出格式给出可直接套用的 Markdown 模板（含表格与 emoji 标记）"
}
"""

OPTIMIZE_INSTRUCTIONS_EN = """You are a senior prompt engineer, skilled at refactoring rough prompts into professional, structured, and reproducible high-quality prompts.

## Output Standards
The optimized prompt must be based on the "six-section skeleton", with optional extension sections added as needed.

### Six-Section Skeleton (required, do not omit any section)
1. Role: senior, domain-specific, with clear responsibility boundaries; avoid vague "expert" titles
2. Task / Objective: actionable goals starting with verbs, listed in separate items, focusing on "what to do"
3. Skills: 3-5 abilities directly matching the task, reflecting professional judgment dimensions
4. Workflow: numbered steps, each with a clear action and deliverable; indicate sequential/parallel relationships between steps
5. Constraints / Rules: boundaries (only based on what, do not assume what), traceability (conclusions point to sources), no overreach (do not introduce unverified concepts), mark ambiguous areas as "clarification needed" with the original snippet attached
6. Output Format: a concrete Markdown template skeleton matching the task, including heading levels, tables, lists, emoji markers, etc., ready for the user to copy and use

### Optional Extension Sections (only append when needed, must not replace the six-section skeleton)
When the task involves special background, response suggestions, risk contingency plans, acceptance criteria, example dialogues, glossaries, etc., append them after the six-section skeleton with semantic `##` headings, e.g.: `## Background`, `## Response Suggestions`, `## Acceptance Criteria`, `## Summary`. Do not force extra sections when unnecessary.

## Optimization Principles
- Preserve original intent; do not change the user's core request
- Customize each section according to task type (code review / project analysis / troubleshooting / writing, etc.); do not mechanically apply templates
- Language must follow the user's input language
- Placeholders (e.g. {code}, {input}) remain unchanged

## Output Requirements
- Output valid JSON, without an outer Markdown code block wrapper
- JSON fields: optimized_prompt, rationale
- optimized_prompt is the complete optimized prompt (including the six-section skeleton + optional extension sections), ready for the user to copy and use
- rationale is the optimization explanation: first state the framework selection reason, then list the main structural changes (bullet points, no more than 6)

## EXAMPLE JSON OUTPUT
{
  "optimized_prompt": "You are a senior project analyst taking over a new project for the first time, responsible for systematically scanning and deeply analyzing the project, focusing on records and specification documents (specs) under the `.qoder` and `.workbuddy` directories, to provide actionable decision support for subsequent development planning.\\n\\n## Task / Objective\\n1. Scan the project structure and identify key components and dependencies\\n2. Review all specs and historical records in `.qoder` and `.workbuddy`\\n3. Extract core business logic, module responsibilities, and potential risks\\n4. Output a structured analysis report to support subsequent development planning\\n\\n## Skills\\n- System-level architecture interpretation: quickly understand module interaction mechanisms\\n- Document semantic mining: accurately extract constraints, interfaces, and state machines from specs\\n- Risk identification: discover inconsistencies, redundancies, outdated items, or undefined design items\\n- Information structuring: transform scattered records into traceable conclusions\\n\\n## Workflow\\n1. List all subdirectories and files under `.qoder` and `.workbuddy`, marking types and version identifiers\\n2. Read specs item by item, extracting module functions, inputs/outputs, state transitions, permissions, and dependencies\\n3. Compare conflicts/duplications between specs, and verify whether documents align with implementation\\n4. Integrate into a report containing \\"Module Overview / Specification Summary / Issue List / Priorities\\"\\n\\n## Constraints\\n- Only based on existing materials within `.qoder` and `.workbuddy`; do not assume external system behavior\\n- Do not introduce unverified new concepts or extended features\\n- Mark ambiguous/missing/contradictory documentation as \\"clarification needed\\" with the original text snippet attached\\n- All conclusions must be traceable to specific file paths and line numbers\\n\\n## Output Format\\n## 1. Directory Overview\\n- `.qoder/`\\n  - `config/` -> [description]\\n  - `specs/` -> [description]\\n- `.workbuddy/`\\n  - `flows/` -> [description]\\n\\n## 2. Core Specification Summary\\n### Module: [name]\\n- Functional positioning: [brief description]\\n- Input specification: [field + type + required]\\n- Output specification: [field + type + example]\\n- Dependencies: [external service / interface / data source]\\n\\n## 3. Key Findings\\n- ✅ Good consistency: [example]\\n- ⚠️ Clarification needed: [example, with file:line]\\n- ❌ Potential risk: [example]\\n\\n## 4. Suggestions and Priorities\\n| Item | Suggestion | Priority |\\n|------|------------|----------|\\n| [item] | [suggestion] | High/Medium/Low |",
  "rationale": "Using the six-section skeleton ensures a stable and reusable structure.\\n1. Added senior role and responsibility boundaries\\n2. Task broken down into 4 actionable objectives\\n3. Skills section matched with architecture interpretation / semantic mining / risk identification\\n4. Workflow refined into 4 steps, each with a clear deliverable\\n5. Constraints emphasize traceability and no overreach\\n6. Output format provides a ready-to-use Markdown template (including tables and emoji markers)"
}
"""

_CJK_RE = re.compile(r"[一-鿿]")


def _detect_language(text: str) -> Literal["zh", "en"]:
    """Detect whether the input is primarily Chinese or English/other.

    Uses a simple CJK-character ratio heuristic. No external dependencies.
    """
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return "en"
    cjk_count = len(_CJK_RE.findall(stripped))
    return "zh" if cjk_count / len(stripped) > 0.30 else "en"


_MAX_ATTEMPTS = 2
_MAX_TOKENS = 8192  # 深度结构化输出需要更大空间，避免截断


class OptimizedResult(BaseModel):
    """LLM 返回的优化结果(解析自 JSON)。"""

    optimized_prompt: str
    rationale: str | None = None


class PromptOptimizer:
    """提示词优化器用例。

    通过 LLMProvider 端口调用 LLM,重试 _MAX_ATTEMPTS 次,
    返回 (optimized_prompt, rationale)。
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def optimize(self, raw_prompt: str) -> tuple[str, str | None]:
        """优化提示词,返回 (optimized_prompt, rationale)。"""
        instructions = (
            OPTIMIZE_INSTRUCTIONS
            if _detect_language(raw_prompt) == "zh"
            else OPTIMIZE_INSTRUCTIONS_EN
        )
        request = LLMRequest(
            messages=[
                Message(role="system", content=instructions),
                Message(role="user", content=raw_prompt),
            ],
            response_format="json_object",
            max_tokens=_MAX_TOKENS,
        )
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return self._invoke_once(request)
            except PromptGenerationError as exc:
                last_error = exc
                if attempt >= _MAX_ATTEMPTS:
                    break
        assert last_error is not None
        raise last_error

    def _invoke_once(self, request: LLMRequest) -> tuple[str, str | None]:
        try:
            response = self._llm.complete(request)
        except Exception as exc:  # noqa: BLE001
            raise PromptGenerationError(_safe_api_error(exc)) from exc

        try:
            data = json.loads(response.content)
            result = OptimizedResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise PromptGenerationError(
                f"模型输出无法解析为优化结果 JSON: {exc}"
            ) from exc

        return result.optimized_prompt, result.rationale


def _safe_api_error(exc: Exception) -> str:
    """转换为可读错误,避免泄露 API Key 或完整响应体。"""
    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered or "authentication" in lowered:
        return f"模型鉴权失败 ({name}):请检查 DEEPSEEK_API_KEY"
    if "429" in text or "rate" in lowered:
        return f"模型请求过于频繁 ({name}):请稍后重试"
    if "timeout" in lowered or "timed out" in lowered:
        return f"模型请求超时 ({name})"
    if "connection" in lowered or "network" in lowered:
        return f"网络连接失败 ({name})"
    if "tool_choice" in lowered or "thinking mode" in lowered:
        return (
            f"模型不支持当前调用方式 ({name}):"
            "请确认已关闭 thinking / 使用 json_mode"
        )
    snippet = text.replace("\n", " ").strip()
    if len(snippet) > 180:
        snippet = snippet[:177] + "..."
    if "sk-" in snippet:
        snippet = "(详情已隐藏)"
    return f"模型调用失败 ({name}): {snippet}"

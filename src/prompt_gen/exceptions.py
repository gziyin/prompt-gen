"""领域异常：CLI 层统一映射为可读信息与退出码。"""


class PromptGenError(Exception):
    """所有项目异常的基类。"""


class ConfigurationError(PromptGenError):
    """缺少配置或配置无效（如 API Key）。"""


class PromptNotFoundError(PromptGenError):
    """指定 ID 的模板不存在。"""


class PromptDataError(PromptGenError):
    """本地 JSON 损坏、非法 ID 或路径校验失败。"""


class PromptGenerationError(PromptGenError):
    """模型调用、鉴权、限流或结构化解析失败。"""

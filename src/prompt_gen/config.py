"""运行配置：从环境变量加载 Settings。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from prompt_gen.exceptions import ConfigurationError


def _find_project_root() -> Path | None:
    """在源码布局下定位含 pyproject.toml 的项目根；安装到 site-packages 时返回 None。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (
            parent / "src" / "prompt_gen"
        ).is_dir():
            return parent
    return None


def _default_dir(name: str) -> Path:
    root = _find_project_root()
    base = root if root is not None else Path.cwd()
    return (base / name).resolve()


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    data_dir: Path
    export_dir: Path


def load_settings(require_api_key: bool = True) -> Settings:
    """加载配置。list/show/export 可传 require_api_key=False。"""
    root = _find_project_root()
    if root is not None:
        load_dotenv(root / ".env")
    load_dotenv()  # 当前工作目录 .env

    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if require_api_key and not api_key:
        raise ConfigurationError(
            "缺少 DEEPSEEK_API_KEY。请在项目根目录创建 .env（参考 .env.example）。"
        )
    if require_api_key and api_key in {"sk-your-key-here", "your-key-here"}:
        raise ConfigurationError(
            "DEEPSEEK_API_KEY 仍是占位符，请填入真实 Key。"
        )

    model = (os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    if not model:
        raise ConfigurationError("DEEPSEEK_MODEL 不能为空。")

    data_dir = Path(
        os.getenv("PROMPT_GEN_DATA_DIR") or _default_dir("prompts")
    ).expanduser().resolve()
    export_dir = Path(
        os.getenv("PROMPT_GEN_EXPORT_DIR") or _default_dir("exports")
    ).expanduser().resolve()

    return Settings(
        api_key=api_key,
        model=model,
        data_dir=data_dir,
        export_dir=export_dir,
    )

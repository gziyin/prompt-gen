"""JSON 持久化：原子写入 prompts/<id>.json。"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from prompt_gen.exceptions import PromptDataError, PromptNotFoundError
from prompt_gen.models import PromptRequest, PromptTemplate, StoredPrompt

_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _as_utc(value: datetime) -> datetime:
    """排序/展示前统一为 aware UTC，避免 naive/aware 混比崩溃。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PromptStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir.expanduser().resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def save(self, request: PromptRequest, template: PromptTemplate) -> StoredPrompt:
        prompt_id = uuid4().hex[:12]
        stored = StoredPrompt(
            schema_version=1,
            id=prompt_id,
            created_at=datetime.now(timezone.utc),
            source=request,
            template=template,
        )
        path = self._path_for_id(prompt_id)
        payload = json.dumps(
            stored.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        self._atomic_write(path, payload)
        return stored

    def list_all(self) -> list[StoredPrompt]:
        items: list[StoredPrompt] = []
        for path in sorted(self._data_dir.glob("*.json")):
            # 只把合法 ID 文件名视为项目数据；其它 json 忽略
            if not _ID_PATTERN.fullmatch(path.stem):
                continue
            try:
                items.append(self._read_file(path))
            except PromptDataError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise PromptDataError(f"无法读取模板文件: {path.name}: {exc}") from exc
        items.sort(key=lambda p: _as_utc(p.created_at), reverse=True)
        return items

    def load(self, prompt_id: str) -> StoredPrompt:
        prompt_id = prompt_id.strip()
        path = self._path_for_id(prompt_id)
        if not path.exists():
            raise PromptNotFoundError(f"模板不存在: {prompt_id}")
        return self._read_file(path)

    def _path_for_id(self, prompt_id: str) -> Path:
        prompt_id = prompt_id.strip()
        if not _ID_PATTERN.fullmatch(prompt_id):
            raise PromptDataError(
                f"非法 ID: {prompt_id!r}（仅允许 12 位小写十六进制）"
            )
        path = (self._data_dir / f"{prompt_id}.json").resolve()
        if not path.is_relative_to(self._data_dir):
            raise PromptDataError(f"路径越界: {prompt_id}")
        return path

    def _read_file(self, path: Path) -> StoredPrompt:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return StoredPrompt.model_validate(data)
        except PromptDataError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PromptDataError(f"模板数据损坏: {path.name}: {exc}") from exc

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".tmp",
            dir=path.parent,
        )
        tmp_path = Path(tmp_name)
        try:
            with open(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                if not content.endswith("\n"):
                    handle.write("\n")
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

"""优化历史持久化:原子写入 <data_dir>/<id>.json。

从旧 PromptStore 改造而来,存 OptimizationRecord 而非 StoredPrompt。
list_all 遇到无法解析的旧文件会跳过(兼容旧 prompts/ 目录中的模板文件)。
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from prompt_gen.domain.models import OptimizationRecord
from prompt_gen.exceptions import PromptDataError, PromptNotFoundError

_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _as_utc(value: datetime) -> datetime:
    """排序/展示前统一为 aware UTC,避免 naive/aware 混比崩溃。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class HistoryStore:
    """优化历史存储。

    接口与旧 PromptStore 对齐(save/list_all/load),
    但保存的是 OptimizationRecord(优化对话)而非 StoredPrompt(模板)。
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir.expanduser().resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def save(
        self,
        raw_prompt: str,
        optimized_prompt: str,
        rationale: str | None,
        model: str | None,
    ) -> OptimizationRecord:
        """保存一次优化记录,返回完整 record(含生成的 id 与 created_at)。"""
        record = OptimizationRecord(
            id=uuid4().hex[:12],
            created_at=datetime.now(timezone.utc),
            raw_prompt=raw_prompt,
            optimized_prompt=optimized_prompt,
            rationale=rationale,
            model=model,
        )
        path = self._path_for_id(record.id)
        payload = json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        self._atomic_write(path, payload)
        return record

    def list_all(self) -> list[OptimizationRecord]:
        """按创建时间倒序列出全部记录。损坏文件跳过而非崩溃。"""
        items: list[OptimizationRecord] = []
        for path in sorted(self._data_dir.glob("*.json")):
            if not _ID_PATTERN.fullmatch(path.stem):
                continue
            try:
                items.append(self._read_file(path))
            except PromptDataError:
                # 跳过损坏文件(可能是旧模板格式),不崩溃
                continue
        items.sort(key=lambda r: _as_utc(r.created_at), reverse=True)
        return items

    def load(self, record_id: str) -> OptimizationRecord:
        """加载指定 ID 的记录。不存在则抛 PromptNotFoundError。"""
        record_id = record_id.strip()
        path = self._path_for_id(record_id)
        if not path.exists():
            raise PromptNotFoundError(f"优化记录不存在: {record_id}")
        return self._read_file(path)

    def _path_for_id(self, record_id: str) -> Path:
        record_id = record_id.strip()
        if not _ID_PATTERN.fullmatch(record_id):
            raise PromptDataError(
                f"非法 ID: {record_id!r}(仅允许 12 位小写十六进制)"
            )
        path = (self._data_dir / f"{record_id}.json").resolve()
        if not path.is_relative_to(self._data_dir):
            raise PromptDataError(f"路径越界: {record_id}")
        return path

    def _read_file(self, path: Path) -> OptimizationRecord:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return OptimizationRecord.model_validate(data)
        except PromptDataError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PromptDataError(f"记录数据损坏: {path.name}: {exc}") from exc

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

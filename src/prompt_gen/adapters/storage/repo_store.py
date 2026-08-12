"""prompt 仓库持久化:原子写入 <data_dir>/repo/<id>.json。

与 HistoryStore 同构(复用其原子写入 / 损坏文件跳过 / 12 位 hex
文件名约定),但存到独立的 repo/ 子目录,避免与 history 的 JSON 混淆。

分组(可选)不按目录存放,而是记录在每条提示词的 group 字段中;
另维护一份 groups.json 清单,使「新建空分组后也能列出」。
list_groups() 返回 manifest 与所有记录 group 字段的并集。
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from prompt_gen.domain.models import RepoPrompt
from prompt_gen.exceptions import PromptDataError, PromptNotFoundError

_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def _as_utc(value: datetime) -> datetime:
    """排序/展示前统一为 aware UTC,避免 naive/aware 混比崩溃。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RepoStore:
    """prompt 仓库存储。

    记录平铺在 <data_dir>/repo/<id>.json,分组信息存于每条记录及
    groups.json 清单。search 在 name/content/description/group 上
    做大小写不敏感子串匹配。
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir.expanduser().resolve()
        self._repo_dir = self._data_dir / "repo"
        self._repo_dir.mkdir(parents=True, exist_ok=True)
        self._groups_path = self._repo_dir / "groups.json"

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def repo_dir(self) -> Path:
        return self._repo_dir

    # ── 写入 ──────────────────────────────────────────────

    def save(
        self,
        *,
        name: str,
        content: str,
        group: str | None = None,
        description: str | None = None,
    ) -> RepoPrompt:
        """保存一条提示词,返回完整 record(含生成的 id 与时间戳)。"""
        now = datetime.now(timezone.utc)
        prompt = RepoPrompt(
            id=uuid4().hex[:12],
            name=name,
            content=content,
            group=group,
            description=description,
            created_at=now,
            updated_at=now,
        )
        path = self._path_for_id(prompt.id)
        self._atomic_write(path, self._serialize(prompt))
        if prompt.group:
            self.add_group(prompt.group)
        return prompt

    def add_group(self, group: str) -> None:
        """登记一个分组(可空分组)。已存在则 no-op。"""
        group = (group or "").strip()
        if not group:
            return
        groups = self._read_groups()
        if group not in groups:
            groups.append(group)
            self._write_groups(groups)

    def update(
        self,
        repo_id: str,
        *,
        name: str | None = None,
        content: str | None = None,
        group: str | None = None,
        description: str | None = None,
    ) -> RepoPrompt:
        """按传入字段更新,刷新 updated_at。未传字段保持原值。"""
        prompt = self.load(repo_id)
        data = prompt.model_dump(mode="json")
        if name is not None:
            data["name"] = name
        if content is not None:
            data["content"] = content
        if group is not None:
            data["group"] = group
        if description is not None:
            data["description"] = description
        data["updated_at"] = datetime.now(timezone.utc)
        updated = RepoPrompt(**data)
        self._atomic_write(self._path_for_id(repo_id), self._serialize(updated))
        if updated.group:
            self.add_group(updated.group)
        return updated

    def delete(self, repo_id: str) -> None:
        """删除指定记录;不存在则静默(幂等)。"""
        path = self._path_for_id(repo_id)
        path.unlink(missing_ok=True)

    def rename_group(self, old: str, new: str) -> None:
        """重命名分组:更新 manifest 与所有归属于该组的记录。"""
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new:
            raise PromptDataError("分组名不能为空")
        for prompt in self.list_all():
            if prompt.group == old:
                self.update(prompt.id, group=new)
        groups = self._read_groups()
        if old in groups:
            groups.remove(old)
        if new and new not in groups:
            groups.append(new)
        self._write_groups(groups)

    def delete_group(self, group: str) -> None:
        """从 manifest 移除分组(不删除其下记录)。"""
        group = (group or "").strip()
        groups = self._read_groups()
        if group in groups:
            groups.remove(group)
            self._write_groups(groups)

    # ── 读取 ──────────────────────────────────────────────

    def list_all(self) -> list[RepoPrompt]:
        """按创建时间倒序列出全部记录。损坏/非 12-hex 文件跳过。"""
        items: list[RepoPrompt] = []
        for path in sorted(self._repo_dir.glob("*.json")):
            if not _ID_PATTERN.fullmatch(path.stem):
                continue  # 跳过 groups.json 及非记录文件
            try:
                items.append(self._read_file(path))
            except PromptDataError:
                continue
        items.sort(key=lambda p: _as_utc(p.created_at), reverse=True)
        return items

    def list_by_group(self, group: str | None) -> list[RepoPrompt]:
        """按分组过滤。group=None 返回未分组记录。"""
        if group is None:
            return self.list_ungrouped()
        return [p for p in self.list_all() if p.group == group]

    def list_ungrouped(self) -> list[RepoPrompt]:
        """未分组的记录(直接存在默认路径下)。"""
        return [p for p in self.list_all() if not p.group]

    def list_groups(self) -> list[str]:
        """返回 manifest 与记录中 group 字段的并集(去重排序)。"""
        groups = set(self._read_groups())
        for prompt in self.list_all():
            if prompt.group:
                groups.add(prompt.group)
        return sorted(groups)

    def search(
        self, query: str, group: str | None = None
    ) -> list[RepoPrompt]:
        """大小写不敏感子串匹配 name/content/description/group。

        group 可选过滤:None 表示不限定(含未分组与任意分组)。
        """
        needle = (query or "").strip().lower()
        items = self.list_all()
        if group is not None:
            items = self.list_by_group(group)
        if not needle:
            return items
        result: list[RepoPrompt] = []
        for prompt in items:
            hay = " ".join(
                [
                    prompt.name,
                    prompt.content,
                    prompt.description or "",
                    prompt.group or "",
                ]
            ).lower()
            if needle in hay:
                result.append(prompt)
        return result

    def load(self, repo_id: str) -> RepoPrompt:
        """加载指定 ID 的记录。不存在则抛 PromptNotFoundError。"""
        repo_id = repo_id.strip()
        path = self._path_for_id(repo_id)
        if not path.exists():
            raise PromptNotFoundError(f"提示词不存在: {repo_id}")
        return self._read_file(path)

    # ── 私有 ──────────────────────────────────────────────

    def _path_for_id(self, repo_id: str) -> Path:
        repo_id = repo_id.strip()
        if not _ID_PATTERN.fullmatch(repo_id):
            raise PromptDataError(
                f"非法 ID: {repo_id!r}(仅允许 12 位小写十六进制)"
            )
        path = (self._repo_dir / f"{repo_id}.json").resolve()
        if not path.is_relative_to(self._repo_dir):
            raise PromptDataError(f"路径越界: {repo_id}")
        return path

    def _read_file(self, path: Path) -> RepoPrompt:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return RepoPrompt.model_validate(data)
        except PromptDataError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PromptDataError(f"记录数据损坏: {path.name}: {exc}") from exc

    def _serialize(self, prompt: RepoPrompt) -> str:
        return json.dumps(
            prompt.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )

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

    def _read_groups(self) -> list[str]:
        if not self._groups_path.exists():
            return []
        try:
            data = json.loads(self._groups_path.read_text(encoding="utf-8"))
            groups = data.get("groups", [])
            return [g for g in groups if isinstance(g, str) and g.strip()]
        except Exception:  # noqa: BLE001
            return []

    def _write_groups(self, groups: list[str]) -> None:
        payload = json.dumps(
            {"groups": groups}, ensure_ascii=False, indent=2
        )
        self._atomic_write(self._groups_path, payload)

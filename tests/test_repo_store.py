"""RepoStore 持久化测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_gen.adapters.storage.repo_store import RepoStore
from prompt_gen.exceptions import PromptDataError, PromptNotFoundError


def _store(tmp_path: Path) -> tuple[RepoStore, Path]:
    """返回 (store, repo_dir)，repo_dir 即 data_dir/repo。"""
    store = RepoStore(tmp_path)
    return store, store.repo_dir


def _save_one(
    store: RepoStore, *, name: str = "提示A", group: str | None = None
):
    return store.save(name=name, content="正文内容", group=group)


def test_save_creates_json_file(tmp_path: Path) -> None:
    store, repo_dir = _store(tmp_path)
    prompt = _save_one(store)
    path = repo_dir / f"{prompt.id}.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == prompt.id
    assert data["name"] == "提示A"


def test_save_returns_id_and_timestamp(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    prompt = _save_one(store)
    assert len(prompt.id) == 12
    assert all(c in "0123456789abcdef" for c in prompt.id)
    assert prompt.updated_at == prompt.created_at


def test_list_all_empty_for_new_dir(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    assert store.list_all() == []


def test_list_all_reverse_chronological(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    first = _save_one(store, name="第一")
    second = _save_one(store, name="第二")
    assert [p.name for p in store.list_all()] == ["第二", "第一"]


def test_add_group_then_list_groups(tmp_path: Path) -> None:
    """新建空分组后 list_groups 应能列出。"""
    store, _ = _store(tmp_path)
    store.add_group("项目A")
    store.add_group("项目A")  # 幂等
    assert store.list_groups() == ["项目A"]


def test_list_groups_includes_groups_from_records(tmp_path: Path) -> None:
    """仅写了带分组的记录,list_groups 也应含该组(并集)。"""
    store, _ = _store(tmp_path)
    _save_one(store, group="项目A")
    _save_one(store, group="项目B")
    assert set(store.list_groups()) == {"项目A", "项目B"}


def test_list_by_group_and_ungrouped(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    _save_one(store, name="有组", group="项目A")
    _save_one(store, name="无组")
    assert [p.name for p in store.list_by_group("项目A")] == ["有组"]
    assert [p.name for p in store.list_ungrouped()] == ["无组"]
    assert [p.name for p in store.list_by_group(None)] == ["无组"]


def test_search_matches_name_content_description_group(
    tmp_path: Path,
) -> None:
    store, _ = _store(tmp_path)
    store.save(name="代码审查", content="检查质量", group="项目A",
               description="review 要点")
    store.save(name="写邮件", content="商务邮件", group="项目B")
    assert {p.name for p in store.search("审查")} == {"代码审查"}
    assert {p.name for p in store.search("商务")} == {"写邮件"}
    assert {p.name for p in store.search("review")} == {"代码审查"}
    assert {p.name for p in store.search("项目B")} == {"写邮件"}


def test_search_case_insensitive(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.save(name="Code Review", content="x")
    assert len(store.search("review")) == 1
    assert len(store.search("CODE")) == 1


def test_search_group_filter(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.save(name="审查", content="x", group="项目A")
    store.save(name="审查", content="x", group="项目B")
    assert [p.group for p in store.search("审查", group="项目A")] == ["项目A"]


def test_load_returns_by_id(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    saved = _save_one(store)
    loaded = store.load(saved.id)
    assert loaded.id == saved.id
    assert loaded.name == saved.name


def test_load_missing_raises_not_found(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    with pytest.raises(PromptNotFoundError):
        store.load("abcdef123456")


def test_load_strips_id_whitespace(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    saved = _save_one(store)
    assert store.load(f"  {saved.id}  ").id == saved.id


def test_rejects_invalid_id_format(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    with pytest.raises(PromptDataError):
        store.load("not-a-valid-id")


def test_update_refreshes_updated_at_and_keeps_others(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    saved = _save_one(store, name="原名", group="A")
    updated = store.update(saved.id, name="新名")
    assert updated.name == "新名"
    assert updated.content == saved.content  # 未传字段保留
    assert updated.group == saved.group
    assert updated.updated_at > saved.updated_at


def test_delete_removes_file(tmp_path: Path) -> None:
    store, repo_dir = _store(tmp_path)
    saved = _save_one(store)
    store.delete(saved.id)
    assert not (repo_dir / f"{saved.id}.json").exists()
    assert store.list_all() == []


def test_rename_group_updates_records_and_manifest(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    saved = _save_one(store, group="旧组")
    store.rename_group("旧组", "新组")
    assert store.load(saved.id).group == "新组"
    assert "新组" in store.list_groups()
    assert "旧组" not in store.list_groups()


def test_delete_group_removes_from_manifest_keeps_records(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.add_group("空组")
    store.delete_group("空组")
    assert "空组" not in store.list_groups()


def test_list_all_ignores_groups_json_and_non_id(tmp_path: Path) -> None:
    store, repo_dir = _store(tmp_path)
    _save_one(store)
    (repo_dir / "groups.json").write_text(
        '{"groups": ["项目A"]}\n', encoding="utf-8"
    )
    (repo_dir / "notes.json").write_text('{"hello": 1}\n', encoding="utf-8")
    assert len(store.list_all()) == 1


def test_list_skips_corrupted_files(tmp_path: Path) -> None:
    store, repo_dir = _store(tmp_path)
    _save_one(store)
    (repo_dir / "badbadbadbad.json").write_text(
        '{"wrong": "schema"}\n', encoding="utf-8"
    )
    assert len(store.list_all()) == 1


def test_json_written_with_lf_and_unicode(tmp_path: Path) -> None:
    store, repo_dir = _store(tmp_path)
    saved = store.save(name="代码审查", content="审查正文")
    raw = (repo_dir / f"{saved.id}.json").read_bytes()
    assert b"\r\n" not in raw
    assert "代码审查".encode("utf-8") in raw

"""HistoryStore 持久化测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_gen.adapters.storage.history_store import HistoryStore
from prompt_gen.domain.models import OptimizationRecord
from prompt_gen.exceptions import PromptDataError, PromptNotFoundError


def _save_one(
    store: HistoryStore, *, raw: str = "原始", opt: str = "优化后"
) -> OptimizationRecord:
    return store.save(
        raw_prompt=raw,
        optimized_prompt=opt,
        rationale="说明",
        model="deepseek-v4-flash",
    )


def test_save_creates_json_file(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    record = _save_one(store)
    path = tmp_path / f"{record.id}.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == record.id
    assert data["raw_prompt"] == "原始"


def test_save_returns_record_with_id_and_timestamp(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    record = _save_one(store)
    assert len(record.id) == 12
    assert all(c in "0123456789abcdef" for c in record.id)
    assert record.created_at is not None


def test_list_all_returns_empty_for_new_dir(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    assert store.list_all() == []


def test_list_all_returns_in_reverse_chronological_order(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    first = _save_one(store, raw="第一")
    second = _save_one(store, raw="第二")
    items = store.list_all()
    assert [r.id for r in items] == [second.id, first.id]


def test_load_returns_record_by_id(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    saved = _save_one(store, raw="找这个")
    loaded = store.load(saved.id)
    assert loaded.id == saved.id
    assert loaded.raw_prompt == "找这个"


def test_load_raises_not_found_for_missing_id(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    with pytest.raises(PromptNotFoundError):
        store.load("abcdef123456")


def test_load_strips_id_whitespace(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    saved = _save_one(store)
    loaded = store.load(f"  {saved.id}  ")
    assert loaded.id == saved.id


def test_rejects_invalid_id_format(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    with pytest.raises(PromptDataError):
        store.load("not-a-valid-id")


def test_list_ignores_non_id_json(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    _save_one(store)
    (tmp_path / "notes.json").write_text('{"hello": 1}\n', encoding="utf-8")
    items = store.list_all()
    assert len(items) == 1


def test_list_skips_corrupted_files(tmp_path: Path) -> None:
    """损坏文件(如旧模板格式)应跳过,不崩溃。"""
    store = HistoryStore(tmp_path)
    _save_one(store)
    bad_path = tmp_path / "badbadbadbad.json"
    bad_path.write_text('{"wrong": "schema"}\n', encoding="utf-8")
    items = store.list_all()
    assert len(items) == 1


def test_json_written_with_lf_and_unicode(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    saved = store.save(
        raw_prompt="邮件润色",
        optimized_prompt="更专业",
        rationale=None,
        model=None,
    )
    raw = (tmp_path / f"{saved.id}.json").read_bytes()
    assert b"\r\n" not in raw
    assert "邮件润色".encode("utf-8") in raw


def test_list_sorts_mixed_naive_and_aware_datetimes(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    older = _save_one(store, raw="旧")
    newer = _save_one(store, raw="新")
    path = tmp_path / f"{older.id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["created_at"] = "2020-01-01T00:00:00"  # naive
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    items = store.list_all()
    assert [item.id for item in items] == [newer.id, older.id]

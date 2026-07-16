"""持久化测试。"""

from pathlib import Path

import pytest

from prompt_gen.exceptions import PromptDataError, PromptNotFoundError
from prompt_gen.models import PromptRequest, PromptTemplate
from prompt_gen.store import PromptStore


def _sample() -> tuple[PromptRequest, PromptTemplate]:
    request = PromptRequest(scenario="邮件润色", goal="更专业", audience="职场")
    template = PromptTemplate(
        name="邮件润色",
        system_prompt="你是写作助手。",
        user_prompt_template="请润色：\n{draft}",
        variables=["draft"],
    )
    return request, template


def test_save_and_reload(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    request, template = _sample()
    saved = store.save(request, template)
    loaded = store.load(saved.id)
    assert loaded.id == saved.id
    assert loaded.template.name == "邮件润色"
    assert (tmp_path / f"{saved.id}.json").exists()


def test_list_across_store_instances(tmp_path: Path) -> None:
    request, template = _sample()
    first = PromptStore(tmp_path)
    saved = first.save(request, template)
    second = PromptStore(tmp_path)
    items = second.list_all()
    assert len(items) == 1
    assert items[0].id == saved.id


def test_missing_and_illegal_id(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    with pytest.raises(PromptNotFoundError):
        store.load("aaaaaaaaaaaa")
    with pytest.raises(PromptDataError, match="非法 ID"):
        store.load("../etc/passwd")
    with pytest.raises(PromptDataError, match="非法 ID"):
        store.load("ABCDEF123456")


def test_corrupted_json_reports_filename(tmp_path: Path) -> None:
    bad = tmp_path / "bbbbbbbbbbbb.json"
    bad.write_text("{not-json", encoding="utf-8")
    store = PromptStore(tmp_path)
    with pytest.raises(PromptDataError, match="bbbbbbbbbbbb.json"):
        store.list_all()


def test_atomic_replace_keeps_valid_json(tmp_path: Path) -> None:
    store = PromptStore(tmp_path)
    request, template = _sample()
    saved = store.save(request, template)
    path = tmp_path / f"{saved.id}.json"
    text = path.read_text(encoding="utf-8")
    assert text.strip().startswith("{")
    assert '"schema_version": 1' in text
    # 同目录不应残留失败的临时文件（成功路径下）
    assert list(tmp_path.glob(".*.tmp")) == []

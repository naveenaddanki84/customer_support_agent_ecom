"""Unit tests for the editable knowledge-document reader. No stack required."""

import importlib

import app.knowledge as knowledge


def _reload_with_dir(monkeypatch, path):
    monkeypatch.setenv("KNOWLEDGE_DIR", str(path))
    return importlib.reload(knowledge)


def test_reads_policy_and_faqs(tmp_path, monkeypatch):
    (tmp_path / "refund_policy.md").write_text("POLICY BODY", encoding="utf-8")
    (tmp_path / "faqs.md").write_text("FAQ BODY", encoding="utf-8")
    k = _reload_with_dir(monkeypatch, tmp_path)
    assert k.read_refund_policy() == "POLICY BODY"
    assert k.read_faqs() == "FAQ BODY"


def test_missing_file_returns_empty(tmp_path, monkeypatch):
    k = _reload_with_dir(monkeypatch, tmp_path)  # empty dir, no files
    assert k.read_refund_policy() == ""
    assert k.read_faqs() == ""


def test_reflects_edits_immediately(tmp_path, monkeypatch):
    policy = tmp_path / "refund_policy.md"
    policy.write_text("v1", encoding="utf-8")
    k = _reload_with_dir(monkeypatch, tmp_path)
    assert k.read_refund_policy() == "v1"
    policy.write_text("v2", encoding="utf-8")  # edited live
    assert k.read_refund_policy() == "v2"


def test_default_dir_has_shipped_documents(monkeypatch):
    # With no override, the real backend/knowledge docs must be present + non-empty.
    monkeypatch.delenv("KNOWLEDGE_DIR", raising=False)
    k = importlib.reload(knowledge)
    assert "Refund Policy" in k.read_refund_policy()
    assert "FAQ" in k.read_faqs() or "Q:" in k.read_faqs()

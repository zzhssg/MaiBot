from src.agent.worker.attachment import build_attachment_hint, needs_worker


def test_needs_worker_for_non_text_formats():
    assert needs_worker(".pdf") is True
    assert needs_worker(".PDF") is True
    assert needs_worker(".docx") is True
    assert needs_worker(".txt") is False
    assert needs_worker(".md") is False


def test_hint_marks_mode_and_local_path():
    text = build_attachment_hint([
        {"name": "a.pdf", "file_ref": "ref1", "path": "/tmp/a.blob"},
        {"name": "b.txt", "file_ref": "ref2", "path": "/tmp/b.blob"},
    ])

    assert "a.pdf" in text and "/tmp/a.blob" in text
    assert "需 dsh_task" in text
    assert "b.txt" in text and "可直接读" in text

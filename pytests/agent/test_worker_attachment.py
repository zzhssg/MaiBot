from src.agent.worker.attachment import attachment_mode, build_attachment_hint


def test_attachment_mode_routes_by_type():
    assert attachment_mode("a.txt") == "可直接 files_read_text"
    assert attachment_mode("a.MD") == "可直接 files_read_text"
    assert attachment_mode("a.pdf") == "先用 files_convert 转 Markdown 再读"
    assert attachment_mode("a.docx") == "需 dsh_task 处理"
    assert attachment_mode("a.zip") == "需 dsh_task 处理"


def test_hint_marks_modes_and_local_path():
    text = build_attachment_hint([
        {"name": "a.pdf", "file_ref": "ref1", "path": "/tmp/a.blob"},
        {"name": "b.txt", "file_ref": "ref2", "path": "/tmp/b.blob"},
    ])

    assert "a.pdf" in text and "/tmp/a.blob" in text
    assert "files_convert" in text
    assert "b.txt" in text and "可直接读" in text

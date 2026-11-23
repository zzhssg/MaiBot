from src.webui.services.ai_help_references import match_help_references


def test_dsh_worker_question_matches_reference():
    results = match_help_references("怎么配置 dsh worker 让麦麦能用电脑")

    assert any(item["source_id"] == "help:dsh-worker" for item in results)


def test_dsh_worker_reference_needs_both_topic_and_config_intent():
    results = match_help_references("dsh worker 是什么")

    assert all(item["source_id"] != "help:dsh-worker" for item in results)

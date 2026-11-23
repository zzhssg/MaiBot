import pytest

from src.chat.replyer.maisaka_expression_selector import MaisakaExpressionSelector


def _candidates() -> list[dict[str, object]]:
    return [{"id": index, "situation": f"情景{index}", "style": f"表达{index}", "count": 1} for index in range(12)]


@pytest.mark.asyncio
async def test_candidate_load_reuses_cached_rows(monkeypatch) -> None:
    selector = MaisakaExpressionSelector()
    calls: list[str] = []

    def loader(session_id: str) -> list[dict[str, object]]:
        calls.append(session_id)
        return _candidates()

    monkeypatch.setattr(selector, "_load_all_expression_candidates", loader)

    first = await selector._load_expression_candidates("session-1")
    second = await selector._load_expression_candidates("session-1")

    assert calls == ["session-1"]
    assert first == second
    assert first is not second


@pytest.mark.asyncio
async def test_candidate_cache_expires(monkeypatch) -> None:
    selector = MaisakaExpressionSelector()
    calls: list[str] = []

    def loader(session_id: str) -> list[dict[str, object]]:
        calls.append(session_id)
        return _candidates()

    monkeypatch.setattr(selector, "_load_all_expression_candidates", loader)

    await selector._load_expression_candidates("session-1")
    _, cached = selector._candidate_cache["session-1"]
    selector._candidate_cache["session-1"] = (0.0, cached)
    await selector._load_expression_candidates("session-1")

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_returned_candidates_do_not_alias_cache(monkeypatch) -> None:
    selector = MaisakaExpressionSelector()
    monkeypatch.setattr(selector, "_load_all_expression_candidates", lambda session_id: _candidates())

    first = await selector._load_expression_candidates("session-1")
    first[0]["style"] = "被调用方改写"

    third = await selector._load_expression_candidates("session-1")

    assert third[0]["style"] == "表达0"

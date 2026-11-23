from types import SimpleNamespace

from src.maisaka.context.injection_cache import PlannerInjectionCache


def _message(message_id: str) -> SimpleNamespace:
    return SimpleNamespace(message_id=message_id)


def test_same_batch_reuses_injections() -> None:
    cache = PlannerInjectionCache()
    key = cache.build_key("m3", [_message("m1"), _message("m2")])

    cache.put(key, ["【人物画像】…", "【启发式记忆】…"])

    assert cache.get(key) == ["【人物画像】…", "【启发式记忆】…"]
    assert cache.get(cache.build_key("m3", [_message("m1"), _message("m2")])) == cache.get(key)


def test_new_message_invalidates_cache() -> None:
    cache = PlannerInjectionCache()
    cache.put(cache.build_key("m3", [_message("m1"), _message("m2")]), ["旧注入"])

    assert cache.get(cache.build_key("m4", [_message("m1"), _message("m2"), _message("m4")])) is None


def test_clear_drops_cached_turn() -> None:
    cache = PlannerInjectionCache()
    key = cache.build_key("m1", [_message("m1")])
    cache.put(key, ["注入"])

    cache.clear()

    assert cache.get(key) is None


def test_returned_list_does_not_alias_cache() -> None:
    cache = PlannerInjectionCache()
    key = cache.build_key("m1", [_message("m1")])
    cache.put(key, ["注入"])

    cache.get(key).append("被调用方修改")

    assert cache.get(key) == ["注入"]

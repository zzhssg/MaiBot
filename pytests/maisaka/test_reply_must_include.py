"""reply 的 must_include 与「交付」档：worker 的事实必须能原样到达最终回复。"""

from src.chat.replyer.reply_prompt import ChatReplyPromptMixin
from src.common.i18n import use_locale
from src.maisaka.builtin_tool.reply import get_tool_spec


def test_reply_schema_exposes_must_include_and_delivery_style() -> None:
    spec = get_tool_spec()
    properties = spec.parameters_schema["properties"]

    assert properties["must_include"]["type"] == "array"
    assert "交付" in properties["reply_style"]["enum"]
    assert "不要原文引用" not in properties["chat_anlyze"]["description"]


def test_must_include_block_keeps_facts_verbatim() -> None:
    with use_locale("zh-CN"):
        block = ChatReplyPromptMixin._build_must_include_block(
            ['<a id="-双语--bilingual"></a>', "README.md", "  "],
        )

    assert '<a id="-双语--bilingual"></a>' in block
    assert "README.md" in block
    assert "逐字" in block
    assert "  \n" not in block


def test_must_include_block_is_empty_without_facts() -> None:
    assert ChatReplyPromptMixin._build_must_include_block(None) == ""
    assert ChatReplyPromptMixin._build_must_include_block([]) == ""
    assert ChatReplyPromptMixin._build_must_include_block(["  "]) == ""


def test_must_include_block_follows_locale() -> None:
    with use_locale("en-US"):
        block = ChatReplyPromptMixin._build_must_include_block(["README.md"])
    assert "verbatim" in block

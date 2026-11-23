from src.chat.replyer.reply_prompt import ChatReplyPromptMixin
from src.common.i18n import use_locale


def test_delivery_override_beats_chat_persona():
    with use_locale("zh-CN"):
        text = ChatReplyPromptMixin._build_delivery_override()

    assert "交付模式" in text
    assert "不接任务" in text
    assert "不知道" in text

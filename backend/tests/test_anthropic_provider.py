"""Tests for Anthropic adapter auth-mode selection and header parsing."""

import pytest

from app.llm import anthropic_provider as ap
from app.llm.anthropic_provider import AnthropicProvider, _parse_custom_headers
from app.llm.base import ImageInput


class _FakeAsyncAnthropic:
    """Captures constructor kwargs instead of making network calls."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs


@pytest.fixture(autouse=True)
def _patch_sdk(monkeypatch):
    # The provider imports AsyncAnthropic lazily inside __init__, so patch the
    # symbol on the anthropic module it imports from.
    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    _FakeAsyncAnthropic.last_kwargs = {}
    yield


def _set(monkeypatch, **values):
    for key, val in values.items():
        monkeypatch.setattr(ap.settings, key, val)


def test_parse_single_header_with_json_value():
    raw = 'x-portkey-metadata: {"_user":"a","provider":"claude"}'
    headers = _parse_custom_headers(raw)
    assert headers == {
        "x-portkey-metadata": '{"_user":"a","provider":"claude"}'
    }


def test_parse_multiple_headers_and_blank_lines():
    raw = "A: 1\n\nB: two: with colon\n  \nC:3"
    headers = _parse_custom_headers(raw)
    assert headers == {"A": "1", "B": "two: with colon", "C": "3"}


def test_direct_api_key_mode(monkeypatch):
    _set(
        monkeypatch,
        ANTHROPIC_API_KEY="sk-test",
        ANTHROPIC_AUTH_TOKEN="",
        ANTHROPIC_BASE_URL="",
        ANTHROPIC_CUSTOM_HEADERS="",
    )
    AnthropicProvider()
    assert _FakeAsyncAnthropic.last_kwargs == {"api_key": "sk-test"}


def test_gateway_mode_passes_none_api_key_and_headers(monkeypatch):
    _set(
        monkeypatch,
        ANTHROPIC_API_KEY="",
        ANTHROPIC_AUTH_TOKEN="dummy",
        ANTHROPIC_BASE_URL="http://gw/proxy",
        ANTHROPIC_CUSTOM_HEADERS="x-portkey: v",
    )
    AnthropicProvider()
    kwargs = _FakeAsyncAnthropic.last_kwargs
    assert kwargs["api_key"] is None  # must not be "" (would shadow bearer)
    assert kwargs["auth_token"] == "dummy"
    assert kwargs["base_url"] == "http://gw/proxy"
    assert kwargs["default_headers"] == {"x-portkey": "v"}


def test_raises_when_nothing_configured(monkeypatch):
    _set(
        monkeypatch,
        ANTHROPIC_API_KEY="",
        ANTHROPIC_AUTH_TOKEN="",
        ANTHROPIC_BASE_URL="",
        ANTHROPIC_CUSTOM_HEADERS="",
    )
    with pytest.raises(RuntimeError) as exc:
        AnthropicProvider()
    assert "not configured" in str(exc.value)


class _CaptureMessages:
    """Captures the messages.create payload."""

    def __init__(self):
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs

        class _Block:
            type = "text"
            text = "{}"

        class _Resp:
            content = [_Block()]

        return _Resp()


@pytest.mark.asyncio
async def test_complete_builds_image_content_block(monkeypatch):
    _set(monkeypatch, ANTHROPIC_API_KEY="sk-test")
    provider = AnthropicProvider()
    cap = _CaptureMessages()
    provider._client.messages = cap  # type: ignore[attr-defined]

    await provider.complete(
        "sys",
        "describe this",
        images=[ImageInput(media_type="image/png", data="QUJD")],
    )
    content = cap.last_kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    # First block is the image, last is the text prompt.
    assert content[0]["type"] == "image"
    assert content[0]["source"]["type"] == "base64"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"] == "QUJD"
    assert content[-1] == {"type": "text", "text": "describe this"}


@pytest.mark.asyncio
async def test_complete_without_images_uses_plain_string(monkeypatch):
    _set(monkeypatch, ANTHROPIC_API_KEY="sk-test")
    provider = AnthropicProvider()
    cap = _CaptureMessages()
    provider._client.messages = cap  # type: ignore[attr-defined]

    await provider.complete("sys", "just text")
    content = cap.last_kwargs["messages"][0]["content"]
    assert content == "just text"

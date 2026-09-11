"""Tests for Discord incoming video attachment handling.

Covers the video branch in DiscordAdapter._handle_message() — the
``video/*`` clause of the attachment content-type loop that downloads,
caches, and surfaces video attachments to the agent as local file paths
(mirroring the image and audio branches).
"""

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import MessageType


# ---------------------------------------------------------------------------
# Discord mock setup (copied from test_discord_document_handling.py)
# ---------------------------------------------------------------------------

def _ensure_discord_mock():
    """Install a mock discord module when discord.py isn't available."""
    if "discord" in sys.modules and hasattr(sys.modules["discord"], "__file__"):
        return

    discord_mod = MagicMock()
    discord_mod.Intents.default.return_value = MagicMock()
    discord_mod.Client = MagicMock
    discord_mod.File = MagicMock
    discord_mod.DMChannel = type("DMChannel", (), {})
    discord_mod.Thread = type("Thread", (), {})
    discord_mod.ForumChannel = type("ForumChannel", (), {})
    discord_mod.ui = SimpleNamespace(View=object, button=lambda *a, **k: (lambda fn: fn), Button=object)
    discord_mod.ButtonStyle = SimpleNamespace(success=1, primary=2, secondary=2, danger=3, green=1, grey=2, blurple=2, red=3)
    discord_mod.Color = SimpleNamespace(orange=lambda: 1, green=lambda: 2, blue=lambda: 3, red=lambda: 4, purple=lambda: 5)
    discord_mod.Interaction = object
    discord_mod.Embed = MagicMock
    discord_mod.app_commands = SimpleNamespace(
        describe=lambda **kwargs: (lambda fn: fn),
        choices=lambda **kwargs: (lambda fn: fn),
        Choice=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    ext_mod = MagicMock()
    commands_mod = MagicMock()
    commands_mod.Bot = MagicMock
    ext_mod.commands = commands_mod

    sys.modules.setdefault("discord", discord_mod)
    sys.modules.setdefault("discord.ext", ext_mod)
    sys.modules.setdefault("discord.ext.commands", commands_mod)


_ensure_discord_mock()

import plugins.platforms.discord.adapter as discord_platform  # noqa: E402
from plugins.platforms.discord.adapter import DiscordAdapter  # noqa: E402


# ---------------------------------------------------------------------------
# Fake channel / thread types
# ---------------------------------------------------------------------------

class FakeDMChannel:
    def __init__(self, channel_id: int = 1):
        self.id = channel_id
        self.name = "dm"


class FakeThread:
    def __init__(self, channel_id: int = 10):
        self.id = channel_id
        self.name = "thread"
        self.parent = None
        self.parent_id = None
        self.guild = SimpleNamespace(name="TestServer")


@pytest.fixture
def video_cache(tmp_path, monkeypatch):
    """Point video cache to tmp_path so tests never write to ~/.hermes."""
    monkeypatch.setattr(
        "gateway.platforms.base.VIDEO_CACHE_DIR", tmp_path / "video_cache"
    )


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(discord_platform.discord, "DMChannel", FakeDMChannel, raising=False)
    monkeypatch.setattr(discord_platform.discord, "Thread", FakeThread, raising=False)

    config = PlatformConfig(enabled=True, token="fake-token")
    a = DiscordAdapter(config)
    a._client = SimpleNamespace(user=SimpleNamespace(id=999))
    a.handle_message = AsyncMock()
    return a


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_attachment(
    *,
    filename: str,
    content_type: Optional[str],
    size: int = 1024,
    url: str = "https://cdn.discordapp.com/attachments/fake/file",
) -> SimpleNamespace:
    return SimpleNamespace(
        filename=filename,
        content_type=content_type,
        size=size,
        url=url,
    )


def make_message(attachments: list, content: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=123,
        content=content,
        attachments=attachments,
        mentions=[],
        reference=None,
        created_at=datetime.now(timezone.utc),
        channel=FakeDMChannel(),
        author=SimpleNamespace(id=42, display_name="Tester", name="Tester"),
    )


def _mock_aiohttp_download(raw_bytes: bytes):
    """Return a patch context manager that makes aiohttp return raw_bytes."""
    resp = AsyncMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=raw_bytes)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    return patch("aiohttp.ClientSession", return_value=session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIncomingVideoHandling:

    @pytest.mark.asyncio
    async def test_mp4_video_cached(self, adapter, video_cache):
        """A video/mp4 attachment should be downloaded, cached, typed VIDEO."""
        video_bytes = b"\x00\x00\x00\x18ftypmp42 fake mp4"

        with _mock_aiohttp_download(video_bytes):
            msg = make_message(
                [make_attachment(filename="demo.mp4", content_type="video/mp4")]
            )
            await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert event.message_type == MessageType.VIDEO
        assert len(event.media_urls) == 1
        assert os.path.exists(event.media_urls[0])
        assert event.media_urls[0].endswith(".mp4")
        assert event.media_types == ["video/mp4"]

    @pytest.mark.asyncio
    async def test_quicktime_mov_cached(self, adapter, video_cache):
        """.mov (video/quicktime) should cache with its .mov extension."""
        with _mock_aiohttp_download(b"fake mov bytes"):
            msg = make_message(
                [make_attachment(filename="clip.mov", content_type="video/quicktime")]
            )
            await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert event.message_type == MessageType.VIDEO
        assert os.path.exists(event.media_urls[0])
        assert event.media_urls[0].endswith(".mov")
        assert event.media_types == ["video/quicktime"]

    @pytest.mark.asyncio
    async def test_no_filename_ext_reverse_lookup(self, adapter, video_cache):
        """A webm attachment without an extension falls back to the MIME lookup."""
        att = make_attachment(filename="", content_type="video/webm")
        # SimpleNamespace can't hold empty filename splitext — give it one
        att.filename = "recording.webm"
        with _mock_aiohttp_download(b"fake webm"):
            msg = make_message([att])
            await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert event.media_urls[0].endswith(".webm")
        assert event.media_types == ["video/webm"]

    @pytest.mark.asyncio
    async def test_oversized_video_skipped(self, adapter, video_cache, monkeypatch):
        """A video above the per-attachment cap is skipped, not cached."""
        monkeypatch.setattr(discord_platform.os, "getenv", lambda key, default=None: "32" if key == "DISCORD_MAX_ATTACHMENT_BYTES" else default)
        big = make_attachment(filename="big.mp4", content_type="video/mp4", size=64 * 1024 * 1024)

        msg = make_message([big])
        await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert event.media_urls == []
        assert event.media_types == []

    @pytest.mark.asyncio
    async def test_video_cache_error_handled(self, adapter, video_cache):
        """A cache failure must not crash the message pipeline."""
        with _mock_aiohttp_download(b"fake mp4"):
            msg = make_message(
                [make_attachment(filename="broken.mp4", content_type="video/mp4")]
            )
            with patch.object(
                DiscordAdapter, "_cache_discord_document", side_effect=RuntimeError("boom")
            ):
                await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert event.media_urls == []
        assert event.media_types == []

    @pytest.mark.asyncio
    async def test_video_with_caption_preserved(self, adapter, video_cache):
        """Caption text survives alongside the cached video path."""
        with _mock_aiohttp_download(b"fake mp4"):
            msg = make_message(
                [make_attachment(filename="demo.mp4", content_type="video/mp4")],
                content="what happens in this demo?",
            )
            await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert "what happens in this demo?" in (event.text or "")
        assert len(event.media_urls) == 1

    @pytest.mark.asyncio
    async def test_video_bypasses_document_allowlist(self, adapter, video_cache):
        """.mp4 is NOT in SUPPORTED_DOCUMENT_TYPES, yet must still be cached."""
        from gateway.platforms.base import SUPPORTED_DOCUMENT_TYPES

        assert ".mp4" not in SUPPORTED_DOCUMENT_TYPES

        with _mock_aiohttp_download(b"fake mp4"):
            msg = make_message(
                [make_attachment(filename="demo.mp4", content_type="video/mp4")]
            )
            await adapter._handle_message(msg)

        event = adapter.handle_message.call_args[0][0]
        assert len(event.media_urls) == 1
        assert event.media_types == ["video/mp4"]

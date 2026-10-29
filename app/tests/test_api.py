"""HTTP handler tests for ``main`` using mocked ``web.Request`` (no TestServer)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import main


@pytest.fixture
def mock_dqueue(monkeypatch):
    d = MagicMock()
    d.initialize = AsyncMock(return_value=None)
    d.add = AsyncMock(return_value={"status": "ok"})
    d.cancel = AsyncMock(return_value={"status": "ok"})
    d.clear = AsyncMock(return_value={"status": "ok"})
    d.start_pending = AsyncMock(return_value={"status": "ok"})
    d.cancel_add = MagicMock()
    d.queue = MagicMock()
    d.done = MagicMock()
    d.pending = MagicMock()
    d.queue.saved_items = MagicMock(return_value=[])
    d.done.saved_items = MagicMock(return_value=[])
    d.pending.saved_items = MagicMock(return_value=[])
    d.queue.items = MagicMock(return_value=[])
    d.done.items = MagicMock(return_value=[])
    d.pending.items = MagicMock(return_value=[])
    d.get = MagicMock(return_value=([], []))
    monkeypatch.setattr(main, "dqueue", d)
    return d


def _valid_video_add_body(**kwargs):
    base = {
        "url": "https://example.com/watch?v=1",
        "download_type": "video",
        "codec": "auto",
        "format": "any",
        "quality": "best",
        "ytdl_options_presets": [],
        "ytdl_options_overrides": "",
    }
    base.update(kwargs)
    return base


def _json_request(body: dict | None):
    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(return_value=body)
    return req


@pytest.mark.asyncio
async def test_add_ok(mock_dqueue):
    req = _json_request(_valid_video_add_body())
    resp = await main.add(req)
    assert resp.status == 200
    text = resp.text
    data = json.loads(text)
    assert data["status"] == "ok"
    mock_dqueue.add.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_passes_preset_and_overrides(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Preset A": {"writesubtitles": True}})
    monkeypatch.setattr(main.config, "ALLOW_YTDL_OPTIONS_OVERRIDES", True)
    req = _json_request(
        _valid_video_add_body(
            ytdl_options_presets=["Preset A"],
            ytdl_options_overrides='{"writesubtitles": true}',
        )
    )
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[13] == ["Preset A"]
    assert call.args[14] == {"writesubtitles": True}


@pytest.mark.asyncio
async def test_add_legacy_string_preset_normalized(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Legacy": {}})
    body = _valid_video_add_body()
    del body["ytdl_options_presets"]
    body["ytdl_options_preset"] = "Legacy"
    req = _json_request(body)
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call.args[13] == ["Legacy"]


@pytest.mark.asyncio
async def test_add_missing_url_returns_400(mock_dqueue):
    req = _json_request({"download_type": "video", "quality": "best", "format": "any"})
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)
    mock_dqueue.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_invalid_download_type(mock_dqueue):
    req = _json_request(_valid_video_add_body(download_type="invalid"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_video_quality(mock_dqueue):
    req = _json_request(_valid_video_add_body(quality="9999"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_subtitle_language(mock_dqueue):
    req = _json_request(
        {
            "url": "https://example.com/v",
            "download_type": "captions",
            "codec": "auto",
            "format": "srt",
            "quality": "best",
            "subtitle_language": "bad language!",
        }
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_json_body(mock_dqueue):
    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(side_effect=json.JSONDecodeError("msg", "", 0))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_invalid_ytdl_options_override_json(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_overrides="{bad json}"))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_rejects_ytdl_options_overrides_when_disabled(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_overrides='{"exec": "rm -rf /"}'))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_add_allows_any_ytdl_options_override_key_when_enabled(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "ALLOW_YTDL_OPTIONS_OVERRIDES", True)
    req = _json_request(_valid_video_add_body(ytdl_options_overrides='{"exec": "echo hi"}'))
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[14] == {"exec": "echo hi"}


@pytest.mark.asyncio
async def test_add_unknown_ytdl_preset(mock_dqueue):
    req = _json_request(_valid_video_add_body(ytdl_options_presets=["Missing"]))
    with pytest.raises(web.HTTPBadRequest):
        await main.add(req)


@pytest.mark.asyncio
async def test_delete_missing_ids(mock_dqueue):
    req = _json_request({"where": "queue"})
    with pytest.raises(web.HTTPBadRequest):
        await main.delete(req)


@pytest.mark.asyncio
async def test_delete_queue_calls_cancel(mock_dqueue):
    req = _json_request({"where": "queue", "ids": ["http://x"]})
    resp = await main.delete(req)
    assert resp.status == 200
    mock_dqueue.cancel.assert_awaited_once_with(["http://x"])


@pytest.mark.asyncio
async def test_start_pending(mock_dqueue):
    req = _json_request({"ids": ["a"]})
    resp = await main.start(req)
    assert resp.status == 200
    mock_dqueue.start_pending.assert_awaited_once_with(["a"])


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"ids": "abc"}, {"ids": []}, {"ids": [1, 2]}])
async def test_start_rejects_malformed_ids(mock_dqueue, body):
    req = _json_request(body)
    with pytest.raises(web.HTTPBadRequest):
        await main.start(req)
    mock_dqueue.start_pending.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"where": "queue"},
        {"where": "queue", "ids": "abc"},
        {"where": "queue", "ids": []},
        {"where": "queue", "ids": [1, 2]},
    ],
)
async def test_delete_rejects_malformed_ids(mock_dqueue, body):
    req = _json_request(body)
    with pytest.raises(web.HTTPBadRequest):
        await main.delete(req)
    mock_dqueue.cancel.assert_not_awaited()
    mock_dqueue.clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_shape(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.history(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert set(data.keys()) == {"done", "queue", "pending"}


@pytest.mark.asyncio
async def test_history_reads_in_memory_queues_not_disk_state(mock_dqueue):
    fake_queue_dl = MagicMock()
    fake_queue_dl.info = {"id": "q1", "title": "Queued"}
    fake_done_dl = MagicMock()
    fake_done_dl.info = {"id": "d1", "title": "Done"}
    fake_pending_dl = MagicMock()
    fake_pending_dl.info = {"id": "p1", "title": "Pending"}
    mock_dqueue.queue.items.return_value = [("q1", fake_queue_dl)]
    mock_dqueue.done.items.return_value = [("d1", fake_done_dl)]
    mock_dqueue.pending.items.return_value = [("p1", fake_pending_dl)]

    req = MagicMock(spec=web.Request)
    resp = await main.history(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert [item["id"] for item in data["queue"]] == ["q1"]
    assert [item["id"] for item in data["done"]] == ["d1"]
    assert [item["id"] for item in data["pending"]] == ["p1"]
    mock_dqueue.queue.saved_items.assert_not_called()
    mock_dqueue.done.saved_items.assert_not_called()
    mock_dqueue.pending.saved_items.assert_not_called()


@pytest.mark.asyncio
async def test_version_json(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.version(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert "yt-dlp" in body and "version" in body


@pytest.mark.asyncio
async def test_presets_endpoint_returns_names(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.config, "YTDL_OPTIONS_PRESETS", {"Preset B": {}, "Preset A": {}})
    req = MagicMock(spec=web.Request)
    resp = await main.presets(req)
    assert resp.status == 200
    assert json.loads(resp.text) == {"presets": ["Preset A", "Preset B"]}


@pytest.mark.asyncio
async def test_cookie_status(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.cookie_status(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data.get("status") == "ok"
    assert "has_cookies" in data


@pytest.mark.asyncio
async def test_options_add_cors(mock_dqueue):
    req = MagicMock(spec=web.Request)
    resp = await main.add_cors(req)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_upload_cookies_missing_field(mock_dqueue):
    req = MagicMock(spec=web.Request)
    reader = MagicMock()
    field = MagicMock()
    field.name = "wrongname"
    reader.next = AsyncMock(side_effect=[field, None])
    req.multipart = AsyncMock(return_value=reader)
    resp = await main.upload_cookies(req)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_add_legacy_format_migrated(mock_dqueue):
    req = _json_request({"url": "https://example.com/v", "format": "m4a", "quality": "best"})
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[1] == "audio"


@pytest.mark.asyncio
async def test_add_passes_clip_bounds_to_queue(mock_dqueue):
    req = _json_request(
        _valid_video_add_body(clip_start="2:26", clip_end="3:24"),
    )
    resp = await main.add(req)
    assert resp.status == 200
    call = mock_dqueue.add.await_args
    assert call is not None
    assert call.args[15] == pytest.approx(146.0)
    assert call.args[16] == pytest.approx(204.0)


@pytest.mark.asyncio
async def test_subscribe_rejects_clip_options(mock_dqueue, monkeypatch):
    monkeypatch.setattr(main.submgr, "add_subscription", AsyncMock())
    req = _json_request(
        {
            **_valid_video_add_body(clip_start="10"),
            "check_interval_minutes": 60,
        }
    )
    with pytest.raises(web.HTTPBadRequest):
        await main.subscribe(req)
    main.submgr.add_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_subscriptions_update_invalid_enabled_returns_error_not_500(mock_dqueue):
    req = _json_request({"id": "nonexistent", "enabled": "maybe"})
    resp = await main.subscriptions_update(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["status"] == "error"


@pytest.mark.asyncio
async def test_subscriptions_update_invalid_interval_returns_error_not_500(mock_dqueue):
    req = _json_request({"id": "nonexistent", "check_interval_minutes": "abc"})
    resp = await main.subscriptions_update(req)
    assert resp.status == 200
    body = json.loads(resp.text)
    assert body["status"] == "error"


def test_is_within_state_dir_blocks_state_subtree():
    state_dir = main._STATE_DIR_REAL
    assert main._is_within_state_dir(state_dir)
    assert main._is_within_state_dir(os.path.join(state_dir, "cookies.txt"))
    assert main._is_within_state_dir(os.path.join(state_dir, "queue", "item.json"))


def test_is_within_state_dir_allows_sibling_downloads():
    download_dir = os.path.realpath(main.config.DOWNLOAD_DIR)
    assert not main._is_within_state_dir(os.path.join(download_dir, "video.mp4"))
    assert not main._is_within_state_dir("/tmp/unrelated/video.mp4")


@pytest.mark.asyncio
async def test_download_blocks_state_dir_files(monkeypatch):
    download_dir = Path(main.config.DOWNLOAD_DIR)
    state_dir = download_dir / ".metube"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "cookies.txt").write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    (download_dir / "video.mp4").write_bytes(b"video")
    # request.path is already percent-decoded by aiohttp; state_dir_guard must
    # not decode it a second time, or a filename containing a literal '%'
    # gets mangled into a false 404.
    percent_filename = "100% done.mp4"
    (download_dir / percent_filename).write_bytes(b"percent video")

    monkeypatch.setattr(main.config, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(main, "_STATE_DIR_REAL", os.path.realpath(str(state_dir)))

    try:
        async with TestClient(TestServer(main.app)) as client:
            blocked = await client.get("/download/.metube/cookies.txt")
            assert blocked.status == 404

            allowed = await client.get("/download/video.mp4")
            assert allowed.status == 200
            assert await allowed.read() == b"video"

            percent_resp = await client.get("/download/" + quote(percent_filename))
            assert percent_resp.status == 200
            assert await percent_resp.read() == b"percent video"
    finally:
        (state_dir / "cookies.txt").unlink(missing_ok=True)
        (download_dir / "video.mp4").unlink(missing_ok=True)
        (download_dir / percent_filename).unlink(missing_ok=True)
        state_dir.rmdir()


@pytest.mark.asyncio
async def test_analyse_returns_real_format_options_without_downloading(monkeypatch):
    called = {}
    class FakeYDL:
        def __init__(self, opts):
            called['opts'] = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download=False):
            called.update(url=url, download=download)
            return {'title': 'Real clip', 'duration': 42, 'thumbnail': 'https://cdn.example/thumb.jpg',
                    'formats': [{'format_id': '18', 'ext': 'mp4', 'height': 360, 'vcodec': 'avc1', 'acodec': 'mp4a'},
                                {'format_id': '140', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'aac'}]}
    monkeypatch.setattr(main, 'YoutubeDL', FakeYDL)
    monkeypatch.setattr(main, 'validate_url', lambda url, allow_private=False: None)
    resp = await main.analyse(_json_request({'url': 'https://example.com/video'}))
    data = json.loads(resp.text)
    assert data['title'] == 'Real clip'
    assert {item['type'] for item in data['options']} == {'video', 'audio'}
    assert called['download'] is False
    assert called['opts']['cookiefile'] is None


@pytest.mark.asyncio
async def test_analyse_generic_mp4_infers_video_from_real_format_ext(monkeypatch):
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download=False):
            return {'title': 'flower', 'formats': [{'format_id': '0', 'ext': 'mp4', 'video_ext': 'mp4', 'audio_ext': 'none'}]}
    monkeypatch.setattr(main, 'YoutubeDL', FakeYDL)
    monkeypatch.setattr(main, 'validate_url', lambda url, allow_private=False: None)
    response = await main.analyse(_json_request({'url': 'https://example.com/flower.mp4'}))
    assert 'video' in {option['type'] for option in json.loads(response.text)['options']}


@pytest.mark.asyncio
async def test_analyse_rejects_invalid_url_without_extractor(monkeypatch):
    monkeypatch.setattr(main, 'validate_url', lambda url, allow_private=False: 'blocked')
    monkeypatch.setattr(main, 'YoutubeDL', lambda *_: pytest.fail('extractor must not run'))
    with pytest.raises(web.HTTPBadRequest):
        await main.analyse(_json_request({'url': 'https://127.0.0.1/private'}))


@pytest.mark.asyncio
async def test_music_alternatives_search_uses_anonymous_scsearch(monkeypatch):
    called = {'queries': []}

    class FakeYDL:
        def __init__(self, opts):
            called['opts'] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, query, download=False):
            called['queries'].append(query)
            if query.startswith('scsearch8:'):
                called['download'] = download
                return {'entries': [{
                    'title': 'Track (cover)', 'uploader': 'Artist', 'duration': 123,
                    'webpage_url': 'https://soundcloud.com/a/track', 'extractor_key': 'Soundcloud',
                }]}
            raise RuntimeError('metadata unavailable')

    monkeypatch.setattr(main, 'YoutubeDL', FakeYDL, raising=False)
    req = _json_request({'url': 'https://music.youtube.com/watch?v=abcdefghijk', 'title': 'Track', 'artist': 'Artist'})
    resp = await main.music_alternatives(req)
    data = json.loads(resp.text)
    # Manual metadata avoids an unnecessary blocked YouTube request.
    assert called['queries'] == ['scsearch8:Artist Track']
    assert called['download'] is False
    assert called['opts']['cookiefile'] is None
    assert data['results'][0]['platform'] == 'SoundCloud'
    assert data['results'][0]['url'] == 'https://soundcloud.com/a/track'


@pytest.mark.asyncio
async def test_music_alternatives_manual_query_when_source_metadata_unavailable(monkeypatch):
    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, query, download=False):
            assert query == 'scsearch8:Manual Artist Manual Title'
            return {'entries': []}

    monkeypatch.setattr(main, 'YoutubeDL', FakeYDL, raising=False)
    req = _json_request({'url': 'https://music.youtube.com/watch?v=abcdefghijk', 'title': 'Manual Title', 'artist': 'Manual Artist'})
    resp = await main.music_alternatives(req)
    assert json.loads(resp.text)['results'] == []


@pytest.mark.asyncio
async def test_spotify_alternatives_reads_public_oembed_and_normalizes_locale(monkeypatch):
    calls = {}
    class Response:
        status = 200
        def raise_for_status(self): pass
        async def json(self, content_type=None): return {"title": "Real Song", "author_name": "Spotify"}
    class Client:
        def __init__(self, **kwargs): calls['timeout'] = kwargs.get('timeout')
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, url, **kwargs):
            calls.update(url=url, kwargs=kwargs)
            class RequestContext:
                async def __aenter__(self): return Response()
                async def __aexit__(self, *args): pass
            return RequestContext()
    monkeypatch.setattr(main, 'aiohttp', type('Aiohttp', (), {'ClientSession': Client, 'ClientTimeout': lambda **kwargs: kwargs}), raising=False)
    monkeypatch.setattr(main, 'YoutubeDL', lambda *_: pytest.fail('metadata from oEmbed should avoid source extraction'), raising=False)
    async def public_artist(url): return 'Real Artist'
    monkeypatch.setattr(main, '_spotify_track_artist', public_artist)
    monkeypatch.setattr(main, '_search_music_candidates', lambda query: [], raising=False)
    resp = await main.music_alternatives(_json_request({'url': 'https://open.spotify.com/intl-es/track/5pS1hoVW3gYiqE54R04Egg'}))
    data = json.loads(resp.text)
    assert calls['url'] == 'https://open.spotify.com/oembed'
    assert calls['kwargs']['params']['url'] == 'https://open.spotify.com/track/5pS1hoVW3gYiqE54R04Egg'
    assert data['track']['title'] == 'Real Song' and data['track']['artist'] == 'Real Artist'
    assert data['query'] == 'Real Artist Real Song'


@pytest.mark.asyncio
async def test_music_alternatives_youtube_oembed_then_searches_without_download(monkeypatch):
    calls = {}
    class Response:
        status_code = 200
        status = 200
        def raise_for_status(self): pass
        async def json(self, content_type=None): return {'title': 'Actual Track — Actual Artist', 'author_name': 'Actual Artist'}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, url, **kwargs):
            calls['oembed_url'] = url
            class RequestContext:
                async def __aenter__(self): return Response()
                async def __aexit__(self, *args): pass
            return RequestContext()
    monkeypatch.setattr(main, 'aiohttp', type('Aiohttp', (), {'ClientSession': Client, 'ClientTimeout': lambda **kwargs: kwargs}), raising=False)
    def search(query): calls['query'] = query; return [{'title': 'candidate'}]
    monkeypatch.setattr(main, '_search_music_candidates', search, raising=False)
    resp = await main.music_alternatives(_json_request({'url': 'https://music.youtube.com/watch?v=Ka8GThTy5Lc'}))
    data = json.loads(resp.text)
    assert calls['oembed_url'] == 'https://www.youtube.com/oembed'
    assert calls['query'] == 'Actual Artist Actual Track'
    assert data['results'] == [{'title': 'candidate'}]

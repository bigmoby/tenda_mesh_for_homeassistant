"""Tests for Tenda Mesh API."""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from multidict import CIMultiDict
import pytest

from custom_components.tenda_mesh.api import (
    TendaAuthError,
    TendaConnectionError,
    TendaLocalClient,
    _non_empty,
    _rand,
    _tenda_decrypt,
    _tenda_password_hash,
)


@pytest.mark.asyncio
async def test_pure_helpers():
    """Test standalone helper functions."""
    # Test _rand
    r = _rand()
    assert isinstance(r, str)
    assert len(r) > 0

    # Test _tenda_password_hash
    assert _tenda_password_hash("test") == hashlib.md5(b"test").hexdigest().upper()

    # Test _non_empty
    assert _non_empty("test") == "test"
    assert _non_empty("") is None
    assert _non_empty(123) is None

    # Test _tenda_decrypt
    sign = "1234567890123456"
    payload = "Gzrcpb0huUN6TiOT4Mlm9A=="  # {"test": "ok"}
    decrypted = _tenda_decrypt(payload, sign)
    assert decrypted == {"test": "ok"}

    # Test _tenda_encrypt
    from custom_components.tenda_mesh.api import _tenda_encrypt

    encrypted = _tenda_encrypt({"test": "ok"}, sign)
    assert encrypted == payload


@pytest.mark.asyncio
async def test_auth_success():
    """Test successful authentication sequence."""
    session = aiohttp.ClientSession()
    client = TendaLocalClient("192.168.1.1", "admin", "password", session=session)

    def create_mock_resp(data, headers=None):
        m = MagicMock(spec=aiohttp.ClientResponse)
        m.status = 200
        m.text = AsyncMock(return_value=json.dumps(data))
        m.headers = headers or CIMultiDict()
        return m

    mock_resp_info = create_mock_resp({"stok": "123", "sign": "1234567890123456"})
    mock_resp_login = create_mock_resp({"status": 0})
    mock_resp_login.headers.add("Set-Cookie", "token=abc; path=/")
    mock_resp_stok = create_mock_resp({"stok": "123", "sign": "1234567890123456"})

    with (
        patch.object(client, "_get", new_callable=AsyncMock) as mock_get,
        patch.object(client, "_post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.side_effect = [mock_resp_info, mock_resp_stok]
        mock_post.return_value = mock_resp_login

        await client.ensure_authenticated()
        client._extract_manual_cookies(mock_resp_login)

        assert client.stok == "123"
        assert client.sign == "1234567890123456"
        assert client._manual_cookies["token"] == "abc"

    await session.close()


@pytest.mark.asyncio
async def test_auth_failure_status():
    """Test login failure status."""
    session = aiohttp.ClientSession()
    client = TendaLocalClient("192.168.1.1", "admin", "password", session=session)

    mock_resp = MagicMock(spec=aiohttp.ClientResponse)
    mock_resp.headers = CIMultiDict()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='{"status": -1}')

    with (
        patch.object(client, "_post", AsyncMock(return_value=mock_resp)),
        patch.object(client, "get_login_info", AsyncMock()),
        patch.object(client, "get_stok_cfg", AsyncMock()),
        pytest.raises(TendaAuthError),
    ):
        await client.ensure_authenticated()

    await session.close()


@pytest.mark.asyncio
async def test_api_http_errors():
    """Test HTTP error handling in _get and _post."""
    session = aiohttp.ClientSession()
    client = TendaLocalClient("192.168.1.1", "admin", "password", session=session)

    mock_resp = MagicMock(spec=aiohttp.ClientResponse)
    mock_resp.status = 500
    mock_resp.headers = CIMultiDict()
    mock_resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(),
        history=(),
        status=500,
    )

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_sess:
        mock_sess = MagicMock(spec=aiohttp.ClientSession)
        mock_sess.get = AsyncMock(return_value=mock_resp)
        mock_sess.post = AsyncMock(return_value=mock_resp)
        mock_get_sess.return_value = mock_sess

        with pytest.raises(TendaConnectionError):
            await client._get("/error")
        with pytest.raises(TendaConnectionError):
            await client._post("/error", data={})

    await session.close()


@pytest.mark.asyncio
async def test_json_or_text_fallback():
    """Test _json_or_text fallback to text."""
    client = TendaLocalClient("192.168.1.1", "admin", "password")
    mock_resp = MagicMock(spec=aiohttp.ClientResponse)
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="Not JSON Text")

    data = await client._json_or_text(mock_resp)
    assert data["status_code"] == 200
    assert data["text"] == "Not JSON Text"

    await client.close()


@pytest.mark.asyncio
async def test_get_modules_and_set_modules():
    """Test get/set modules with encryption."""
    session = aiohttp.ClientSession()
    client = TendaLocalClient("192.168.1.1", "admin", "password", session=session)
    client.stok = "123"
    client.sign = "1234567890123456"

    mock_resp = MagicMock(spec=aiohttp.ClientResponse)
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value='{"result": "ok"}')
    mock_resp.headers = CIMultiDict()

    with patch.object(client, "_get", AsyncMock(return_value=mock_resp)) as mock_get:
        data = await client.get_modules(["mod1"])
        assert data == {"result": "ok"}
        assert "mod1" in str(mock_get.call_args)

    with patch.object(client, "_post", AsyncMock(return_value=mock_resp)) as mock_post:
        # Encryption is automatic because sign is set
        data = await client.set_modules(["mod1"], {"test": "ok"})
        assert data == {"result": "ok"}

        # Verify mock_post was called with encrypted "data" key
        call_args = mock_post.call_args
        json_payload = call_args[1]["json"]
        assert "data" in json_payload
        assert isinstance(json_payload["data"], str)

    await session.close()


@pytest.mark.asyncio
async def test_api_branches():
    """Test specific API branches for coverage."""
    client = TendaLocalClient("1.1.1.1", "u", "p")

    # 1. stokCfg extraction via get_stok_cfg
    mock_resp = MagicMock(spec=aiohttp.ClientResponse)
    mock_resp.text = AsyncMock(
        return_value='{"stokCfg": {"stok": "s1", "sign": "si1"}}'
    )
    with patch.object(client, "_get", AsyncMock(return_value=mock_resp)):
        await client.get_stok_cfg()
        assert client.stok == "s1"
        assert client.sign == "si1"

    # 2. Token extraction from "data" sub-key
    client.stok = None
    client.sign = None
    data = {"data": {"stok": "s2", "sign": "si2"}}
    client._extract_tokens(data, json.dumps(data))
    assert client.stok == "s2"
    assert client.sign == "si2"

    # 3. Token extraction from raw text regex
    client.stok = None
    client.sign = None
    client._extract_tokens({}, '{"stok":"s3","sign":"si3extra"}')
    assert client.stok == "s3"
    assert client.sign == "si3extra"

    # 4. HTML fallback in get_modules raises TendaAuthError
    mock_resp.text = AsyncMock(return_value="<!DOCTYPE html>")
    mock_resp.status = 200
    mock_resp.headers = CIMultiDict({"Content-Type": "text/html"})
    with (
        patch.object(client, "_get", AsyncMock(return_value=mock_resp)),
        pytest.raises(TendaAuthError),
    ):
        await client.get_modules(["mod1"])

    # 5. Empty body in get_modules returns {}
    client.stok = "s3"  # restore stok cleared above
    client.sign = "si3extra"  # restore sign cleared above
    mock_resp.text = AsyncMock(return_value="")
    mock_resp.headers = CIMultiDict()
    with patch.object(client, "_get", AsyncMock(return_value=mock_resp)):
        result = await client.get_modules(["mod1"])
        # empty body: _json_or_text returns fallback dict
        assert "status_code" in result

    # 6. _url helper
    assert client._url("/test") == "http://1.1.1.1/test"

    # 7. _get_session creates a new session when none is set
    sess = await client._get_session()
    assert isinstance(sess, aiohttp.ClientSession)

    await client.close()

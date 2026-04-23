"""Async HTTP client for Tenda Mesh local API.

Uses aiohttp (bundled with Home Assistant) for non-blocking I/O.
AES decryption is offloaded to an executor to keep the event loop free.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
from typing import Any

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from .const import AES_IV, HTTP_TIMEOUT

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (synchronous, CPU-only – safe to run in executor)
# ---------------------------------------------------------------------------


def _tenda_password_hash(password: str) -> str:
    """Return MD5-upper of the password (Tenda's login hash scheme)."""
    return hashlib.md5(password.encode("utf-8")).hexdigest().upper()


def _tenda_decrypt(cipher_b64: str, sign: str) -> Any:
    """Decrypt a Tenda AES-CBC payload. Run this in an executor."""
    key = sign.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, AES_IV)
    raw = base64.b64decode(cipher_b64)
    plain = unpad(cipher.decrypt(raw), AES.block_size)
    return json.loads(plain.decode("utf-8"))


def _tenda_encrypt(data: dict[str, Any], sign: str) -> str:
    """Encrypt a Tenda AES-CBC payload. Run this in an executor."""
    from Crypto.Util.Padding import pad

    key = sign.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, AES_IV)
    plain = json.dumps(data).encode("utf-8")
    cipher_text = cipher.encrypt(pad(plain, AES.block_size))
    return base64.b64encode(cipher_text).decode("utf-8")


def _rand() -> str:
    return str(random.random())


def _non_empty(value: Any) -> str | None:
    return value if isinstance(value, str) and value != "" else None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TendaAuthError(Exception):
    """Raised when authentication fails (wrong password, stok/sign missing)."""


class TendaConnectionError(Exception):
    """Raised for network/connection issues."""


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


class TendaLocalClient:
    """Async client for the Tenda Mesh local HTTP API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        scheme: str = "http",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the TendaLocalClient."""
        self.host = host
        self.username = username
        self.password = password
        self.scheme = scheme
        self._base_url = f"{scheme}://{host}"
        self._owned_session = session is None
        self._session: aiohttp.ClientSession | None = session
        self.stok: str | None = None
        self.sign: str | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "Mozilla/5.0 (compatible; TendaMeshHA/1.0)",
                },
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying aiohttp session (only if we created it)."""
        if self._owned_session and self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        if path.startswith("/"):
            return f"{self._base_url}{path}"
        return f"{self._base_url}/{path}"

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (compatible; TendaMeshHA/1.0)",
        }

    def _extract_manual_cookies(self, resp: aiohttp.ClientResponse) -> None:
        if not hasattr(self, "_manual_cookies"):
            self._manual_cookies = {}
        for cookie_str in resp.headers.getall("Set-Cookie", []):
            parts = cookie_str.split(";")
            if parts:
                key_val = parts[0].strip()
                if "=" in key_val:
                    key, val = key_val.split("=", 1)
                    self._manual_cookies[key] = val

    def _get_manual_cookie_header(self) -> str | None:
        if not hasattr(self, "_manual_cookies") or not self._manual_cookies:
            return None
        return "; ".join([f"{k}={v}" for k, v in self._manual_cookies.items()])

    async def _get(self, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        session = await self._get_session()
        headers = {**self._default_headers(), **kwargs.pop("headers", {})}

        cookie_header = self._get_manual_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header

        try:
            resp = await session.get(self._url(path), headers=headers, **kwargs)
            self._extract_manual_cookies(resp)
            resp.raise_for_status()
        except aiohttp.ClientError as exc:
            raise TendaConnectionError(str(exc)) from exc
        else:
            return resp

    async def _post(self, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        session = await self._get_session()
        headers = {**self._default_headers(), **kwargs.pop("headers", {})}

        cookie_header = self._get_manual_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header

        try:
            resp = await session.post(
                self._url(path), allow_redirects=False, headers=headers, **kwargs
            )
            self._extract_manual_cookies(resp)
            resp.raise_for_status()
        except aiohttp.ClientError as exc:
            raise TendaConnectionError(str(exc)) from exc
        else:
            return resp

    async def _json_or_text(self, resp: aiohttp.ClientResponse) -> Any:
        text = await resp.text()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"status_code": resp.status, "text": text}

    # ------------------------------------------------------------------
    # Token extraction (mirrors original _update_tokens_from_payload)
    # ------------------------------------------------------------------

    def _extract_tokens(self, data: Any, raw_text: str) -> None:
        stok: str | None = None
        sign: str | None = None

        if isinstance(data, dict):
            stok = (
                _non_empty(data.get("stok"))
                or _non_empty(
                    (data.get("data") or {}).get("stok")
                    if isinstance(data.get("data"), dict)
                    else None
                )
                or _non_empty(
                    (data.get("stokCfg") or {}).get("stok")
                    if isinstance(data.get("stokCfg"), dict)
                    else None
                )
            )
            sign = (
                _non_empty(data.get("sign"))
                or _non_empty(
                    (data.get("data") or {}).get("sign")
                    if isinstance(data.get("data"), dict)
                    else None
                )
                or _non_empty(
                    (data.get("stokCfg") or {}).get("sign")
                    if isinstance(data.get("stokCfg"), dict)
                    else None
                )
            )

        if not stok:
            m = re.search(r'"stok"\s*:\s*"([a-zA-Z0-9]+)"', raw_text)
            if m:
                stok = m.group(1)
        if not stok:
            m = re.search(r";stok=([a-zA-Z0-9]+)", raw_text)
            if m:
                stok = m.group(1)
        if not sign:
            m = re.search(r'"sign"\s*:\s*"([^"]+)"', raw_text)
            if m:
                sign = m.group(1)

        if stok:
            self.stok = stok
        if sign:
            self.sign = sign

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    async def get_login_info(self) -> Any:
        """GET /goform/loginInfo (pre-login step)."""
        resp = await self._get("/goform/loginInfo", params={"rand": _rand()})
        return await self._json_or_text(resp)

    async def login(self) -> Any:
        """POST /login/Auth with hashed password."""
        payload = {
            "userName": self.username,
            "password": _tenda_password_hash(self.password),
        }
        headers = {
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/login.html?{_rand()}",
        }
        self.stok = None
        self.sign = None

        resp = await self._post("/login/Auth", json=payload, headers=headers)
        content_type = resp.headers.get("Content-Type", "").lower()
        set_cookies = resp.headers.getall("Set-Cookie", [])
        _LOGGER.debug("Set-Cookie headers from login: %s", set_cookies)
        text = await resp.text()
        text = text.lstrip()

        if "text/html" in content_type or text.startswith(("<!DOCTYPE html", "<html")):
            _LOGGER.debug("Login returned HTML – will rely on stokCfg for tokens")
            return {"status_code": resp.status, "html_fallback": True}

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"status_code": resp.status, "text": text}

        self._extract_tokens(data, text)
        return data

    async def get_stok_cfg(self) -> Any:
        """GET /goform/stokCfg – retrieves stok + sign after login."""
        resp = await self._get("/goform/stokCfg", params={"rand": _rand()})
        text = await resp.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"status_code": resp.status, "text": text}
        self._extract_tokens(data, text)
        return data

    async def ensure_authenticated(self) -> None:
        """Full login sequence: loginInfo → login → stokCfg."""
        if self.stok and self.sign:
            return

        await self.get_login_info()
        await self.login()
        if not self.stok or not self.sign:
            await self.get_stok_cfg()
        if not self.stok or not self.sign:
            raise TendaAuthError(
                "Authentication failed: stok/sign not available after login"
            )

    async def get_modules(self, modules: list[str], sn: str | None = None) -> Any:
        """GET /;stok=.../goform/getModules and decrypt the response."""
        if not self.stok:
            raise TendaAuthError("No stok – call ensure_authenticated() first.")
        if not self.sign:
            raise TendaAuthError("No sign – call ensure_authenticated() first.")

        params: dict[str, Any] = {
            "rand": _rand(),
            "modules": ",".join(modules),
        }
        if sn:
            params["sn"] = sn

        path = f"/;stok={self.stok}/goform/getModules"
        resp = await self._get(path, params=params)
        body = await self._json_or_text(resp)

        if (
            isinstance(body, dict)
            and "status_code" in body
            and isinstance(body.get("text"), str)
        ):
            if "<!DOCTYPE html>" in body.get("text", ""):
                self.stok = None
                self.sign = None
                raise TendaAuthError("Session expired, router returned login page")

        if isinstance(body, dict) and isinstance(body.get("data"), str):
            sign = self.sign
            return await asyncio.get_running_loop().run_in_executor(
                None, _tenda_decrypt, body["data"], sign
            )
        return body

    async def set_modules(self, modules: list[str], payload: dict[str, Any]) -> Any:
        """POST /;stok=.../goform/setModules."""
        if not self.stok:
            raise TendaAuthError("No stok – call ensure_authenticated() first.")

        # If we have a sign, we MUST encrypt the payload
        final_payload = payload
        if self.sign:
            sign = self.sign
            encrypted_data = await asyncio.get_running_loop().run_in_executor(
                None, _tenda_encrypt, payload, sign
            )
            final_payload = {"data": encrypted_data}

        path = f"/;stok={self.stok}/goform/setModules"
        resp = await self._post(
            path, params={"modules": ",".join(modules)}, json=final_payload
        )
        body = await self._json_or_text(resp)

        # If the response is also encrypted, decrypt it
        if isinstance(body, dict) and isinstance(body.get("data"), str) and self.sign:
            sign = self.sign
            return await asyncio.get_running_loop().run_in_executor(
                None, _tenda_decrypt, body["data"], sign
            )
        return body

    # ------------------------------------------------------------------
    # Connectivity test (used by config_flow)
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Return True if we can authenticate successfully."""
        try:
            await self.ensure_authenticated()
        except (TendaAuthError, TendaConnectionError):
            raise
        except Exception as exc:
            raise TendaConnectionError(str(exc)) from exc
        else:
            return True

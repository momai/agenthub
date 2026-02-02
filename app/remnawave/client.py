from __future__ import annotations

from typing import Any

import logging

import httpx


class RemnawaveClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        mode: str = "remote",
        caddy_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/.")
        self.api_key = api_key
        self.mode = mode
        self.caddy_token = caddy_token

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.caddy_token:
            headers["Authorization"] = f"Basic {self.caddy_token}"
            headers["X-Api-Key"] = self.api_key
        if self.mode == "local":
            headers["x-forwarded-for"] = "127.0.0.1"
            headers["x-forwarded-proto"] = "https"
        return headers

    async def ping(self) -> None:
        await self._raw_get("/api/users", params={"size": 1, "start": 0})

    async def get_users(self):
        return await self._raw_get("/api/users", params={"size": 1, "start": 0})

    async def get_user_by_telegram_id(self, telegram_id: int):
        try:
            return await self._raw_get(f"/api/users/by-telegram-id/{telegram_id}")
        except RuntimeError as exc:
            if " 404 " in str(exc):
                return {"response": []}
            raise

    async def get_user_by_username(self, username: str):
        try:
            return await self._raw_get(f"/api/users/by-username/{username}")
        except RuntimeError as exc:
            if " 404 " in str(exc):
                logging.info("Remnawave get_user_by_username: not found username=%s", username)
                return {"response": []}
            raise

    async def _raw_get(self, path: str, params: dict[str, Any] | None = None):
        async with httpx.AsyncClient(headers=self._headers()) as client:
            resp = await client.get(f"{self.base_url}{path}", params=params)
            logging.info("Remnawave GET %s -> %s", path, resp.status_code)
            return await self._handle_response(resp, "GET", path)

    async def create_user(self, payload: dict[str, Any]):
        return await self._raw_post("/api/users", payload)

    async def update_user(self, payload: dict[str, Any]):
        return await self._raw_patch("/api/users", payload)

    async def _raw_post(self, path: str, payload: dict[str, Any]):
        async with httpx.AsyncClient(headers=self._headers()) as client:
            resp = await client.post(f"{self.base_url}{path}", json=payload)
            logging.info("Remnawave POST %s -> %s", path, resp.status_code)
            return await self._handle_response(resp, "POST", path)

    async def _raw_patch(self, path: str, payload: dict[str, Any]):
        async with httpx.AsyncClient(headers=self._headers()) as client:
            resp = await client.patch(f"{self.base_url}{path}", json=payload)
            logging.info("Remnawave PATCH %s -> %s", path, resp.status_code)
            return await self._handle_response(resp, "PATCH", path)

    async def _handle_response(self, resp: httpx.Response, method: str, path: str):
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except ValueError:
                payload = resp.text
            raise RuntimeError(f"Remnawave {method} {path} failed: {resp.status_code} {payload}")
        try:
            return resp.json()
        except ValueError:
            return {}

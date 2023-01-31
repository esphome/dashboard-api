"""API to interact with the ESPHome dashboard."""
from __future__ import annotations

import logging
from typing import Any, Callable, TypedDict

import aiohttp


class ConfiguredDevice(TypedDict):
    """Configured ESPHome device."""

    address: str
    comment: str | None
    configuration: str
    current_version: str
    deployed_version: str
    loaded_integrations: list[str]
    name: str
    path: str
    target_platform: str
    web_port: str | None


class AdoptableDevice(TypedDict):
    """Adoptable ESPHome device."""

    name: str
    network: str
    package_import_url: str
    project_name: str
    project_version: str


class Devices(TypedDict):
    """ESPHome devices."""

    configured: list[ConfiguredDevice]
    importable: list[AdoptableDevice]


class ESPHomeDashboardAPI:
    """Class to interact with the ESPHome dashboard API."""

    def __init__(self, url: str, session: aiohttp.ClientSession) -> None:
        """Initialize."""
        self.url = url
        self.session = session

    async def request(self, method, path, **kwargs) -> dict:
        """Make a request to the dashboard."""
        resp = await self.session.request(method, f"{self.url}/{path}", **kwargs)
        resp.raise_for_status()
        return await resp.json()

    async def stream_logs(
        self,
        path: str,
        params: dict[str, Any],
        line_received_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Stream the logs from an ESPHome dashboard command."""
        async with self.session.ws_connect(
            f"{self.url}/{path}",
        ) as client:
            await client.send_json({"type": "spawn", **params})

            async for msg in client:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    return False

                data = msg.json()

                event = data.get("event")

                if event == "exit":
                    return data["code"] == 0

                if event != "line":
                    logging.getLogger(__name__).error(
                        "Unexpected event during %s: %s", path, event
                    )
                    return False

                if line_received_cb:
                    line_received_cb(data["data"])

        return False

    async def get_config(self, configuration: str) -> dict | None:
        """Get a configuration."""
        try:
            return await self.request(
                "GET", "json-config", params={"configuration": configuration}
            )
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                return None
            raise

    async def get_encryption_key(self, configuration: str) -> str | None:
        """Get the encryption key for a configuration."""
        config = await self.get_config(configuration)

        if not config:
            return None

        api = config.get("api")
        # An empty `api:` section in yaml produces a null object in json
        if api is None:
            return None

        encryption = api.get("encryption")

        if encryption is None:
            return None

        return encryption.get("key")

    async def get_devices(self) -> Devices:
        """Get all devices."""
        return await self.request("GET", "devices")

    async def compile(
        self,
        configuration: str,
        line_received_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Compile a configuration."""
        return await self.stream_logs(
            "compile",
            {"configuration": configuration},
            line_received_cb,
        )

    async def upload(
        self,
        configuration: str,
        port: str,
        line_received_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Upload a configuration."""
        return await self.stream_logs(
            "upload",
            {"configuration": configuration, "port": port},
            line_received_cb,
        )

"""Base plugin implementation providing core Maubot functionality.

This module provides the foundation for the NSFW detection plugin by handling:
- Plugin configuration and initialisation
- Room alias resolution and caching
- Matrix client setup and management
- Semaphore-based concurrency control

The BasePlugin class implements common Maubot plugin functionality, allowing
the main NSFWModelPlugin to focus on NSFW detection and content management.

Technical Details:
    - Implements Maubot's Plugin interface
    - Provides lazy-loaded semaphore for concurrent operations
    - Caches room alias resolutions for performance
    - Handles configuration validation and updates
"""

from __future__ import annotations

from asyncio import Lock, Semaphore
from functools import lru_cache
from typing import TYPE_CHECKING, ClassVar

from maubot.plugin_base import Plugin
from mautrix.types import RoomAlias

from nsfwbot.config import Config

if TYPE_CHECKING:
    from mautrix.util.config import BaseProxyConfig


class BasePlugin(Plugin):
    """Base plugin providing core Maubot functionality."""

    _semaphore: ClassVar[Semaphore | None] = None
    _lock: ClassVar[Lock] = Lock()
    via_servers: ClassVar[list] = []
    actions: ClassVar[dict] = {}
    report_to_room: ClassVar[str] = ""

    @property
    def semaphore(self) -> Semaphore:
        """Lazy initialisation of semaphore.

        Returns:
            Semaphore: The semaphore instance.
        """
        if self._semaphore is None:
            max_concurrent_jobs = self.config["max_concurrent_jobs"]
            self._semaphore = Semaphore(max_concurrent_jobs)
        return self._semaphore

    @classmethod
    def get_config_class(cls) -> type[BaseProxyConfig]:
        """Get the configuration class for the plugin.

        Returns:
            Configuration class.
        """
        return Config

    @lru_cache(maxsize=100)
    async def resolve_room_alias(self, room_alias: str) -> str:
        """Resolve room alias to room ID with caching.

        Args:
            room_alias: The room alias to resolve.

        Returns:
            str: The resolved room ID.
        """
        if not room_alias.startswith("#"):
            return room_alias
        info = await self.client.resolve_room_alias(RoomAlias(room_alias))
        return str(info.room_id)

    async def start(self) -> None:
        """Initialise plugin by loading config."""
        await super().start()
        try:
            if not isinstance(self.config, Config):
                self.log.error("Plugin not yet configured.")
                return

            self.config.load_and_update()
            self.via_servers = self.config["via_servers"]
            self.actions = self.config["actions"]

            report_room = str(self.actions.get("report_to_room", ""))
            if report_room:
                self.report_to_room = await self.resolve_room_alias(report_room)

            self.log.info("Loaded base plugin successfully")
        except Exception:
            self.log.exception("Error during start")

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

from asyncio import Semaphore
from functools import lru_cache
from threading import Lock
from typing import TYPE_CHECKING, ClassVar

from maubot import Plugin
from mautrix.types import RoomAlias

from nsfwbot.config import Config

if TYPE_CHECKING:
    from mautrix.util.config import BaseProxyConfig


class BasePlugin(Plugin):
    """Base plugin providing core Maubot functionality."""

    _lock: ClassVar[Lock] = Lock()
    _semaphore: ClassVar[Semaphore | None] = None
    _current_max_jobs: ClassVar[int] = 0

    @property
    def semaphore(self) -> Semaphore:
        """Get or create a semaphore for concurrent job limiting.

        Returns:
            A semaphore with the configured number of concurrent jobs.
        """
        with self._lock:
            # Check if we need to create or update the semaphore
            max_jobs = int(self.config.get("max_concurrent_jobs", 1))
            if self._semaphore is None or self._current_max_jobs != max_jobs:
                self.log.info("Creating semaphore with %d concurrent jobs", max_jobs)
                self._semaphore = Semaphore(max_jobs)
                self._current_max_jobs = max_jobs
            return self._semaphore

    @classmethod
    def get_config_class(cls) -> type[BaseProxyConfig]:
        """Get the configuration class for this plugin.

        Returns:
            The Config class for this plugin.
        """
        return Config

    @lru_cache(maxsize=100)
    async def resolve_room_alias(self, room_alias: str) -> str:
        """Resolve a room alias to a room ID.

        Args:
            room_alias: The room alias to resolve.

        Returns:
            The resolved room ID or the original alias if resolution fails.
        """
        if not room_alias or not room_alias.startswith(("#", "!")):
            return room_alias

        try:
            if room_alias.startswith("!"):
                return room_alias
            resolved = await self.client.resolve_room_alias(RoomAlias(room_alias))
        except Exception:
            self.log.exception("Failed to resolve room alias %s", room_alias)
            return room_alias
        else:
            return resolved.room_id

    async def start(self) -> None:
        """Initialise plugin by loading config."""
        await super().start()
        try:
            if not isinstance(self.config, Config):
                self.log.error("Plugin not yet configured.")
                return

            # Load and update config from Maubot
            self.config.load_and_update()

            # Update report room if needed
            report_to_room = str(self.config.get("report_to_room", ""))
            if report_to_room:
                resolved_room = await self.resolve_room_alias(report_to_room)
                if resolved_room != report_to_room:
                    self.log.info("Resolved report room %s to %s", report_to_room, resolved_room)
                    # Update the config with the resolved room ID
                    self.config["report_to_room"] = resolved_room
                    self.config.save()

            # Log current configuration
            actions = self.config.get("actions", {}) or {}
            self.log.info(
                "Config loaded: threshold=%.2f, report_to_room=%s, ignore_sfw=%s, redact_nsfw=%s, "
                "direct_reply=%s, post_errors=%s",
                float(self.config.get("nsfw_threshold", 0.5)),
                self.config.get("report_to_room", None) or "(empty)",
                actions.get("ignore_sfw"),
                actions.get("redact_nsfw"),
                actions.get("direct_reply"),
                actions.get("post_errors"),
            )
        except Exception:
            self.log.exception("Error during start")

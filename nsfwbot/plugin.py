"""Main plugin implementation for NSFWModelPlugin."""

from __future__ import annotations

from asyncio import Lock, Semaphore
from functools import lru_cache
from typing import TYPE_CHECKING, ClassVar

from maubot.handlers import command
from maubot.plugin_base import Plugin
from mautrix.errors import MBadJSON, MForbidden
from mautrix.types import (
    ContentURI,
    MediaMessageEventContent,
    MessageType,
    RoomAlias,
    RoomID,
    TextMessageEventContent,
)
from nsfw_detector import Model

from nsfwbot.config import Config
from nsfwbot.models import ScanResult
from nsfwbot.utils import create_matrix_to_url, extract_img_tags

if TYPE_CHECKING:
    from maubot.matrix import MaubotMessageEvent as MessageEvent
    from mautrix.util.config import BaseProxyConfig


class NSFWModelPlugin(Plugin):
    """Plugin to detect NSFW content in images and text messages."""

    model: ClassVar[Model] = Model()
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

            self.log.info("Loaded nsfwbot successfully")
        except Exception:
            self.log.exception("Error during start")

    async def process_scan(self, scan: ScanResult) -> None:
        """Process a complete scan operation.

        Args:
            scan: The scan result to process.
        """
        async with self.semaphore:
            try:
                # Set the matrix.to URL for the scan
                scan.matrix_to_url = create_matrix_to_url(
                    scan.event.room_id, scan.event.event_id, self.via_servers
                )

                # Download and process images
                await scan.download_images(self.client)
                scan.process_images()

                # Handle responses and actions
                await self.handle_scan_results(scan)
            except Exception:
                self.log.exception("Error processing scan")
            finally:
                scan.cleanup()

    async def handle_scan_results(self, scan: ScanResult) -> None:
        """Handle the results of a completed scan.

        Args:
            scan: The completed scan result.
        """
        try:
            # Check if we should ignore SFW results
            if self.actions.get("ignore_sfw", False) and not scan.has_nsfw:
                self.log.info("Ignored SFW images in %s", scan.event.room_id)
                return

            response = scan.format_response()

            # Direct reply in the same room
            if self.actions.get("direct_reply", False):
                await scan.event.reply(response)
                self.log.info("Replied to %s", scan.event.room_id)

            # Report to a specific room
            if self.report_to_room:
                try:
                    await self.client.send_text(room_id=RoomID(self.report_to_room), text=response)
                    self.log.info("Sent report to %s", self.report_to_room)
                except MBadJSON:
                    self.log.warning("Failed to send message to %s", self.report_to_room)

            # Redact NSFW messages if enabled
            if self.actions.get("redact_nsfw", False) and scan.has_nsfw:
                try:
                    await self.client.redact(
                        room_id=scan.event.room_id, event_id=scan.event.event_id, reason="NSFW"
                    )
                    self.log.info("Redacted NSFW message in %s", scan.event.room_id)
                except MForbidden:
                    self.log.warning("Failed to redact NSFW message in %s", scan.event.room_id)
        except Exception:
            self.log.exception("Error handling scan results")

    @command.passive(
        "^mxc://.+/.+$", field=lambda evt: evt.content.url or "", msgtypes=(MessageType.IMAGE)
    )
    async def handle_image_message(self, evt: MessageEvent, url: tuple[str]) -> None:
        """Handle direct image messages.

        Args:
            evt: The message event containing the image.
            url: The URL of the image.
        """
        if not isinstance(evt.content, MediaMessageEventContent) or not evt.content.url:
            return

        scan = ScanResult(evt, [evt.content.url], self.log, self.model)
        await self.process_scan(scan)

    @command.passive(
        '^<img src="mxc://.+/.+"',
        field=lambda evt: evt.content.formatted_body or "",
        msgtypes=(MessageType.TEXT),
    )
    async def handle_text_message(self, evt: MessageEvent) -> None:
        """Handle text messages with possible <img> tags.

        Args:
            evt: The message event containing the text.
        """
        if not isinstance(evt.content, TextMessageEventContent) or not evt.content.formatted_body:
            return

        img_urls = [ContentURI(url) for url in extract_img_tags(evt.content.formatted_body)]
        if not img_urls:
            return

        scan = ScanResult(evt, img_urls, self.log, self.model)
        await self.process_scan(scan)

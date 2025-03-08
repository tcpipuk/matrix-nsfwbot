"""NSFW Model Plugin for Maubot.

This plugin detects NSFW content in images and text messages containing image tags,
and takes appropriate actions based on the configuration.
"""

from __future__ import annotations

from asyncio import Lock, Semaphore, gather
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, ClassVar

from bs4 import BeautifulSoup
from maubot.handlers import command
from maubot.plugin_base import Plugin
from mautrix.errors import MBadJSON, MForbidden
from mautrix.types import (
    ContentURI,
    EventID,
    MediaMessageEventContent,
    MessageType,
    RoomAlias,
    RoomID,
    TextMessageEventContent,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from nsfw_detector import Model

if TYPE_CHECKING:
    from logging import Logger

    from maubot.matrix import MaubotMatrixClient as Client, MaubotMessageEvent as MessageEvent


@dataclass
class ImageResult:
    """Represents the result of processing a single image."""

    mxc_url: ContentURI
    temp_path: str | None = None
    prediction: dict | None = None
    error: Exception | None = None

    @property
    def success(self) -> bool:
        """Check if the image was processed successfully."""
        return self.temp_path is not None and self.prediction is not None

    @property
    def is_nsfw(self) -> bool:
        """Check if the image is classified as NSFW."""
        return bool(self.success and self.prediction and self.prediction["Label"] == "NSFW")

    def format_result(self, matrix_to_url: str) -> str:
        """Format the result for display.

        Args:
            matrix_to_url: The matrix.to URL for the message.

        Returns:
            Formatted string describing the result.
        """
        if not self.success:
            return f"{self.mxc_url} in {matrix_to_url} could not be processed: {self.error}"
        return (
            f"{self.mxc_url} in {matrix_to_url} appears {self.prediction['Label']} "
            f"with score {self.prediction['Score']:.2%}"
        )


@dataclass
class ScanResult:
    """Manages a batch of images to be scanned."""

    event: MessageEvent
    mxc_urls: list[ContentURI]
    logger: Logger
    model: Model
    images: list[ImageResult] = field(init=False)
    matrix_to_url: str = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the scan result with empty image results."""
        self.images = [ImageResult(url) for url in self.mxc_urls]
        self.matrix_to_url = ""

    @property
    def has_nsfw(self) -> bool:
        """Check if any successfully processed images are NSFW."""
        return any(img.is_nsfw for img in self.images)

    @property
    def all_succeeded(self) -> bool:
        """Check if all images were processed successfully."""
        return all(img.success for img in self.images)

    async def download_images(self, client: Client) -> None:
        """Download all images concurrently.

        Args:
            client: The Matrix client to use for downloads.
        """

        async def download_single(image: ImageResult) -> None:
            try:
                with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                    img_bytes = await client.download_media(image.mxc_url)
                    Path(temp_file.name).write_bytes(img_bytes)
                    image.temp_path = temp_file.name
            except Exception as e:
                image.error = e
                self.logger.warning("Failed to download %s: %s", image.mxc_url, e)

        await gather(*[download_single(image) for image in self.images])

    def process_images(self) -> None:
        """Process all successfully downloaded images with the NSFW model."""
        try:
            # Get paths of successfully downloaded images
            valid_images = [(img.mxc_url, img.temp_path) for img in self.images if img.temp_path]
            if not valid_images:
                return

            # Run predictions
            predictions = self.model.predict([path for _, path in valid_images])

            # Update image results with predictions
            for img in self.images:
                if img.temp_path and img.temp_path in predictions:
                    img.prediction = predictions[img.temp_path]
        except Exception as e:
            self.logger.exception("Error processing images with model")
            for img in self.images:
                if not img.error:  # Don't overwrite download errors
                    img.error = e

    def cleanup(self) -> None:
        """Remove all temporary files."""
        for img in self.images:
            if img.temp_path:
                Path(img.temp_path).unlink(missing_ok=True)

    def format_response(self) -> str:
        """Format the complete scan results for display.

        Returns:
            Formatted string containing all results.
        """
        parts = [img.format_result(self.matrix_to_url) for img in self.images]
        return "- " + "\n- ".join(parts) if len(parts) > 1 else parts[0]


class Config(BaseProxyConfig):
    """Configuration manager for the NSFWModelPlugin."""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """Update the configuration with new values.

        Args:
            helper: Helper object to copy configuration values.
        """
        helper.copy("max_concurrent_jobs")
        helper.copy("via_servers")
        helper.copy("actions")


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
                scan.matrix_to_url = self.create_matrix_to_url(
                    scan.event.room_id, scan.event.event_id
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

        img_urls = [ContentURI(url) for url in self.extract_img_tags(evt.content.formatted_body)]
        if not img_urls:
            return

        scan = ScanResult(evt, img_urls, self.log, self.model)
        await self.process_scan(scan)

    def create_matrix_to_url(self, room_id: RoomID, event_id: EventID) -> str:
        """Create a matrix.to URL for a given room ID and event ID.

        Args:
            room_id: The room ID.
            event_id: The event ID.

        Returns:
            The matrix.to URL.
        """
        via_params = (
            "?" + "&".join(f"via={server}" for server in self.via_servers)
            if self.via_servers
            else ""
        )
        return f"https://matrix.to/#/{room_id}/{event_id}{via_params}"

    def extract_img_tags(self, html: str) -> list[str]:
        """Extract image URLs from <img> tags in the HTML content.

        Args:
            html: The HTML content.

        Returns:
            List of image URLs.
        """
        soup = BeautifulSoup(html, "html.parser", parser="lxml")
        return [img["src"] for img in soup.find_all("img") if "src" in img.attrs]

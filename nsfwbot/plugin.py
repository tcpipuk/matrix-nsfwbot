"""Core Matrix plugin for NSFW content detection and management.

This module implements the main Maubot plugin that monitors Matrix chat rooms for
images and analyses them for NSFW content. It provides:

Core Features:
    - Automatic monitoring of image uploads
    - Detection of embedded images in text messages
    - Configurable concurrent processing
    - Multiple response options:
        * Direct replies with detection results
        * Centralised reporting to a moderation room
        * Automatic removal of inappropriate content

Technical Implementation:
    - Uses the nsfwdetection library for image analysis
    - Implements Maubot's plugin system for Matrix integration
    - Provides both active and passive command handlers
    - Manages resource usage through semaphores

Usage in Matrix:
    The plugin automatically processes:
    1. Direct image uploads
    2. Images embedded in formatted messages
    3. Multiple images in a single message

    Results are reported based on configuration:
    - Directly in the chat room
    - To a designated moderation room
    - With optional automatic message removal

Configuration is handled through the Maubot admin interface or config.yaml.
See the config.py module for available settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from maubot.handlers import command
from mautrix.errors import MBadJSON, MForbidden
from mautrix.types import ContentURI, MediaMessageEventContent, MessageType, RoomID
from nsfw_detector import Model

from nsfwbot.base import BasePlugin
from nsfwbot.models import BatchImageScan
from nsfwbot.utils import create_matrix_to_url, extract_img_tags

if TYPE_CHECKING:
    from maubot.matrix import MaubotMessageEvent as MessageEvent


class NSFWModelPlugin(BasePlugin):
    """Plugin to detect NSFW content in images and text messages."""

    model: ClassVar[Model] = Model()

    async def process_scan(self, scan: BatchImageScan) -> None:
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

    async def handle_scan_results(self, scan: BatchImageScan) -> None:
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

        scan = BatchImageScan(evt, [evt.content.url], self.log, self.model)
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
        if not evt.content.formatted_body:
            return

        img_urls = [ContentURI(url) for url in extract_img_tags(evt.content.formatted_body)]
        if not img_urls:
            return

        scan = BatchImageScan(evt, img_urls, self.log, self.model)
        await self.process_scan(scan)

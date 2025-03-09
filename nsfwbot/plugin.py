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
                via_servers = self.config.get("via_servers", ["matrix.org"])
                scan.matrix_to_url = create_matrix_to_url(
                    scan.evt.room_id, scan.evt.event_id, via_servers
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
            # Ensure actions is never None
            actions = self.config.get("actions", {}) or {}

            # Get the current ignore_sfw setting from config
            ignore_sfw = bool(actions.get("ignore_sfw", False))
            post_errors = bool(actions.get("post_errors", False))

            # Check if there are any errors
            has_errors = any(img.error is not None for img in scan.images)

            # Only ignore SFW results if ignore_sfw is True and no NSFW images were found
            if ignore_sfw and not scan.has_nsfw and not (has_errors and post_errors):
                self.log.info(
                    "Ignored images below NSFW threshold in %s (ignore_sfw=%s)",
                    scan.evt.room_id,
                    ignore_sfw,
                )
                return

            response = scan.format_response()
            self.log.debug("Scan results: %s", response)

            # Direct reply in the same room
            if actions.get("direct_reply", False):
                await scan.evt.reply(response)
                self.log.info("Replied to %s", scan.evt.room_id)

            # Report to a specific room
            report_to_room = self.config.get("report_to_room", None)
            if report_to_room:
                try:
                    await self.client.send_text(room_id=RoomID(report_to_room), text=response)
                    self.log.info("Sent report to %s", report_to_room)
                except MBadJSON:
                    self.log.warning("Failed to send message to %s", report_to_room)

            # Redact NSFW messages if enabled
            if actions.get("redact_nsfw", False) and scan.has_nsfw:
                try:
                    await self.client.redact(
                        room_id=scan.evt.room_id, event_id=scan.evt.event_id, reason="NSFW"
                    )
                    self.log.info("Redacted message with NSFW content in %s", scan.evt.room_id)
                except MForbidden:
                    self.log.warning("Failed to redact message in %s", scan.evt.room_id)
        except Exception:
            self.log.exception("Error handling scan results")

    @command.passive(
        "^mxc://.+/.+$", field=lambda evt: evt.content.url or "", msgtypes=[MessageType.IMAGE]
    )
    async def handle_image_message(self, evt: MessageEvent, url: tuple[str]) -> None:  # noqa: ARG002
        """Handle direct image messages.

        Args:
            evt: The message event containing the image.
            url: The URL of the image.
        """
        if not isinstance(evt.content, MediaMessageEventContent) or not evt.content.url:
            return

        scan = BatchImageScan(
            evt=evt,
            mxc_urls=[evt.content.url],
            logger=self.log,
            model=self.model,
            config=self.config,
        )
        await self.process_scan(scan)

    @command.passive(
        '^<img src="mxc://.+/.+"',
        field=lambda evt: evt.content.formatted_body or "",
        msgtypes=[MessageType.TEXT],
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

        scan = BatchImageScan(
            evt=evt, mxc_urls=img_urls, logger=self.log, model=self.model, config=self.config
        )
        await self.process_scan(scan)

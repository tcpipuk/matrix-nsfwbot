"""
NSFW Model Plugin for Maubot

This plugin detects NSFW content in images and text messages containing image tags,
and takes appropriate actions based on the configuration.
"""

import os
from typing import List, Tuple, Type
from uuid import uuid4
from asyncio import Semaphore
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
from mautrix.errors import MBadJSON, MForbidden
from maubot import Plugin, MessageEvent  # type:ignore
from maubot.handlers import command
from nsfw_detector import Model
from bs4 import BeautifulSoup


class Config(BaseProxyConfig):
    """
    Configuration manager for the NSFWModelPlugin.
    """

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """
        Update the configuration with new values.

        :param helper: Helper object to copy configuration values.
        """
        helper.copy("max_concurrent_jobs")
        helper.copy("via_servers")
        helper.copy("actions")


class NSFWModelPlugin(Plugin):
    """
    Plugin to detect NSFW content in images and text messages.
    """

    model = Model()
    semaphore = Semaphore(1)
    via_servers = []
    actions = {}
    report_to_room = ""

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        """
        Get the configuration class for the plugin.

        :return: Configuration class.
        """
        return Config

    async def start(self) -> None:
        """
        Initialise plugin by loading config and setting up semaphore.
        """
        await super().start()
        try:
            if not isinstance(self.config, Config):
                self.log.error("Plugin not yet configured.")
            else:
                self.config.load_and_update()
                self.via_servers = self.config["via_servers"]
                self.actions = self.config["actions"]
                max_concurrent_jobs = self.config["max_concurrent_jobs"]
                self.semaphore = Semaphore(max_concurrent_jobs)
                self.report_to_room = str(self.actions.get("report_to_room", ""))
                if self.report_to_room.startswith("#"):
                    report_to_info = await self.client.resolve_room_alias(
                        RoomAlias(self.report_to_room)
                    )
                    self.report_to_room = report_to_info.room_id
                elif self.report_to_room and not self.report_to_room.startswith("!"):
                    self.log.warning("Invalid room ID or alias provided for report_to_room")
                self.log.info("Loaded nsfwbot successfully")
        except Exception as e:
            self.log.error(f"Error during start: {e}")

    @command.passive(
        "^mxc://.+/.+$",
        field=lambda evt: evt.content.url or "",  # type:ignore
        msgtypes=(MessageType.IMAGE,),
    )
    async def handle_image_message(self, evt: MessageEvent, url: Tuple[str]) -> None:
        """
        Handle direct image messages.

        :param evt: The message event containing the image.
        :param url: The URL of the image.
        """
        try:
            if not isinstance(evt.content, MediaMessageEventContent) or not evt.content.url:
                return
            results = await self.process_images([evt.content.url])
            matrix_to_url = self.create_matrix_to_url(evt.room_id, evt.event_id)
            response = self.format_response(results, matrix_to_url)
            await self.send_responses(evt, response, results)
        except Exception as e:
            self.log.error(f"Error handling image message: {e}")

    @command.passive(
        '^<img src="mxc://.+/.+"',
        field=lambda evt: evt.content.formatted_body or "",  # type:ignore
        msgtypes=(MessageType.TEXT,),
    )
    async def handle_text_message(self, evt: MessageEvent) -> None:
        """
        Handle text messages with possible <img> tags.

        :param evt: The message event containing the text.
        """
        try:
            if isinstance(evt.content, TextMessageEventContent) and evt.content.formatted_body:
                img_urls = self.extract_img_tags(evt.content.formatted_body)
                if len(img_urls) == 0:
                    return
                all_results = await self.process_images([ContentURI(url) for url in img_urls])
                matrix_to_url = self.create_matrix_to_url(evt.room_id, evt.event_id)
                response = self.format_response(all_results, matrix_to_url)
                await self.send_responses(evt, response, all_results)
        except Exception as e:
            self.log.error(f"Error handling text message: {e}")

    async def process_images(self, mxc_urls: List[ContentURI]) -> dict:
        """
        Download and process the images using the NSFW model.

        :param mxc_urls: List of MXC URLs of the images.
        :return: Dictionary of results with MXC URLs as keys and predictions as values.
        """
        async with self.semaphore:
            temp_files = []
            try:
                for mxc_url in mxc_urls:
                    img_bytes = await self.client.download_media(mxc_url)  # type:ignore
                    temp_filename = f"/tmp/{uuid4()}.jpg"
                    with open(temp_filename, "wb") as img_file:
                        img_file.write(img_bytes)
                    temp_files.append((mxc_url, temp_filename))

                predictions = self.model.predict([temp_filename for _, temp_filename in temp_files])

                final_results = {
                    str(mxc_url): predictions.pop(temp_filename)
                    for mxc_url, temp_filename in temp_files
                }
                return final_results
            except Exception as e:
                self.log.error(f"Error processing images: {e}")
                return {}
            finally:
                for _, temp_filename in temp_files:
                    os.remove(temp_filename)

    def create_matrix_to_url(self, room_id: RoomID, event_id: EventID) -> str:
        """
        Create a matrix.to URL for a given room ID and event ID.

        :param room_id: The room ID.
        :param event_id: The event ID.
        :return: The matrix.to URL.
        """
        via_params = (
            str("?" + "&".join([f"via={server}" for server in self.via_servers]))
            if self.via_servers
            else ""
        )
        return f"https://matrix.to/#/{room_id}/{event_id}{via_params}"

    def extract_img_tags(self, html: str) -> List[str]:
        """
        Extract image URLs from <img> tags in the HTML content.

        :param html: The HTML content.
        :return: List of image URLs.
        """
        soup = BeautifulSoup(html, "html.parser")
        return [img["src"] for img in soup.find_all("img") if "src" in img.attrs]

    def format_response(self, results: dict, matrix_to_url: str) -> str:
        """
        Format the response message based on the results.

        :param results: Dictionary of results with MXC URLs as keys and predictions as values.
        :param matrix_to_url: The matrix.to URL for the original message.
        :return: The formatted response message.
        """
        response_parts = [
            f"{mxc_url} in {matrix_to_url} appears {res['Label']} with score {res['Score']:.2%}"
            for mxc_url, res in results.items()
        ]
        if len(response_parts) > 1:
            return "- " + "\n- ".join(response_parts)
        else:
            return "\n".join(response_parts)

    async def send_responses(self, evt: MessageEvent, response: str, results: dict) -> None:
        """
        Send responses or take actions based on config.

        :param evt: The message event.
        :param response: The formatted response message.
        :param results: Dictionary of results with MXC URLs as keys and predictions as values.
        """
        try:
            # Check if we should ignore SFW images
            ignore_sfw = self.actions.get("ignore_sfw", False)
            nsfw_results = [res for res in results.values() if res["Label"] == "NSFW"]
            # If all images were SFW and should be ignored
            if ignore_sfw and not nsfw_results:
                self.log.info(f"Ignored SFW images in {evt.room_id}")
                return

            # Direct reply in the same room
            if self.actions.get("direct_reply", False):
                await evt.reply(response)
                self.log.info(f"Replied to {evt.room_id}")

            # Report to a specific room
            if self.report_to_room:
                try:
                    await self.client.send_text(room_id=RoomID(self.report_to_room), text=response)
                    self.log.info(f"Sent report to {RoomID(self.report_to_room)}")
                except MBadJSON as e:
                    self.log.warning(
                        f"Failed to send message to {RoomID(self.report_to_room)}: {e}"
                    )

            # Redact the message if it's NSFW and redacting is enabled
            redact_nsfw = self.actions.get("redact_nsfw", False)
            if nsfw_results and redact_nsfw:
                try:
                    await self.client.redact(
                        room_id=evt.room_id, event_id=evt.event_id, reason="NSFW"
                    )
                    self.log.info(f"Redacted NSFW message in {evt.room_id}")
                except MForbidden:
                    self.log.warning(f"Failed to redact NSFW message in {evt.room_id}")
        except Exception as e:
            self.log.error(f"Error sending responses: {e}")

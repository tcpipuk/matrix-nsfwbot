import os
from typing import List, Tuple, Type
from uuid import uuid4
from asyncio import Semaphore
from mautrix.types import (
    ContentURI,
    EventID,
    MediaMessageEventContent,
    MessageType,
    RoomID,
    TextMessageEventContent,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from mautrix.errors import MForbidden
from maubot import Plugin, MessageEvent  # type:ignore
from maubot.handlers import command
from nsfw_detector import Model
from bs4 import BeautifulSoup


class Config(BaseProxyConfig):
    """
    Configuration manager
    """

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("max_concurrent_jobs")
        helper.copy("via_servers")
        helper.copy("actions")


class NSFWModelPlugin(Plugin):
    model = Model()
    semaphore = Semaphore(1)
    via_servers = []
    actions = {}

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        """Initialise plugin by loading config and setting up semaphore."""
        await super().start()
        # Check if config exists
        if not isinstance(self.config, Config):
            self.log.error("Plugin not yet configured.")
        else:
            # Load in config
            self.config.load_and_update()
            # Load via_servers from config, with a default fallback
            self.via_servers = self.config["via_servers"]
            # Load actions from config
            self.actions = self.config["actions"]
            # Initialise the Semaphore based on the max_concurrent_jobs setting
            max_concurrent_jobs = self.config["max_concurrent_jobs"]
            self.semaphore = Semaphore(max_concurrent_jobs)
            # Initialise the NSFW model
            self.log.info("Loaded nsfwbot successfully")

    @command.passive(
        "^mxc://.+/.+$",
        field=lambda evt: evt.content.url or "",  # type:ignore
        msgtypes=(MessageType.IMAGE,),
    )
    async def handle_image_message(self, evt: MessageEvent, url: Tuple[str]) -> None:
        """Handle direct image messages."""
        if not isinstance(evt.content, MediaMessageEventContent) or not evt.content.url:
            return
        # Process image
        results = await self.process_images([evt.content.url])
        # Create matrix.to URL for the original message
        matrix_to_url = self.create_matrix_to_url(evt.room_id, evt.event_id)
        # Prepare the response message
        response = self.format_response(results, matrix_to_url)
        # Send responses based on actions
        await self.send_responses(evt, response, results)

    @command.passive(
        '^<img src="mxc://.+/.+"',
        field=lambda evt: evt.content.formatted_body or "",  # type:ignore
        msgtypes=(MessageType.TEXT,),
    )
    async def handle_text_message(self, evt: MessageEvent) -> None:
        """Handle text messages with possible <img> tags."""
        if isinstance(evt.content, TextMessageEventContent) and evt.content.formatted_body:
            img_urls = self.extract_img_tags(evt.content.formatted_body)
            # Do nothing if no URLs found
            if len(img_urls) == 0:
                return
            # Process all images at once
            all_results = await self.process_images([ContentURI(url) for url in img_urls])
            # Create matrix.to URL for the original message
            matrix_to_url = self.create_matrix_to_url(evt.room_id, evt.event_id)
            # Prepare the response message
            response = self.format_response(all_results, matrix_to_url)
            # Send responses based on actions
            await self.send_responses(evt, response, all_results)

    async def process_images(self, mxc_urls: List[ContentURI]) -> dict:
        """Download and process the images using the NSFW model."""
        async with self.semaphore:
            temp_files = []
            try:
                # Download all images and save to temporary files
                for mxc_url in mxc_urls:
                    img_bytes = await self.client.download_media(mxc_url)  # type:ignore
                    temp_filename = f"/tmp/{uuid4()}.jpg"
                    with open(temp_filename, "wb") as img_file:
                        img_file.write(img_bytes)
                    temp_files.append((mxc_url, temp_filename))

                # Predict using the NSFW model
                predictions = self.model.predict([temp_filename for _, temp_filename in temp_files])

                # Replace temporary filenames in the results with the original MXC URLs
                final_results = {
                    str(mxc_url): predictions.pop(temp_filename)
                    for mxc_url, temp_filename in temp_files
                }
                return final_results
            finally:
                # Ensure all temporary files are removed
                for _, temp_filename in temp_files:
                    os.remove(temp_filename)

    def create_matrix_to_url(self, room_id: RoomID, event_id: EventID) -> str:
        """Create a matrix.to URL for a given room ID and event ID."""
        via_params = (
            str("?" + "&".join([f"via={server}" for server in self.via_servers]))
            if self.via_servers
            else ""
        )
        return f"https://matrix.to/#/{room_id}/{event_id}{via_params}"

    def extract_img_tags(self, html: str) -> List[str]:
        """Extract image URLs from <img> tags in the HTML content."""
        soup = BeautifulSoup(html, "html.parser")
        return [img["src"] for img in soup.find_all("img") if "src" in img.attrs]

    def format_response(self, results: dict, matrix_to_url: str) -> str:
        """Format the response message based on the results."""
        response_parts = [
            f"{mxc_url} in {matrix_to_url} appears {res['Label']} with score {res['Score']:.2%}"
            for mxc_url, res in results.items()
        ]
        if len(response_parts) > 1:
            return "- " + "\n- ".join(response_parts)
        else:
            return "\n".join(response_parts)

    async def send_responses(self, evt: MessageEvent, response: str, results: dict) -> None:
        """Send responses or take actions based on config."""
        # Check if we should ignore SFW images
        ignore_sfw = self.actions.get("ignore_sfw", False)
        nsfw_results = [res for res in results.values() if res["Label"] == "NSFW"]
        # If all images were SFW and should be ignored
        if ignore_sfw and not nsfw_results:
            self.log.info(f"Ignored SFW images in {evt.room_id}")
            return

        # Direct reply in the same room
        if self.actions.get("direct_reply", False):
            await evt.reply(TextMessageEventContent(msgtype=MessageType.NOTICE, body=response))
            self.log.info(f"Replied to {evt.room_id}")

        # Report to a specific room
        report_room_id = self.actions.get("report_to_room", "")
        if report_room_id:
            await self.client.send_text(room_id=RoomID(report_room_id), text=response)
            self.log.info(f"Sent report to {report_room_id}")

        # Redact the message if it's NSFW and redacting is enabled
        redact_nsfw = self.actions.get("redact_nsfw", False)
        if nsfw_results and redact_nsfw:
            try:
                await self.client.redact(room_id=evt.room_id, event_id=evt.event_id, reason="NSFW")
                self.log.info(f"Redacted NSFW message in {evt.room_id}")
            except MForbidden:
                self.log.warning(f"Failed to redact NSFW message in {evt.room_id}")

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


class NSFWModelPlugin(Plugin):
    model = Model()
    semaphore = Semaphore(1)
    via_servers = []

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        """Initializes the plugin by loading the configuration and setting up resources."""
        await super().start()
        # Check if config exists
        if not isinstance(self.config, Config):
            self.log.error("Plugin not yet configured.")
        else:
            # Load in config
            self.config.load_and_update()
            # Load via_servers from config, with a default fallback
            self.via_servers = self.config["via_servers"]  # type:ignore
            # Initialize the Semaphore based on the max_concurrent_jobs setting
            max_concurrent_jobs = self.config["max_concurrent_jobs"]  # type:ignore
            self.semaphore = Semaphore(max_concurrent_jobs)
            # Initialize the NSFW model
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
        # Prepare and send the response message
        response = self.format_response(results, matrix_to_url)
        await evt.respond(response)

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
            # Prepare and send the response message
            response = self.format_response(all_results, matrix_to_url)
            await evt.respond(response)

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

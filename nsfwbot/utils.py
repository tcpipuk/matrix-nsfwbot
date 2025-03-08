"""Utility functions for the NSFWModelPlugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from mautrix.types import EventID, RoomID


def create_matrix_to_url(room_id: RoomID, event_id: EventID, via_servers: list[str]) -> str:
    """Create a matrix.to URL for a given room ID and event ID.

    Args:
        room_id: The room ID.
        event_id: The event ID.
        via_servers: List of via servers to include in the URL.

    Returns:
        The matrix.to URL.
    """
    via_params = "?" + "&".join(f"via={server}" for server in via_servers) if via_servers else ""
    return f"https://matrix.to/#/{room_id}/{event_id}{via_params}"


def extract_img_tags(html: str) -> list[str]:
    """Extract image URLs from <img> tags in the HTML content.

    Args:
        html: The HTML content.

    Returns:
        List of image URLs.
    """
    soup = BeautifulSoup(html, "html.parser", parser="lxml")
    return [img["src"] for img in soup.find_all("img") if "src" in img.attrs]

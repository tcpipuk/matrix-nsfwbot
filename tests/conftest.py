"""Shared test fixtures and mock classes for the NSFWBot test suite.

This module contains reusable test components that can be used across
multiple test files, including mock implementations of Maubot classes
and pytest fixtures.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import pytest
from aiohttp import web
from maubot.client import Client
from maubot.loader import PluginLoader

from nsfwbot import NSFWModelPlugin
from nsfwbot.config import Config

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from mautrix.types import UserID


class MockConfig(Config):
    """Mock configuration for testing.

    This class provides a minimal implementation of the Config class
    that doesn't require a real base config file.
    """

    def load_base(self) -> dict[str, Any]:
        """Load the base configuration.

        Returns:
            dict[str, Any]: The base configuration dictionary.
        """
        return {
            "max_concurrent_jobs": 1,
            "via_servers": ["matrix.org"],
            "actions": {
                "ignore_sfw": True,
                "redact_nsfw": False,
                "direct_reply": False,
                "report_to_room": "",
            },
        }


class MockClient(Client):
    """Mock Matrix client for testing.

    This class provides a minimal implementation of a Matrix client
    for testing purposes, implementing only the essential methods
    needed for the plugin to function during tests.

    Attributes:
        logged_in: A boolean indicating whether the mock client is logged in.
    """

    def __init__(self) -> None:
        """Initialise the mock client with default state."""
        self.logged_in = False
        self.mxid: UserID = "@test:test.org"

    async def is_logged_in(self) -> bool:
        """Check if the mock client is logged in.

        Returns:
            bool: The logged in state of the mock client.
        """
        return self.logged_in


class MockLoader(PluginLoader):
    """Mock plugin loader for testing.

    This class provides a minimal implementation of a Maubot plugin loader
    for testing purposes, containing only the essential attributes needed
    for the plugin to function during tests.

    Attributes:
        id: The plugin identifier.
        path: The mock filesystem path.
        version: The plugin version string.
    """

    def __init__(self) -> None:
        """Initialise the mock loader with test values."""
        self.id = "uk.tcpip.nsfwbot"
        self.path = "."
        self.version = "0.3.0"

    async def delete(self) -> None:
        """Mock implementation of delete method.

        This method is required by the PluginLoader abstract class but
        is not used in our tests.
        """

    async def list_files(self) -> list[str]:
        """Mock implementation of list_files method.

        Returns:
            list[str]: An empty list as we don't need real files for testing.
        """
        return []

    async def load(self) -> None:
        """Mock implementation of load method.

        This method is required by the PluginLoader abstract class but
        is not used in our tests.
        """

    async def read_file(self, path: str) -> bytes:  # noqa: ARG002
        """Mock implementation of read_file method.

        Args:
            path: The path to read from (unused in mock).

        Returns:
            bytes: Empty bytes as we don't need real file content for testing.
        """
        return b""

    async def reload(self) -> None:
        """Mock implementation of reload method.

        This method is required by the PluginLoader abstract class but
        is not used in our tests.
        """

    def source(self) -> str:
        """Mock implementation of source method.

        Returns:
            str: A dummy source path.
        """
        return "mock_source"


@pytest.fixture
async def mock_plugin() -> AsyncGenerator[NSFWModelPlugin]:
    """Create a mock NSFWBot plugin instance for testing.

    This fixture provides a fully configured mock plugin instance with
    minimal valid configuration for testing purposes.

    Yields:
        NSFWModelPlugin: A configured mock plugin instance.
    """
    # Create all required dependencies
    client = MockClient()
    loader = MockLoader()

    # Create plugin instance with all required dependencies
    return NSFWModelPlugin(
        client=client,
        loop=asyncio.get_event_loop(),
        http=web.Application(),
        instance_id="test_instance",
        log=logging.getLogger("test_logger"),
        config=MockConfig(dict, lambda: None, loader),
        database=None,  # Plugin doesn't use a database
        webapp=web.Application(),
        webapp_url="http://test.local",
        loader=loader,
    )

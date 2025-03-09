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

    def __init__(self) -> None:
        """Initialize the mock configuration with default values."""
        # Create default config
        self._base_config = {
            "max_concurrent_jobs": 1,
            "nsfw_threshold": 0.5,
            "via_servers": ["matrix.org"],
            "actions": {
                "ignore_sfw": True,
                "redact_nsfw": False,
                "direct_reply": False,
                "report_to_room": "",
            },
        }

        # Define required functions for BaseProxyConfig
        def load() -> dict[str, Any]:
            return self._base_config.copy()

        def save(data: dict[str, Any]) -> None:
            self._base_config.update(data)

        # Initialise the parent class with required arguments
        super().__init__(load, self.load_base, save)

        # Initialize the base config
        self.base = self.load_base()

    def load_base(self) -> dict[str, Any]:
        """Load the base configuration.

        Returns:
            dict[str, Any]: The base configuration dictionary.
        """
        return self._base_config.copy()

    def load_and_update(self) -> None:
        """Load and update the configuration.

        This method is called by the plugin to reload the configuration.
        In the mock, it ensures the base config is loaded and updated.
        """
        # Update the base config from _base_config
        self.base = self.load_base()

    def __getitem__(self, key: str) -> object:
        """Get a configuration value.

        This method is called by the plugin to get configuration values.
        In the mock, it returns values directly from _base_config.

        Args:
            key: The configuration key to get.

        Returns:
            The configuration value.
        """
        return self._base_config[key]

    def get(self, key: str, default: object = None) -> object:
        """Get a configuration value with a default.

        This method is called by the plugin to get configuration values.
        In the mock, it returns values directly from _base_config.

        Args:
            key: The configuration key to get.
            default: The default value if the key doesn't exist.

        Returns:
            The configuration value or the default.
        """
        return self._base_config.get(key, default)


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
    """Create a mock plugin instance for testing.

    This fixture provides a fully initialized NSFWModelPlugin instance
    with mock dependencies for testing.

    Yields:
        NSFWModelPlugin: The mock plugin instance.
    """
    # Create mock loader
    loader = MockLoader()

    # Create mock client
    client = MockClient()

    # Create the plugin instance
    return NSFWModelPlugin(
        client=client,
        loop=asyncio.get_event_loop(),
        http=None,  # Plugin doesn't use HTTP
        instance_id="test_instance",
        log=logging.getLogger("test_logger"),
        config=MockConfig(),
        database=None,  # Plugin doesn't use a database
        webapp=web.Application(),
        webapp_url="http://test.local",  # Required parameter
        loader=loader,
    )

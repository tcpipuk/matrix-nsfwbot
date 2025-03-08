"""Tests for the NSFW detection plugin functionality.

This module tests the core functionality of the plugin, including:
- Plugin loading and initialisation
- Configuration management
- NSFW threshold handling
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from maubot import Plugin

from tests.conftest import MockConfig

if TYPE_CHECKING:
    from nsfwbot import NSFWModelPlugin


@pytest.mark.asyncio
async def test_plugin_loads(mock_plugin: NSFWModelPlugin) -> None:
    """Test that the plugin can be loaded with correct attributes.

    This test verifies that:
    1. The plugin is an instance of the base Maubot Plugin class
    2. The plugin has the required internal_start method
    3. The plugin is from the correct module

    Args:
        mock_plugin: The mock plugin instance to test.

    Raises:
        pytest.Failed: If any of the plugin attributes are incorrect.
    """
    if not isinstance(mock_plugin, Plugin):
        pytest.fail("Plugin is not an instance of maubot.Plugin")
    if not hasattr(mock_plugin, "internal_start"):
        pytest.fail("Plugin missing required internal_start method")
    if mock_plugin.__module__ != "nsfwbot.plugin":
        pytest.fail(f"Incorrect module: {mock_plugin.__module__}")


@pytest.mark.asyncio
async def test_plugin_starts(mock_plugin: NSFWModelPlugin) -> None:
    """Test that the plugin can start without raising exceptions.

    Args:
        mock_plugin: The mock plugin instance to test.

    Raises:
        pytest.Failed: If the plugin fails to start.
    """
    try:
        await mock_plugin.internal_start()
    except Exception as e:
        pytest.fail(f"Plugin failed to start: {e}")


@pytest.mark.asyncio
async def test_config_loads(mock_plugin: NSFWModelPlugin) -> None:
    """Test that the plugin configuration loads with correct values.

    This test verifies that:
    1. The max_concurrent_jobs setting is correct
    2. The via_servers list contains the expected server
    3. The ignore_sfw action is set correctly
    4. The NSFW threshold is set to the default value

    Args:
        mock_plugin: The mock plugin instance to test.

    Raises:
        pytest.Failed: If any configuration values are incorrect.
    """
    config = cast(MockConfig, mock_plugin.config)
    base_config = config.load_base()

    # Test max_concurrent_jobs
    if base_config["max_concurrent_jobs"] != 1:
        pytest.fail("Incorrect max_concurrent_jobs value")

    # Test via_servers
    if "matrix.org" not in base_config["via_servers"]:
        pytest.fail("matrix.org not found in via_servers")

    # Test actions
    if not base_config["actions"]["ignore_sfw"]:
        pytest.fail("ignore_sfw should be True")

    # Test NSFW threshold
    if base_config["nsfw_threshold"] != 0.5:
        pytest.fail("Default NSFW threshold should be 0.5")


@pytest.mark.asyncio
async def test_nsfw_threshold_loads(mock_plugin: NSFWModelPlugin) -> None:
    """Test that the NSFW threshold is properly loaded from config.

    This test verifies that:
    1. The default threshold is loaded correctly
    2. The threshold is accessible in the plugin instance
    3. The threshold is a valid float between 0 and 1

    Args:
        mock_plugin: The mock plugin instance to test.

    Raises:
        pytest.Failed: If the NSFW threshold is not properly configured.
    """
    await mock_plugin.start()

    # Check threshold is loaded
    if not hasattr(mock_plugin, "nsfw_threshold"):
        pytest.fail("NSFW threshold not found in plugin instance")

    # Check threshold is correct type and value
    if not isinstance(mock_plugin.nsfw_threshold, float):
        pytest.fail("NSFW threshold should be a float")

    # Check threshold is in valid range
    if not 0 <= mock_plugin.nsfw_threshold <= 1:
        pytest.fail("NSFW threshold should be between 0 and 1")

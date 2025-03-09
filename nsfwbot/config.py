"""Configuration management for the NSFW detection plugin.

This module handles the plugin's configuration settings, which control its behaviour
in Matrix chat rooms. The configuration system uses Maubot's BaseProxyConfig to manage:

Settings available:
    max_concurrent_jobs (int):
        Controls how many images can be processed simultaneously.
        Default: 4

    nsfw_threshold (float):
        The confidence threshold for classifying an image as NSFW.
        Range: 0.0 to 1.0 (0% to 100%)
        Default: 0.5 (50%)

    report_to_room (str):
        The room ID to report NSFW images to.
        Example: "!room:example.org"

    via_servers (list[str]):
        List of Matrix servers to include in matrix.to URLs.
        Example: ["matrix.org", "tcpip.uk"]

    actions (dict):
        Configurable responses to detected content:
        - ignore_sfw (bool): Skip reporting safe content
        - redact_nsfw (bool): Remove inappropriate messages
        - direct_reply (bool): Reply in the same room
        - post_errors (bool): Post errors to the report room

Example config.yaml:
    max_concurrent_jobs: 4
    nsfw_threshold: 0.6  # 60% confidence threshold
    report_to_room: "#moderation:example.org"
    via_servers:
      - "matrix.org"
    actions:
      ignore_sfw: true
      redact_nsfw: false
      direct_reply: true
      post_errors: true
"""

from __future__ import annotations

from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    """Configuration manager for the NSFWModelPlugin."""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """Update the configuration with new values.

        This method is called when the user modifies the config.
        It copies values from the user-provided config into the base config.

        Args:
            helper: Helper object to copy configuration values.
        """
        # Copy configuration values from user config to base config
        helper.copy("max_concurrent_jobs")
        helper.copy("nsfw_threshold")
        helper.copy("via_servers")
        helper.copy("report_to_room")
        helper.copy("actions")

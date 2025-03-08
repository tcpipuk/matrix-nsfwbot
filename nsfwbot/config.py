"""Configuration management for the NSFWModelPlugin."""

from __future__ import annotations

from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    """Configuration manager for the NSFWModelPlugin."""

    def do_update(self, helper: ConfigUpdateHelper) -> None:
        """Update the configuration with new values.

        Args:
            helper: Helper object to copy configuration values.
        """
        helper.copy("max_concurrent_jobs")
        helper.copy("via_servers")
        helper.copy("actions")

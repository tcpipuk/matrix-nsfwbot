"""NSFW Model Plugin for Maubot.

This plugin detects NSFW content in images and text messages containing image tags,
and takes appropriate actions based on the configuration.
"""

from __future__ import annotations

from nsfwbot.plugin import NSFWModelPlugin

__all__ = ["NSFWModelPlugin"]

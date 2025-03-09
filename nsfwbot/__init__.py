"""Matrix bot plugin for detecting and managing NSFW content in images.

This package provides a Maubot plugin that helps maintain appropriate content in Matrix
chat rooms by analysing images for NSFW (Not Safe For Work) content. The plugin can:
- detect NSFW content in directly posted images
- analyse images embedded in text messages
- take configurable actions like reporting or removing inappropriate content
- provide detailed feedback about detected content

The plugin is structured into several modules:
- config: Configuration management and settings
- models: Data structures for image analysis results
- plugin: Core plugin implementation and Matrix event handling
- utils: Helper functions for URL creation and HTML parsing

For setup and usage instructions, see the README.md file.

Example usage in matrix-docker-ansible-deploy:
    maubot:
      plugins:
        nsfwbot:
          image: "ghcr.io/tcpipuk/maubot:debian"
          version: "v0.3.0"
          config:
            max_concurrent_jobs: 4
            actions:
              redact_nsfw: true
"""

from __future__ import annotations

from nsfwbot.plugin import NSFWModelPlugin

__all__ = ["NSFWModelPlugin"]

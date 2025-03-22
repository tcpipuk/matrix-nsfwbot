# nsfwbot for Matrix

`nsfwbot` is a [Maubot](https://github.com/maubot/maubot) plugin for Matrix that helps maintain
appropriate content in chat rooms by detecting NSFW (Not Safe For Work) images. It uses
[nsfwdetection](https://github.com/gsarridis/NSFW-Detection-Pytorch), a lightweight model that can
run efficiently without requiring a GPU.

## Features

- **Image Analysis**: Detects and analyses images posted in Matrix chats.
- **Text Message Parsing**: Analyses images embedded in text messages.
- **Configurable Concurrency**: Controls concurrent image processing tasks.
- **Configurable Threshold**: Adjust the NSFW detection threshold to avoid false positives.
- **Custom Actions**: Configurable actions for detected content, including reporting and redacting messages.
- **Error Reporting**: Option to report processing errors to a moderation room.

## Requirements

- **Maubot**
- **Python Dependencies**:
  - `beautifulsoup4`: For HTML message parsing
  - `nsfwdetection`: For image content analysis
  - `pillow`: To read and convert images

> **Important**: As well as requiring the above plugins, the default
> Alpine-based Maubot Docker image is not compatible with `nsfwdetection`.
> You can use my custom Debian-based image instead: `ghcr.io/tcpipuk/maubot:debian`

## Quick Start

1. **Use our Debian-based Maubot image**:

   ```bash
   docker pull ghcr.io/tcpipuk/maubot:debian
   ```

2. **Install the plugin** (choose one method):
   - Download from [releases](https://github.com/tcpipuk/matrix-nsfwbot/releases)
   - Build from source:

     ```bash
     git clone https://github.com/tcpipuk/matrix-nsfwbot
     cd matrix-nsfwbot
     zip -r nsfwbot.mbp nsfwbot/ maubot.yaml base-config.yaml
     ```

3. **Upload and Configure**:
   - Upload through the Maubot admin interface
   - Configure settings (see Configuration section)
   - Enable the plugin

## Configuration Guide

Edit settings in the Maubot admin interface or `base-config.yaml`:

```yaml
# Control concurrent processing
max_concurrent_jobs: 2

# NSFW detection threshold (0.0 to 1.0)
nsfw_threshold: 0.65

# Central reporting room
report_to_room: "#moderation:example.org"

# Servers for matrix.to URLs
via_servers:
  - "matrix.org"
  - "example.org"

# Response configuration
actions:
  # Skip reporting safe content
  ignore_sfw: true

  # Remove inappropriate messages
  redact_nsfw: false

  # Reply in the source room
  direct_reply: true

  # Report processing errors to moderation room
  post_errors: false
```

> **Tip**: Using room IDs (like `!room:server`) is more efficient than aliases (like `#room:server`)
> for the `report_to_room` setting.

## Usage Examples

### Single Image Upload

```yaml
User: [uploads image]
Bot: mxc://matrix.org/abc123 in https://matrix.to/#/!room:example.org/$event
     appears NSFW with score 87.93%
```

### Multiple Embedded Images

```yaml
User: [message with embedded images]
Bot: - mxc://matrix.org/abc123 appears SFW with score 2.45%
     - mxc://matrix.org/xyz789 appears NSFW with score 94.82%
```

## Deployment Example

Using matrix-docker-ansible-deploy:

```yaml
maubot:
  plugins:
    nsfwbot:
      image: "ghcr.io/tcpipuk/maubot:debian"
      version: "v0.3.0"
      config:
        max_concurrent_jobs: 4
        nsfw_threshold: 0.65
        actions:
          redact_nsfw: true
          post_errors: true
```

## Contributing

Contributions are welcome! Open an issue or submit a pull request on GitHub.

## Licence

This project is licensed under the AGPLv3 Licence. See the [LICENCE](LICENCE) file for details.

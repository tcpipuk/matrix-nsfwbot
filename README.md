# nsfwbot for Matrix

`nsfwbot` is a Matrix bot plugin that attempts to detect NSFW (Not Safe For Work) images posted in
Matrix chat rooms. It uses [nsfwdetection](https://github.com/gsarridis/NSFW-Detection-Pytorch),
which includes a small model that can run without a GPU with low resource requirements.

## Features

- **Image Analysis**: Detects and analyses images posted in Matrix chats.
- **Text Message Parsing**: Analyses images embedded in text messages.
- **Configurable Concurrency**: Controls concurrent image processing tasks.
- **Custom Actions**: Configurable actions for detected content, including reporting and redacting messages.

## Requirements

- **Maubot**: Runs within the Maubot framework.
- **Python Dependencies**: `nsfwdetection` and `beautifulsoup4`.
  > **Note**: `nsfwdetection` will not run on Alpine Linux. This means the default Maubot Docker
  > image will not work. I have built a custom Debian-based Maubot in the
  > `ghcr.io/tcpipuk/maubot:debian` Docker image.

## Installation

1. **Use the Custom Maubot Docker Image**:
   Replace the official Maubot image with a custom Debian-based image:

   ```bash
   docker pull ghcr.io/tcpipuk/maubot:debian
   ```

2. a. **Install pre-prepared plugin from [repository releases](https://github.com/tcpipuk/matrix-nsfwbot/releases)**

   b. **Clone the Repository**:

      ```bash
      git clone https://github.com/tcpipuk/matrix-nsfwbot
      ```

      Zip the plugin files and upload through the Maubot admin interface. Ensure the plugin is
      configured and enabled.

3. **Configure the Plugin**:
   See configuration section below for a summary of settings in the Maubot UI.

## Configuration

Edit `base-config.yaml` to set:

- `max_concurrent_jobs`: Number of concurrent jobs to allow.
- `via_servers`: List of servers for `matrix.to` URLs.
- `actions`:
  - `ignore_sfw`: Ignore SFW images (default: `true`).
  - `redact_nsfw`: Redact NSFW messages (default: `false`).
  - `direct_reply`: Reply directly in the same room (default: `false`).
  - `report_to_room`: Room ID for reporting (not enabled by default).
    > **Note**: This can be a room alias (like `#room:server`) but this is far less efficient,
      as the bot will need to find the room ID (like `!room:server`) to send messages.

## Usage

Once installed and configured, `nsfwbot` will automatically analyse images posted in the chat and
reply with a classification result, e.g.

```markdown
mxc://matrix.org/abcd1234 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears NSFW with score 87.93%
```

If multiple images are detected in a text message:

```markdown
- mxc://matrix.org/abcd1234 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears SFW with score 2.45%
- mxc://matrix.org/efgh5678 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears NSFW with score 94.82%
```

## Contributing

Contributions are welcome! Open an issue or submit a pull request on GitHub.

## License

This project is licensed under the AGPLv3 License. See the [LICENSE](LICENSE) file for details.

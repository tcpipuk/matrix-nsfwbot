# nsfwbot for Matrix

nsfwbot is a Matrix bot plugin designed to detect NSFW (Not Safe For Work) content in images posted in Matrix chat rooms. This plugin leverages the [nsfwdetection](https://github.com/gsarridis/NSFW-Detection-Pytorch) model to analyze images and return a classification result, indicating whether the content is likely to be NSFW or SFW (Safe For Work).

## Features

- **Image Analysis**: Automatically detects images posted in a Matrix chat and analyzes them using the NSFW detection model.
- **Text Message Parsing**: Parses text messages for embedded `<img>` tags and analyzes those images as well.
- **Configurable Concurrency**: Controls the number of concurrent image processing tasks using a configurable semaphore.
- **Customizable `via_servers`**: Allows users to customize the list of servers used in the `matrix.to` URLs for linking back to the original message.
- **Planned Features**: While the plugin currently only returns a classification of the image content, future updates are planned to include moderation actions such as automatically deleting or flagging unwanted images.

## Requirements

- **Maubot**: The plugin is designed to run within the Maubot framework.
- **Python Dependencies**: The plugin relies on the `nsfwdetection` and `beautifulsoup4` Python modules. These are automatically installed by the plugin if they are not already present.

## Installation

### 1. Use the Custom Maubot Docker Image

The `nsfwdetection` plugin does not currently run on Alpine Linux, which is the base image for the official Maubot Docker container. To use `nsfwbot`, you need to switch to a Debian-based container.

- Replace the official Maubot image with a custom Debian-based image:

  ```
  ghcr.io/tcpipuk/maubot:debian
  ```
  
- This custom image is a drop-in replacement for the official Maubot image and comes pre-installed with the `nsfwdetection` and `beautifulsoup4` modules, allowing for faster deployment of `nsfwbot`.

### 2. Clone the Repository

Clone the `nsfwbot` plugin repository from GitHub:

```bash
git clone https://github.com/tcpipuk/matrix-nsfwbot
```

### 3. Configure the Plugin

Edit the `base-config.yaml` file to customize the settings according to your needs:

- **`via_servers`**: List of servers to include in the `via` parameter for `matrix.to` URLs.
- **`max_concurrent_jobs`**: Maximum number of concurrent image processing jobs. This controls the Semaphore used to limit concurrency.

### 4. Upload the Plugin to Maubot

Zip the plugin files and upload the plugin through the Maubot administration interface. Ensure that the plugin is configured and enabled.

## Usage

Once installed and configured, `nsfwbot` will automatically analyze images posted in the chat. The plugin replies to the message containing the image with a classification result, indicating whether the image is NSFW or SFW.

### Example Output

When an image is detected and analyzed, `nsfwbot` will reply to the message with something like:

```
mxc://matrix.org/abcd1234 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears NSFW with score 87.93%
```

If multiple images are detected in a text message:

```
- mxc://matrix.org/abcd1234 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears SFW with score 2.45%
- mxc://matrix.org/efgh5678 in https://matrix.to/#/!roomid:matrix.org/$eventid?via=matrix.org appears NSFW with score 94.82%
```

## Planned Features

- **Automatic Moderation**: The ability to automatically take action (e.g., delete or flag messages) when NSFW content is detected.
- **Custom Actions**: Allowing users to configure specific actions for different types of detected content.

## Notes

- **Debian-based Maubot Container**: If using Docker, the custom container image at `ghcr.io/tcpipuk/maubot:debian` is required due to compatibility issues with Alpine. This image is a direct replacement for the official Maubot image and is necessary for running `nsfwbot`.
- **Manual Installations**: If you prefer to use a different environment, ensure that `nsfwdetection` and `beautifulsoup4` are installed, and note that Alpine is not supported.

## Contributing

Contributions to `nsfwbot` are welcome! Feel free to open an issue or submit a pull request on GitHub.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

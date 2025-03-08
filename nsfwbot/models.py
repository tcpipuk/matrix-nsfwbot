"""Data models for managing image analysis and results.

This module provides the core data structures used to track and process images
within the NSFW detection system. It includes:

Classes:
    ImageResult:
        Tracks the analysis of a single image, including:
        - Download status and temporary storage
        - NSFW detection results and confidence scores
        - Error handling and reporting

    BatchImageScan:
        Manages processing multiple images from a single message:
        - Concurrent image downloads
        - Batch NSFW detection
        - Result formatting and temporary file cleanup

The models ensure consistent handling of images throughout the detection process,
from initial download through analysis to result reporting. They handle both
direct image posts and images embedded in text messages.

Example result format:
    mxc://matrix.org/abc123 in https://matrix.to/#/!room:example.org/$event
    appears NSFW with score 94.82%

Technical details:
    - Images are downloaded to temporary files
    - NSFW detection uses the nsfwdetection library
    - Results include both classification and confidence scores
    - All temporary files are properly cleaned up after processing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger

    from maubot.matrix import MaubotMatrixClient as Client, MaubotMessageEvent as MessageEvent
    from mautrix.types import ContentURI
    from nsfw_detector import Model


@dataclass(slots=True)
class ImageResult:
    """Represents the result of processing a single image."""

    mxc_url: ContentURI
    nsfw_threshold: float
    temp_path: str | None = field(default=None)
    prediction: dict | None = field(default=None)
    error: Exception | None = field(default=None)

    @property
    def success(self) -> bool:
        """Check if the image was processed successfully."""
        return self.temp_path is not None and self.prediction is not None

    @property
    def is_nsfw(self) -> bool | None:
        """Check if the image is classified as NSFW based on the configured threshold."""
        # Return None if the image was not processed successfully
        if not self.success or self.prediction is None:
            return None
        # Return True if the score is greater than or equal to the threshold
        return bool(self.prediction["Score"] >= self.nsfw_threshold)

    def format_result(self, matrix_to_url: str) -> str:
        """Format the result for display.

        Args:
            matrix_to_url: The matrix.to URL for the message.

        Returns:
            Formatted string describing the result.
        """
        if not self.success:
            return f"{self.mxc_url} in {matrix_to_url} could not be processed: {self.error}"
        return (
            f"{self.mxc_url} in {matrix_to_url} appears {self.prediction['Label']} "
            f"with score {self.prediction['Score']:.2%}"
        )


@dataclass(slots=True)
class BatchImageScan:
    """Manages a batch of images to be scanned."""

    event: MessageEvent
    mxc_urls: list[ContentURI]
    logger: Logger
    model: Model
    nsfw_threshold: float
    images: list[ImageResult] = field(init=False)
    matrix_to_url: str = field(init=False)

    def __post_init__(self) -> None:
        """Initialise the scan result with empty image results."""
        self.images = [
            ImageResult(url, nsfw_threshold=self.nsfw_threshold) for url in self.mxc_urls
        ]
        self.matrix_to_url = ""

    @property
    def has_nsfw(self) -> bool:
        """Check if any successfully processed images are NSFW."""
        return any(img.is_nsfw for img in self.images)

    @property
    def all_succeeded(self) -> bool:
        """Check if all images were processed successfully."""
        return all(img.success for img in self.images)

    async def download_images(self, client: Client) -> None:
        """Download all images concurrently.

        Args:
            client: The Matrix client to use for downloads.
        """
        from asyncio import gather
        from tempfile import NamedTemporaryFile

        async def download_single(image: ImageResult) -> None:
            try:
                with NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                    img_bytes = await client.download_media(image.mxc_url)
                    Path(temp_file.name).write_bytes(img_bytes)
                    image.temp_path = temp_file.name
            except Exception as e:
                image.error = e
                self.logger.warning("Failed to download %s: %s", image.mxc_url, e)

        await gather(*[download_single(image) for image in self.images])

    def process_images(self) -> None:
        """Process all successfully downloaded images with the NSFW model."""
        try:
            # Get paths of successfully downloaded images
            valid_images = [(img.mxc_url, img.temp_path) for img in self.images if img.temp_path]
            if not valid_images:
                return

            # Run predictions
            predictions = self.model.predict([path for _, path in valid_images])

            # Update image results with predictions
            for img in self.images:
                if img.temp_path and img.temp_path in predictions:
                    img.prediction = predictions[img.temp_path]
        except Exception as e:
            self.logger.exception("Error processing images with model")
            for img in self.images:
                if not img.error:  # Don't overwrite download errors
                    img.error = e

    def cleanup(self) -> None:
        """Remove all temporary files."""
        for img in self.images:
            if img.temp_path:
                Path(img.temp_path).unlink(missing_ok=True)

    def format_response(self) -> str:
        """Format the complete scan results for display.

        Returns:
            Formatted string containing all results.
        """
        parts = [img.format_result(self.matrix_to_url) for img in self.images]
        return "- " + "\n- ".join(parts) if len(parts) > 1 else parts[0]

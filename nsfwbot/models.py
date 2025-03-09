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
from decimal import Decimal, getcontext as decimal_getcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Set precision for Decimal calculations
decimal_getcontext().prec = 10

if TYPE_CHECKING:
    from logging import Logger

    from maubot.matrix import MaubotMatrixClient as Client, MaubotMessageEvent as MessageEvent
    from mautrix.types import ContentURI
    from nsfw_detector import Model


@dataclass(slots=True)
class ImageResult:
    """Represents the result of processing a single image."""

    mxc_url: ContentURI
    config: Any
    temp_path: str | None = field(default=None)
    prediction: dict | None = field(default=None)
    error: Exception | None = field(default=None)

    @property
    def success(self) -> bool:
        """Check if the image was processed successfully."""
        return self.temp_path is not None and self.prediction is not None

    @property
    def is_nsfw(self) -> bool | None:
        """Check if the image is classified as NSFW based on the configured threshold.

        We only care about the score compared to our configured threshold,
        not the model's own binary classification label.

        Returns:
            bool|None: True if score >= threshold, False if score < threshold, None if failed
        """
        # Return None if the image was not processed successfully
        if not self.success or self.prediction is None:
            return None

        # Read threshold directly from config and convert to Decimal
        threshold = Decimal(str(self.config.get("nsfw_threshold", 0.5)))

        # Get the score and convert to Decimal
        score = Decimal(str(self.prediction["Score"]))

        # Return True if the score is greater than or equal to the threshold
        return bool(score >= threshold)

    def format_result(self, matrix_to_url: str) -> str:
        """Format the result for display.

        Args:
            matrix_to_url: The matrix.to URL for the message.

        Returns:
            Formatted string describing the result.
        """
        if not self.success:
            error_msg = str(self.error) if self.error else "unknown error"
            # Check for common error patterns
            if "broadcast" in error_msg and "shapes" in error_msg:
                return (
                    f"{self.mxc_url} in {matrix_to_url} could not be processed: "
                    "image format error (RGBA vs RGB)"
                )
            return f"{self.mxc_url} in {matrix_to_url} could not be processed: {error_msg}"

        # Read threshold directly from config and convert to Decimal
        threshold = Decimal(str(self.config.get("nsfw_threshold", 0.5)))

        # Format the result with score percentage
        score = Decimal(str(self.prediction["Score"]))

        # Determine if NSFW based on our threshold, not the model's label
        is_nsfw = score >= threshold
        our_label = "NSFW" if is_nsfw else "SFW"
        threshold_status = "above" if is_nsfw else "below"

        return (
            f"{self.mxc_url} in {matrix_to_url} appears {our_label} "
            f"with score {score:.2%} ({threshold_status} threshold of {threshold:.2%})"
        )


@dataclass(slots=True)
class BatchImageScan:
    """Manages a batch of images to be scanned.

    Args:
        evt: The Matrix message event being processed.
        mxc_urls: List of Matrix content URLs to scan.
        logger: Logger instance for recording scan progress.
        model: NSFW detection model instance.
        config: The plugin configuration object.
    """

    evt: MessageEvent
    mxc_urls: list[ContentURI]
    logger: Logger
    model: Model
    config: Any
    images: list[ImageResult] = field(init=False)
    matrix_to_url: str = field(init=False)

    def __post_init__(self) -> None:
        """Initialise the scan result with empty image results."""
        self.images = [ImageResult(url, config=self.config) for url in self.mxc_urls]
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

    def _process_single_image(self, path: str) -> tuple[dict | None, Exception | None]:
        """Process a single image and handle errors.

        Args:
            path: Path to the image file

        Returns:
            Tuple of (prediction, error)
        """
        try:
            # Process the image
            single_prediction = self.model.predict([path])
            if path in single_prediction:
                return single_prediction[path], None
            return None, ValueError(f"No prediction for {path}")
        except ValueError as e:
            # Handle channel mismatch errors (RGBA vs RGB)
            error_msg = str(e)
            if "broadcast" in error_msg and "shapes" in error_msg:
                self.logger.warning("RGBA image detected, cannot process: %s", path)
                return None, ValueError("Model doesn't know how to handle RGBA images yet")
            self.logger.warning("ValueError processing image: %s", error_msg)
            return None, e
        except Exception as e:
            self.logger.warning("Error processing image: %s", e)
            return None, e

    def process_images(self) -> None:
        """Process all successfully downloaded images with the NSFW model."""
        try:
            # Get paths of successfully downloaded images
            valid_images = [(img.mxc_url, img.temp_path) for img in self.images if img.temp_path]
            if not valid_images:
                return

            # Process each image
            for img in self.images:
                if not img.temp_path:
                    continue

                # Process the image
                try:
                    prediction, error = self._process_single_image(img.temp_path)

                    # Store responses for processing
                    if prediction:
                        img.prediction = prediction
                    elif error:
                        img.error = error
                        self.logger.warning("Error processing image %s: %s", img.mxc_url, error)
                except Exception as e:
                    img.error = e
                    self.logger.exception("Unexpected error processing image %s", img.mxc_url)

        except Exception as e:
            self.logger.exception("Error processing images with model")
            for img in self.images:
                if not img.error:
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

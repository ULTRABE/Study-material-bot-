"""
Media processor: download, optimize, and store media files.
Runs in a separate process via the worker pool.
"""
import os
import asyncio
import logging
import subprocess
import tempfile
import time
from typing import Optional, Callable, Awaitable
from pathlib import Path

import httpx

from app.config import settings
from app.utils.helpers import ensure_dir, format_file_size

logger = logging.getLogger(__name__)


class DownloadProgress:
    """Tracks download progress."""

    def __init__(self, total_bytes: int = 0):
        self.total_bytes = total_bytes
        self.downloaded_bytes = 0
        self.start_time = time.time()

    @property
    def percent(self) -> int:
        if self.total_bytes <= 0:
            return 0
        return min(100, int(self.downloaded_bytes / self.total_bytes * 100))

    @property
    def speed_mbps(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0
        return (self.downloaded_bytes / (1024 * 1024)) / elapsed


class MediaProcessor:
    """
    Handles the full media processing pipeline:
    1. Validate URL
    2. Download stream
    3. Optimize with ffmpeg
    4. Store temporary file
    """

    SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts"}
    SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".aac", ".ogg", ".flac", ".wav", ".m4a"}

    def __init__(self):
        ensure_dir(settings.TEMP_DIR)

    async def process(
        self,
        url: str,
        job_id: str,
        progress_callback: Optional[Callable[[int, str], Awaitable[None]]] = None,
    ) -> Optional[str]:
        """
        Full processing pipeline.
        Returns path to processed file, or None on failure.
        """
        # Step 1: Detect
        if progress_callback:
            await progress_callback(0, "detecting")

        # Step 2: Extract stream info
        if progress_callback:
            await progress_callback(5, "extracting")

        content_type, content_length = await self._probe_url(url)
        if content_type is None:
            raise ValueError("Unable to access media URL. Check the link and try again.")

        # Step 3: Download
        if progress_callback:
            await progress_callback(10, "downloading")

        raw_path = await self._download_file(url, job_id, content_length, progress_callback)
        if raw_path is None:
            raise ValueError("Download failed. The file may be too large or unavailable.")

        # Step 4: Optimize
        if progress_callback:
            await progress_callback(70, "optimizing")

        output_path = await self._optimize_file(raw_path, job_id, progress_callback)

        # Clean up raw file if different from output
        if raw_path != output_path and os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass

        if progress_callback:
            await progress_callback(100, "complete")

        return output_path

    async def _probe_url(self, url: str) -> tuple:
        """
        Probe URL for content type and length.
        Returns (content_type, content_length) or (None, None) on failure.
        """
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 RavenBot/1.0"},
            ) as client:
                resp = await client.head(url)
                if resp.status_code not in (200, 206):
                    # Try GET with range
                    resp = await client.get(
                        url,
                        headers={"Range": "bytes=0-0"},
                    )
                    if resp.status_code not in (200, 206):
                        return None, None

                content_type = resp.headers.get("content-type", "")
                content_length_str = resp.headers.get("content-length", "0")
                try:
                    content_length = int(content_length_str)
                except ValueError:
                    content_length = 0

                return content_type, content_length
        except Exception as e:
            logger.warning(f"URL probe failed: {e}")
            return None, None

    async def _download_file(
        self,
        url: str,
        job_id: str,
        content_length: int,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[str]:
        """
        Download file from URL with progress tracking.
        Returns path to downloaded file.
        """
        # Determine extension from URL
        url_path = url.split("?")[0].split("#")[0]
        ext = Path(url_path).suffix.lower()
        if ext not in self.SUPPORTED_VIDEO_EXTENSIONS | self.SUPPORTED_AUDIO_EXTENSIONS:
            ext = ".mp4"  # Default

        raw_filename = f"raw_{job_id}{ext}"
        raw_path = os.path.join(settings.TEMP_DIR, raw_filename)

        progress = DownloadProgress(content_length)
        last_update = time.time()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=15.0, read=300.0, write=30.0, pool=30.0),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 RavenBot/1.0"},
            ) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code not in (200, 206):
                        logger.error(f"Download HTTP error: {resp.status_code}")
                        return None

                    # Update content length from actual response
                    cl = resp.headers.get("content-length")
                    if cl:
                        progress.total_bytes = int(cl)

                    with open(raw_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            progress.downloaded_bytes += len(chunk)

                            # Update progress every 5 seconds
                            now = time.time()
                            if progress_callback and now - last_update >= settings.PROGRESS_UPDATE_INTERVAL:
                                last_update = now
                                # Map download progress to 10-70% range
                                dl_pct = progress.percent
                                mapped_pct = 10 + int(dl_pct * 0.6)
                                await progress_callback(mapped_pct, "downloading")

            return raw_path

        except Exception as e:
            logger.error(f"Download error: {e}")
            if os.path.exists(raw_path):
                os.remove(raw_path)
            return None

    async def _optimize_file(
        self,
        input_path: str,
        job_id: str,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """
        Optimize media file using ffmpeg.
        Preserves audio, FPS, applies balanced compression.
        Returns path to optimized file.
        """
        ext = Path(input_path).suffix.lower()
        output_filename = f"opt_{job_id}.mp4"
        output_path = os.path.join(settings.TEMP_DIR, output_filename)

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]

        try:
            # Run ffmpeg in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._run_ffmpeg,
                cmd,
                job_id,
            )

            if result and os.path.exists(output_path):
                return output_path
            else:
                # If ffmpeg fails, return original file
                logger.warning(f"ffmpeg optimization failed for job {job_id}, using raw file")
                return input_path

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            return input_path

    def _run_ffmpeg(self, cmd: list, job_id: str) -> bool:
        """Run ffmpeg subprocess synchronously."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,  # 10 minute timeout
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg error (job {job_id}): {result.stderr.decode()[-500:]}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timeout for job {job_id}")
            return False
        except FileNotFoundError:
            logger.warning("ffmpeg not found, skipping optimization")
            return False
        except Exception as e:
            logger.error(f"ffmpeg subprocess error: {e}")
            return False

    async def get_media_info(self, file_path: str) -> dict:
        """Get media file information using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, timeout=30),
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout.decode())
        except Exception:
            pass
        return {}

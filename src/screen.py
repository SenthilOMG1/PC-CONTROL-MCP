"""
Fast screen capture module using MSS (Desktop Duplication API on Windows).
"""

import base64
import io
import time
from typing import Optional, Tuple, Dict, Any
import mss
from PIL import Image


class ScreenCapture:
    """High-performance screen capture using Desktop Duplication API."""

    def __init__(self):
        self.sct = mss.mss()
        self._last_capture = None
        self._last_capture_time = 0
        self._cache_ttl = 0.1  # 100ms cache

    def get_monitors(self) -> list:
        """Get list of available monitors."""
        return [
            {
                "index": i,
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
                "is_primary": i == 1  # Monitor 0 is "all monitors combined"
            }
            for i, m in enumerate(self.sct.monitors)
        ]

    def capture(
        self,
        monitor: int = 1,  # 0 = all monitors, 1 = primary, 2+ = others
        region: Optional[Dict[str, int]] = None,  # {x, y, width, height}
        format: str = "jpeg",
        quality: int = 80,
        scale: float = 1.0,
        grayscale: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Capture screen and return base64 encoded image.

        Returns:
            Tuple of (base64_image, metadata)
        """
        start_time = time.perf_counter()

        # Determine capture region
        if region:
            capture_region = {
                "left": region["x"],
                "top": region["y"],
                "width": region["width"],
                "height": region["height"]
            }
        else:
            capture_region = self.sct.monitors[monitor]

        # Capture screenshot (this is FAST - uses GPU)
        screenshot = self.sct.grab(capture_region)

        # Convert to PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # Apply transformations
        original_size = img.size

        if scale != 1.0:
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        if grayscale:
            img = img.convert("L")

        # Encode to bytes
        buffer = io.BytesIO()
        if format.lower() == "jpeg":
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buffer, format="PNG", optimize=True)

        # Base64 encode
        image_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        capture_time = time.perf_counter() - start_time

        metadata = {
            "width": img.width,
            "height": img.height,
            "original_width": original_size[0],
            "original_height": original_size[1],
            "format": format,
            "capture_time_ms": round(capture_time * 1000, 2),
            "size_bytes": len(buffer.getvalue()),
            "monitor": monitor,
            "region": region
        }

        return image_data, metadata

    def capture_region_around_point(
        self,
        x: int,
        y: int,
        width: int = 400,
        height: int = 300,
        **kwargs
    ) -> Tuple[str, Dict[str, Any]]:
        """Capture a region centered around a point."""
        region = {
            "x": max(0, x - width // 2),
            "y": max(0, y - height // 2),
            "width": width,
            "height": height
        }
        return self.capture(region=region, **kwargs)

    def detect_changes(
        self,
        previous: Optional[bytes] = None,
        threshold: float = 0.01
    ) -> Tuple[bool, float]:
        """
        Detect if screen has changed significantly.

        Returns:
            Tuple of (has_changed, change_percentage)
        """
        # Quick capture for comparison
        screenshot = self.sct.grab(self.sct.monitors[1])
        current = screenshot.raw

        if previous is None:
            return True, 1.0

        if len(current) != len(previous):
            return True, 1.0

        # Quick byte comparison (very fast)
        differences = sum(1 for a, b in zip(current, previous) if a != b)
        change_ratio = differences / len(current)

        return change_ratio > threshold, change_ratio


# Global instance
_screen = None

def get_screen() -> ScreenCapture:
    global _screen
    if _screen is None:
        _screen = ScreenCapture()
    return _screen

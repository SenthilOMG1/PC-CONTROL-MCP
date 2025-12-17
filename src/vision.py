"""
Vision module for image-based screen analysis.

Features:
- Template matching (find image on screen)
- Screen change detection
- Image comparison

Uses OpenCV for efficient image processing.
"""

import asyncio
import time
import base64
from typing import Optional, Dict, Any, Tuple, List
from io import BytesIO

# Try to import OpenCV
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

# Fallback to Pillow for basic operations
from PIL import Image, ImageChops

from screen import get_screen


class ScreenVision:
    """Image-based screen analysis."""

    def __init__(self):
        self._screen = get_screen()
        self._last_screenshot = None
        self._last_screenshot_time = 0

    def _decode_image(self, image_data: str) -> 'np.ndarray':
        """Decode base64 image to numpy array (OpenCV format)."""
        image_bytes = base64.b64decode(image_data)
        img = Image.open(BytesIO(image_bytes))

        if HAS_OPENCV:
            # Convert PIL to OpenCV format (BGR)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        else:
            return img

    def _encode_image(self, img: Any, format: str = "png") -> str:
        """Encode image to base64."""
        if HAS_OPENCV and isinstance(img, np.ndarray):
            # OpenCV to bytes
            if format == "png":
                _, buffer = cv2.imencode('.png', img)
            else:
                _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return base64.b64encode(buffer.tobytes()).decode('utf-8')
        elif isinstance(img, Image.Image):
            # PIL to bytes
            buffer = BytesIO()
            img.save(buffer, format=format.upper())
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        return ""

    def _capture_screen_cv(
        self,
        region: Optional[Dict[str, int]] = None,
        monitor: int = 1
    ) -> Tuple[Any, Dict]:
        """Capture screen and return as OpenCV image."""
        image_data, metadata = self._screen.capture(
            monitor=monitor,
            region=region,
            format="png",
            quality=100,
            scale=1.0,
            grayscale=False
        )
        return self._decode_image(image_data), metadata

    def find_image_on_screen(
        self,
        template_data: str,
        region: Optional[Dict[str, int]] = None,
        threshold: float = 0.8,
        grayscale: bool = True,
        monitor: int = 1
    ) -> Dict[str, Any]:
        """
        Find a template image on screen using template matching.

        Args:
            template_data: Base64 encoded template image
            region: Optional region to limit search
            threshold: Match confidence threshold (0-1)
            grayscale: Convert to grayscale for faster matching
            monitor: Monitor to capture

        Returns:
            {
                "found": True/False,
                "confidence": float,
                "location": {"x", "y", "width", "height", "center_x", "center_y"},
                "all_matches": [...]  # If multiple matches found
            }
        """
        if not HAS_OPENCV:
            return self._find_image_pillow(template_data, region, threshold)

        # Capture screen
        screen_img, metadata = self._capture_screen_cv(region=region, monitor=monitor)
        template_img = self._decode_image(template_data)

        # Convert to grayscale if requested
        if grayscale:
            if len(screen_img.shape) == 3:
                screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
            else:
                screen_gray = screen_img

            if len(template_img.shape) == 3:
                template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
            else:
                template_gray = template_img
        else:
            screen_gray = screen_img
            template_gray = template_img

        # Template matching
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)

        # Find best match
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        template_h, template_w = template_gray.shape[:2]

        # Offset for region
        offset_x = region.get("x", 0) if region else 0
        offset_y = region.get("y", 0) if region else 0

        if max_val >= threshold:
            location = {
                "x": max_loc[0] + offset_x,
                "y": max_loc[1] + offset_y,
                "width": template_w,
                "height": template_h,
                "center_x": max_loc[0] + offset_x + template_w // 2,
                "center_y": max_loc[1] + offset_y + template_h // 2
            }

            # Find all matches above threshold
            all_matches = []
            locations = np.where(result >= threshold)
            for pt in zip(*locations[::-1]):
                all_matches.append({
                    "x": pt[0] + offset_x,
                    "y": pt[1] + offset_y,
                    "width": template_w,
                    "height": template_h,
                    "center_x": pt[0] + offset_x + template_w // 2,
                    "center_y": pt[1] + offset_y + template_h // 2,
                    "confidence": float(result[pt[1], pt[0]])
                })

            # Remove duplicates (overlapping matches)
            all_matches = self._filter_overlapping_matches(all_matches)

            return {
                "found": True,
                "confidence": float(max_val),
                "location": location,
                "all_matches": all_matches[:10]  # Limit to 10
            }

        return {
            "found": False,
            "confidence": float(max_val),
            "location": None,
            "message": f"Best match confidence {max_val:.2f} below threshold {threshold}"
        }

    def _find_image_pillow(
        self,
        template_data: str,
        region: Optional[Dict[str, int]] = None,
        threshold: float = 0.8
    ) -> Dict[str, Any]:
        """Fallback image matching using Pillow (slower, less accurate)."""
        # This is a basic implementation - OpenCV is much better
        return {
            "found": False,
            "error": "OpenCV not available. Install opencv-python for image matching.",
            "location": None
        }

    def _filter_overlapping_matches(
        self,
        matches: List[Dict],
        overlap_threshold: float = 0.5
    ) -> List[Dict]:
        """Remove overlapping match rectangles."""
        if not matches:
            return []

        # Sort by confidence
        matches = sorted(matches, key=lambda m: m.get("confidence", 0), reverse=True)
        filtered = [matches[0]]

        for match in matches[1:]:
            overlaps = False
            for existing in filtered:
                # Check overlap
                x1 = max(match["x"], existing["x"])
                y1 = max(match["y"], existing["y"])
                x2 = min(match["x"] + match["width"], existing["x"] + existing["width"])
                y2 = min(match["y"] + match["height"], existing["y"] + existing["height"])

                if x1 < x2 and y1 < y2:
                    overlap_area = (x2 - x1) * (y2 - y1)
                    match_area = match["width"] * match["height"]
                    if overlap_area / match_area > overlap_threshold:
                        overlaps = True
                        break

            if not overlaps:
                filtered.append(match)

        return filtered

    async def wait_for_screen_change(
        self,
        region: Optional[Dict[str, int]] = None,
        timeout: float = 10.0,
        threshold: float = 0.02,
        poll_interval: float = 0.1,
        monitor: int = 1
    ) -> Dict[str, Any]:
        """
        Wait for the screen to change.

        Args:
            region: Optional region to monitor
            timeout: Max wait time in seconds
            threshold: Change threshold (0-1, where 0.02 = 2% pixels changed)
            poll_interval: Time between checks
            monitor: Monitor to watch

        Returns:
            {
                "changed": True/False,
                "change_percent": float,
                "elapsed": float
            }
        """
        # Capture initial screenshot
        initial_img, _ = self._capture_screen_cv(region=region, monitor=monitor)
        start_time = time.time()

        while time.time() - start_time < timeout:
            await asyncio.sleep(poll_interval)

            current_img, _ = self._capture_screen_cv(region=region, monitor=monitor)
            change_percent = self._compare_images(initial_img, current_img)

            if change_percent >= threshold:
                return {
                    "changed": True,
                    "change_percent": change_percent,
                    "elapsed": time.time() - start_time
                }

        return {
            "changed": False,
            "change_percent": 0.0,
            "elapsed": time.time() - start_time,
            "message": "Timeout waiting for screen change"
        }

    def _compare_images(self, img1: Any, img2: Any) -> float:
        """Compare two images and return percentage difference."""
        if HAS_OPENCV:
            # Convert to grayscale for comparison
            if len(img1.shape) == 3:
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            else:
                gray1 = img1

            if len(img2.shape) == 3:
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            else:
                gray2 = img2

            # Calculate absolute difference
            diff = cv2.absdiff(gray1, gray2)
            # Count non-zero pixels (changed pixels)
            changed_pixels = np.count_nonzero(diff > 10)  # threshold for noise
            total_pixels = diff.size

            return changed_pixels / total_pixels
        else:
            # Pillow fallback
            if isinstance(img1, Image.Image) and isinstance(img2, Image.Image):
                diff = ImageChops.difference(img1.convert('L'), img2.convert('L'))
                diff_array = list(diff.getdata())
                changed = sum(1 for p in diff_array if p > 10)
                return changed / len(diff_array)
            return 0.0

    def get_screen_diff(
        self,
        img1_data: str,
        img2_data: str,
        highlight_color: Tuple[int, int, int] = (255, 0, 0)
    ) -> Dict[str, Any]:
        """
        Get visual diff between two screenshots.

        Args:
            img1_data: Base64 first image
            img2_data: Base64 second image
            highlight_color: Color to highlight differences (BGR)

        Returns:
            {
                "diff_percent": float,
                "diff_image": str (base64),
                "changed_regions": [{"x", "y", "width", "height"}, ...]
            }
        """
        if not HAS_OPENCV:
            return {"error": "OpenCV required for diff visualization"}

        img1 = self._decode_image(img1_data)
        img2 = self._decode_image(img2_data)

        # Ensure same size
        if img1.shape != img2.shape:
            return {"error": "Images must be same size"}

        # Calculate diff
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray1, gray2)

        # Threshold to get binary mask
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # Find contours of changed regions
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Draw on copy of img2
        result = img2.copy()
        changed_regions = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 100:  # Filter small noise
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(result, (x, y), (x + w, y + h), highlight_color, 2)
                changed_regions.append({
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h)
                })

        diff_percent = np.count_nonzero(thresh) / thresh.size

        return {
            "diff_percent": float(diff_percent),
            "diff_image": self._encode_image(result),
            "changed_regions": changed_regions
        }


# Global instance
_screen_vision = None


def get_screen_vision() -> ScreenVision:
    global _screen_vision
    if _screen_vision is None:
        _screen_vision = ScreenVision()
    return _screen_vision

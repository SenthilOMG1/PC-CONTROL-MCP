"""
OCR module for text recognition on screen.

Uses Windows Runtime OCR API (built into Windows 10/11).
This is the FALLBACK for when UI Automation doesn't work (e.g., browsers).

Key features:
- No external installation needed (uses Windows built-in OCR)
- Fast, GPU-accelerated
- Works with any application including browsers
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Tuple
from io import BytesIO

# Screen capture for OCR
from screen import get_screen

# Try to import Windows Runtime OCR
try:
    import winrt.windows.media.ocr as wocr
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.storage.streams as streams
    HAS_WINRT_OCR = True
except ImportError:
    HAS_WINRT_OCR = False

# Fallback to pytesseract if winrt not available
try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


class OCREngine:
    """OCR engine using Windows Runtime API."""

    def __init__(self):
        self._engine = None
        self._available = False
        self._init_engine()

    def _init_engine(self):
        """Initialize the OCR engine."""
        if HAS_WINRT_OCR:
            try:
                # Get system language or use English
                self._engine = wocr.OcrEngine.try_create_from_user_profile_languages()
                if self._engine:
                    self._available = True
                else:
                    # Try English specifically
                    from winrt.windows.globalization import Language
                    lang = Language("en-US")
                    self._engine = wocr.OcrEngine.try_create_from_language(lang)
                    self._available = self._engine is not None
            except Exception as e:
                self._available = False
        elif HAS_TESSERACT:
            self._available = True

    @property
    def available(self) -> bool:
        return self._available

    async def recognize_async(
        self,
        image_data: bytes,
        region: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Perform OCR on image data.

        Args:
            image_data: PNG or JPEG image bytes
            region: Optional region to crop before OCR

        Returns:
            {
                "text": "full text",
                "words": [{"text": "word", "bounds": {...}, "confidence": 0.95}, ...],
                "lines": [{"text": "line", "bounds": {...}}, ...]
            }
        """
        if not self._available:
            return {"error": "OCR not available", "text": "", "words": [], "lines": []}

        try:
            if HAS_WINRT_OCR and self._engine:
                return await self._recognize_winrt(image_data, region)
            elif HAS_TESSERACT:
                return self._recognize_tesseract(image_data, region)
        except Exception as e:
            return {"error": str(e), "text": "", "words": [], "lines": []}

        return {"error": "No OCR engine available", "text": "", "words": [], "lines": []}

    async def _recognize_winrt(
        self,
        image_data: bytes,
        region: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """Use Windows Runtime OCR."""
        # Convert image bytes to SoftwareBitmap
        stream = streams.InMemoryRandomAccessStream()
        writer = streams.DataWriter(stream)
        writer.write_bytes(image_data)
        await writer.store_async()
        stream.seek(0)

        # Decode image
        decoder = await imaging.BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        # Run OCR
        result = await self._engine.recognize_async(bitmap)

        # Parse results
        words = []
        lines = []
        full_text_parts = []

        for line in result.lines:
            line_text = line.text
            full_text_parts.append(line_text)

            line_bounds = {
                "x": int(line.words[0].bounding_rect.x) if line.words else 0,
                "y": int(line.words[0].bounding_rect.y) if line.words else 0,
                "width": int(sum(w.bounding_rect.width for w in line.words)),
                "height": int(max(w.bounding_rect.height for w in line.words)) if line.words else 0
            }
            lines.append({"text": line_text, "bounds": line_bounds})

            for word in line.words:
                rect = word.bounding_rect
                words.append({
                    "text": word.text,
                    "bounds": {
                        "x": int(rect.x),
                        "y": int(rect.y),
                        "width": int(rect.width),
                        "height": int(rect.height),
                        "center_x": int(rect.x + rect.width / 2),
                        "center_y": int(rect.y + rect.height / 2)
                    }
                })

        return {
            "text": "\n".join(full_text_parts),
            "words": words,
            "lines": lines
        }

    def _recognize_tesseract(
        self,
        image_data: bytes,
        region: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """Use Tesseract OCR as fallback."""
        img = Image.open(BytesIO(image_data))

        if region:
            img = img.crop((
                region["x"],
                region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"]
            ))

        # Get detailed data
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        words = []
        lines = []
        current_line = []
        current_line_num = -1

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue

            conf = int(data["conf"][i])
            if conf < 0:
                continue

            word_data = {
                "text": text,
                "bounds": {
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                    "center_x": data["left"][i] + data["width"][i] // 2,
                    "center_y": data["top"][i] + data["height"][i] // 2
                },
                "confidence": conf / 100.0
            }
            words.append(word_data)

            line_num = data["line_num"][i]
            if line_num != current_line_num:
                if current_line:
                    lines.append({
                        "text": " ".join(w["text"] for w in current_line),
                        "bounds": self._merge_bounds([w["bounds"] for w in current_line])
                    })
                current_line = [word_data]
                current_line_num = line_num
            else:
                current_line.append(word_data)

        if current_line:
            lines.append({
                "text": " ".join(w["text"] for w in current_line),
                "bounds": self._merge_bounds([w["bounds"] for w in current_line])
            })

        full_text = pytesseract.image_to_string(img)

        return {
            "text": full_text.strip(),
            "words": words,
            "lines": lines
        }

    def _merge_bounds(self, bounds_list: List[Dict]) -> Dict:
        """Merge multiple bounding boxes into one."""
        if not bounds_list:
            return {"x": 0, "y": 0, "width": 0, "height": 0}

        min_x = min(b["x"] for b in bounds_list)
        min_y = min(b["y"] for b in bounds_list)
        max_x = max(b["x"] + b["width"] for b in bounds_list)
        max_y = max(b["y"] + b["height"] for b in bounds_list)

        return {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y
        }


class ScreenOCR:
    """High-level OCR interface for screen content."""

    def __init__(self):
        self._engine = OCREngine()
        self._screen = get_screen()

    @property
    def available(self) -> bool:
        return self._engine.available

    async def get_screen_text(
        self,
        region: Optional[Dict[str, int]] = None,
        monitor: int = 1
    ) -> Dict[str, Any]:
        """
        Get all text visible on screen.

        Args:
            region: Optional region to limit OCR
            monitor: Monitor to capture (1=primary)

        Returns:
            OCR results with text, words, and lines
        """
        # Capture screen
        image_data, metadata = self._screen.capture(
            monitor=monitor,
            region=region,
            format="png",
            quality=100,
            scale=1.0,
            grayscale=False
        )

        # Decode base64
        import base64
        image_bytes = base64.b64decode(image_data)

        # Run OCR
        result = await self._engine.recognize_async(image_bytes)

        # Adjust coordinates if region was specified
        if region and "words" in result:
            for word in result["words"]:
                word["bounds"]["x"] += region.get("x", 0)
                word["bounds"]["y"] += region.get("y", 0)
                word["bounds"]["center_x"] += region.get("x", 0)
                word["bounds"]["center_y"] += region.get("y", 0)

        result["capture_time_ms"] = metadata.get("capture_time_ms", 0)
        return result

    async def find_text(
        self,
        text: str,
        region: Optional[Dict[str, int]] = None,
        case_sensitive: bool = False,
        partial_match: bool = True,
        return_all: bool = False
    ) -> Dict[str, Any]:
        """
        Find text on screen and return its location.

        Args:
            text: Text to find
            region: Optional region to limit search
            case_sensitive: Whether match is case-sensitive
            partial_match: Whether to match partial words
            return_all: Return all matches or just first

        Returns:
            {"found": True, "matches": [...], "best_match": {...}}
        """
        ocr_result = await self.get_screen_text(region=region)

        if "error" in ocr_result:
            return {"found": False, "error": ocr_result["error"], "matches": []}

        search_text = text if case_sensitive else text.lower()
        matches = []

        # Search in words
        for word in ocr_result.get("words", []):
            word_text = word["text"] if case_sensitive else word["text"].lower()

            if partial_match:
                if search_text in word_text:
                    matches.append(word)
            else:
                if search_text == word_text:
                    matches.append(word)

        # Also search in lines for multi-word matches
        if " " in text:
            for line in ocr_result.get("lines", []):
                line_text = line["text"] if case_sensitive else line["text"].lower()
                if search_text in line_text:
                    # Find position within line
                    idx = line_text.find(search_text)
                    if idx >= 0:
                        matches.append({
                            "text": text,
                            "bounds": line["bounds"],  # Approximate
                            "type": "line_match"
                        })

        if not return_all and len(matches) > 1:
            matches = [matches[0]]

        return {
            "found": len(matches) > 0,
            "matches": matches,
            "best_match": matches[0] if matches else None,
            "search_text": text
        }

    async def wait_for_text(
        self,
        text: str,
        condition: str = "appear",
        timeout: float = 10.0,
        poll_interval: float = 0.5,
        region: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Wait for text to appear or disappear.

        Args:
            text: Text to wait for
            condition: "appear" or "disappear"
            timeout: Max wait time in seconds
            poll_interval: Time between checks
            region: Optional region to limit search

        Returns:
            {"success": True/False, "elapsed": float, "location": {...}}
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = await self.find_text(text, region=region)
            found = result.get("found", False)

            if condition == "appear" and found:
                return {
                    "success": True,
                    "elapsed": time.time() - start_time,
                    "location": result.get("best_match")
                }
            elif condition == "disappear" and not found:
                return {
                    "success": True,
                    "elapsed": time.time() - start_time,
                    "location": None
                }

            await asyncio.sleep(poll_interval)

        return {
            "success": False,
            "elapsed": time.time() - start_time,
            "message": f"Timeout waiting for text to {condition}"
        }


# Global instance
_screen_ocr = None


def get_screen_ocr() -> ScreenOCR:
    global _screen_ocr
    if _screen_ocr is None:
        _screen_ocr = ScreenOCR()
    return _screen_ocr

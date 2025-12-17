"""
Input simulation module using pynput and uiautomation.
"""

import time
from typing import Optional, Tuple, List
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController
import uiautomation as auto


# Key name mapping
KEY_MAP = {
    # Special keys
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "escape": Key.esc,
    "esc": Key.esc,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "del": Key.delete,
    "space": Key.space,

    # Arrow keys
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,

    # Modifiers
    "ctrl": Key.ctrl,
    "control": Key.ctrl,
    "alt": Key.alt,
    "shift": Key.shift,
    "win": Key.cmd,
    "windows": Key.cmd,
    "cmd": Key.cmd,

    # Function keys
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,

    # Other
    "home": Key.home,
    "end": Key.end,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "insert": Key.insert,
    "printscreen": Key.print_screen,
    "caps": Key.caps_lock,
    "capslock": Key.caps_lock,
    "numlock": Key.num_lock,
    "scrolllock": Key.scroll_lock,
    "pause": Key.pause,
}

BUTTON_MAP = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


class InputSimulator:
    """Cross-platform input simulation."""

    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyboardController()

    def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position."""
        return self.mouse.position

    def move_mouse(self, x: int, y: int, smooth: bool = False, duration: float = 0.2):
        """Move mouse to position."""
        if smooth:
            start_x, start_y = self.mouse.position
            steps = int(duration * 60)  # 60 fps
            for i in range(steps + 1):
                t = i / steps
                # Ease in-out curve
                t = t * t * (3 - 2 * t)
                current_x = int(start_x + (x - start_x) * t)
                current_y = int(start_y + (y - start_y) * t)
                self.mouse.position = (current_x, current_y)
                time.sleep(duration / steps)
        else:
            self.mouse.position = (x, y)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        count: int = 1
    ) -> bool:
        """Click at position or current position."""
        try:
            if x is not None and y is not None:
                self.mouse.position = (x, y)
                time.sleep(0.01)  # Small delay for position to register

            btn = BUTTON_MAP.get(button, Button.left)
            self.mouse.click(btn, count)
            return True
        except Exception as e:
            return False

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Double click at position."""
        return self.click(x, y, "left", 2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Right click at position."""
        return self.click(x, y, "right", 1)

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        button: str = "left",
        duration: float = 0.3
    ) -> bool:
        """Drag from one position to another."""
        try:
            btn = BUTTON_MAP.get(button, Button.left)

            # Move to start
            self.mouse.position = (from_x, from_y)
            time.sleep(0.05)

            # Press
            self.mouse.press(btn)
            time.sleep(0.05)

            # Move smoothly to end
            self.move_mouse(to_x, to_y, smooth=True, duration=duration)

            # Release
            self.mouse.release(btn)
            return True
        except Exception as e:
            return False

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Scroll mouse wheel. Positive = up, negative = down."""
        try:
            if x is not None and y is not None:
                self.mouse.position = (x, y)
                time.sleep(0.01)

            self.mouse.scroll(0, amount)
            return True
        except Exception as e:
            return False

    def type_text(self, text: str, interval: float = 0.0) -> bool:
        """Type text character by character."""
        try:
            for char in text:
                self.keyboard.type(char)
                if interval > 0:
                    time.sleep(interval)
            return True
        except Exception as e:
            return False

    def press_key(self, key: str) -> bool:
        """Press a single key."""
        try:
            k = KEY_MAP.get(key.lower())
            if k:
                self.keyboard.press(k)
                self.keyboard.release(k)
            else:
                # Single character
                self.keyboard.press(key)
                self.keyboard.release(key)
            return True
        except Exception as e:
            return False

    def key_combo(self, *keys: str) -> bool:
        """Press key combination (e.g., Ctrl+C)."""
        try:
            # Convert all keys
            parsed_keys = []
            for key in keys:
                k = KEY_MAP.get(key.lower())
                if k:
                    parsed_keys.append(k)
                else:
                    parsed_keys.append(key)

            # Press all keys
            for k in parsed_keys:
                self.keyboard.press(k)

            # Small delay
            time.sleep(0.05)

            # Release in reverse order
            for k in reversed(parsed_keys):
                self.keyboard.release(k)

            return True
        except Exception as e:
            return False

    def send_keys(self, keys: str) -> bool:
        """
        Send keys with special key support.

        Format: "{CTRL}c" for Ctrl+C, "{ENTER}" for Enter, etc.
        Regular text is typed as-is.
        """
        try:
            # Use uiautomation's SendKeys which handles special syntax
            auto.SendKeys(keys, waitTime=0.01)
            return True
        except Exception as e:
            return False

    def hold_key(self, key: str, duration: float = 0.5) -> bool:
        """Hold a key for specified duration."""
        try:
            k = KEY_MAP.get(key.lower())
            if k:
                self.keyboard.press(k)
                time.sleep(duration)
                self.keyboard.release(k)
            else:
                self.keyboard.press(key)
                time.sleep(duration)
                self.keyboard.release(key)
            return True
        except Exception as e:
            return False


class Clipboard:
    """Clipboard operations using uiautomation."""

    @staticmethod
    def get() -> Optional[str]:
        """Get clipboard text content."""
        try:
            return auto.GetClipboardText()
        except:
            return None

    @staticmethod
    def set(text: str) -> bool:
        """Set clipboard text content."""
        try:
            auto.SetClipboardText(text)
            return True
        except:
            return False

    @staticmethod
    def clear() -> bool:
        """Clear clipboard."""
        try:
            auto.SetClipboardText("")
            return True
        except:
            return False


# Global instance
_input = None

def get_input() -> InputSimulator:
    global _input
    if _input is None:
        _input = InputSimulator()
    return _input

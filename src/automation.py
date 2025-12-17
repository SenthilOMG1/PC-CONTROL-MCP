"""
Windows UI Automation module for semantic UI interaction.

This is the KILLER FEATURE - instead of clicking coordinates,
we can interact with UI elements by name, type, and properties.

LIMITATION: UI Automation works best with native Windows apps.
For browsers (Chrome, Edge, Firefox), the internal web content is NOT
accessible via UI Automation. Use OCR-based tools (find_text_on_screen,
click_text) as fallbacks for web content.
"""

import time
from typing import Optional, List, Dict, Any, Union
import uiautomation as auto

# Import win32gui for accurate window bounds
try:
    import win32gui
    import win32con
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False

# Browser class names that don't expose internal UI
BROWSER_CLASSES = {
    "Chrome_WidgetWin_1",      # Chrome, Edge (Chromium)
    "MozillaWindowClass",       # Firefox
    "Internet Explorer_Server", # IE
    "ApplicationFrameWindow",   # UWP apps (can have issues too)
}


# Control type mapping
CONTROL_TYPES = {
    "button": auto.ButtonControl,
    "edit": auto.EditControl,
    "text": auto.TextControl,
    "checkbox": auto.CheckBoxControl,
    "radiobutton": auto.RadioButtonControl,
    "combobox": auto.ComboBoxControl,
    "list": auto.ListControl,
    "listitem": auto.ListItemControl,
    "menu": auto.MenuControl,
    "menuitem": auto.MenuItemControl,
    "tab": auto.TabControl,
    "tabitem": auto.TabItemControl,
    "tree": auto.TreeControl,
    "treeitem": auto.TreeItemControl,
    "window": auto.WindowControl,
    "pane": auto.PaneControl,
    "group": auto.GroupControl,
    "hyperlink": auto.HyperlinkControl,
    "image": auto.ImageControl,
    "document": auto.DocumentControl,
    "scrollbar": auto.ScrollBarControl,
    "slider": auto.SliderControl,
    "spinner": auto.SpinnerControl,
    "statusbar": auto.StatusBarControl,
    "toolbar": auto.ToolBarControl,
    "tooltip": auto.ToolTipControl,
    "custom": auto.CustomControl,
}


class UIElement:
    """Wrapper for UI Automation element with useful methods."""

    def __init__(self, control: auto.Control):
        self.control = control

    def to_dict(self) -> Dict[str, Any]:
        """Convert element to dictionary representation."""
        try:
            rect = self.control.BoundingRectangle
            return {
                "name": self.control.Name or "",
                "control_type": self.control.ControlTypeName,
                "automation_id": self.control.AutomationId or "",
                "class_name": self.control.ClassName or "",
                "is_enabled": self.control.IsEnabled,
                "is_visible": rect.width() > 0 and rect.height() > 0,
                "bounds": {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.width(),
                    "height": rect.height(),
                    "center_x": rect.xcenter(),
                    "center_y": rect.ycenter()
                },
                "value": self._get_value(),
                "is_keyboard_focusable": self.control.IsKeyboardFocusable,
                "has_keyboard_focus": self.control.HasKeyboardFocus,
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_value(self) -> Optional[str]:
        """Get the value/text of the element if available."""
        try:
            # Try ValuePattern first
            pattern = self.control.GetValuePattern()
            if pattern:
                return pattern.Value
        except:
            pass

        try:
            # Try TextPattern
            pattern = self.control.GetTextPattern()
            if pattern:
                return pattern.DocumentRange.GetText(-1)
        except:
            pass

        return None

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Click the element."""
        try:
            if double:
                self.control.DoubleClick()
            elif button == "right":
                self.control.RightClick()
            elif button == "middle":
                self.control.MiddleClick()
            else:
                self.control.Click()
            return True
        except Exception as e:
            # Fallback to coordinate click
            try:
                rect = self.control.BoundingRectangle
                auto.Click(rect.xcenter(), rect.ycenter())
                return True
            except:
                return False

    def type_text(self, text: str, clear_first: bool = True) -> bool:
        """Type text into the element."""
        try:
            self.control.SetFocus()
            time.sleep(0.05)

            if clear_first:
                # Select all and delete
                auto.SendKeys('{Ctrl}a{Delete}', waitTime=0.05)

            # Use SetValue if available (faster and more reliable)
            try:
                pattern = self.control.GetValuePattern()
                if pattern:
                    pattern.SetValue(text)
                    return True
            except:
                pass

            # Fallback to SendKeys
            auto.SendKeys(text, waitTime=0)
            return True
        except Exception as e:
            return False

    def get_children(self, depth: int = 1) -> List['UIElement']:
        """Get child elements."""
        children = []
        try:
            for child in self.control.GetChildren():
                children.append(UIElement(child))
                if depth > 1:
                    children.extend(
                        UIElement(child).get_children(depth - 1)
                    )
        except:
            pass
        return children


class UIAutomation:
    """Main UI Automation interface."""

    def __init__(self):
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 0.5  # 500ms cache for UI tree

    def get_desktop(self) -> UIElement:
        """Get the desktop root element."""
        return UIElement(auto.GetRootControl())

    def get_focused_element(self) -> Optional[UIElement]:
        """Get the currently focused element."""
        try:
            control = auto.GetFocusedControl()
            return UIElement(control) if control else None
        except:
            return None

    def get_foreground_window(self) -> Optional[UIElement]:
        """Get the foreground (active) window."""
        try:
            control = auto.GetForegroundControl()
            return UIElement(control) if control else None
        except:
            return None

    def find_element(
        self,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        automation_id: Optional[str] = None,
        class_name: Optional[str] = None,
        contains_text: Optional[str] = None,
        window_title: Optional[str] = None,
        timeout: float = 5.0,
        search_depth: int = 10
    ) -> Optional[UIElement]:
        """
        Find a UI element by various criteria.

        Args:
            name: Exact name match
            control_type: Type like "button", "edit", "text", etc.
            automation_id: Automation ID (most reliable)
            class_name: Window class name
            contains_text: Partial name match
            window_title: Scope search to specific window
            timeout: Max time to search (seconds)
            search_depth: How deep to search

        Returns:
            UIElement if found, None otherwise
        """
        start_time = time.time()

        # Determine search root
        if window_title:
            root = auto.WindowControl(searchDepth=1, Name=window_title)
            if not root.Exists(0):
                root = auto.WindowControl(searchDepth=1, SubName=window_title)
        else:
            root = auto.GetRootControl()

        # Build search criteria
        search_kwargs = {"searchDepth": search_depth}

        if name:
            search_kwargs["Name"] = name
        if automation_id:
            search_kwargs["AutomationId"] = automation_id
        if class_name:
            search_kwargs["ClassName"] = class_name

        # Get control class
        if control_type:
            control_class = CONTROL_TYPES.get(control_type.lower(), auto.Control)
        else:
            control_class = auto.Control

        # Search with timeout
        while time.time() - start_time < timeout:
            try:
                if contains_text and not name:
                    # Need to search and filter
                    control = control_class(searchFromControl=root, **search_kwargs)
                    if control.Exists(0.1):
                        if contains_text.lower() in (control.Name or "").lower():
                            return UIElement(control)
                else:
                    control = control_class(searchFromControl=root, **search_kwargs)
                    if control.Exists(0.1):
                        return UIElement(control)
            except Exception as e:
                pass

            time.sleep(0.1)

        return None

    def find_all_elements(
        self,
        control_type: Optional[str] = None,
        window_title: Optional[str] = None,
        search_depth: int = 5,
        max_results: int = 50
    ) -> List[UIElement]:
        """Find all elements matching criteria."""
        results = []

        # Determine search root
        if window_title:
            root = auto.WindowControl(searchDepth=1, Name=window_title)
            if not root.Exists(0):
                root = auto.WindowControl(searchDepth=1, SubName=window_title)
                if not root.Exists(0):
                    return results
        else:
            root = auto.GetForegroundControl()

        # Get control class
        if control_type:
            control_class = CONTROL_TYPES.get(control_type.lower(), auto.Control)
        else:
            control_class = auto.Control

        try:
            for control in root.GetChildren():
                self._collect_elements(
                    control, control_class, results, search_depth, max_results
                )
                if len(results) >= max_results:
                    break
        except:
            pass

        return results

    def _collect_elements(
        self,
        control: auto.Control,
        target_class: type,
        results: List[UIElement],
        depth: int,
        max_results: int
    ):
        """Recursively collect matching elements."""
        if len(results) >= max_results or depth <= 0:
            return

        try:
            if isinstance(control, target_class) or target_class == auto.Control:
                rect = control.BoundingRectangle
                if rect.width() > 0 and rect.height() > 0:  # Only visible
                    results.append(UIElement(control))

            for child in control.GetChildren():
                self._collect_elements(
                    child, target_class, results, depth - 1, max_results
                )
        except:
            pass

    def get_ui_tree(
        self,
        root: Optional[str] = None,
        depth: int = 3,
        include_invisible: bool = False
    ) -> Dict[str, Any]:
        """
        Get UI element tree structure.

        Args:
            root: Window title to start from (None = foreground window)
            depth: How deep to traverse
            include_invisible: Include zero-size elements

        Returns:
            Nested dictionary representing UI tree
        """
        if root:
            root_control = auto.WindowControl(searchDepth=1, Name=root)
            if not root_control.Exists(0):
                root_control = auto.WindowControl(searchDepth=1, SubName=root)
        else:
            root_control = auto.GetForegroundControl()

        if not root_control.Exists(0):
            return {"error": "Root element not found"}

        return self._build_tree(root_control, depth, include_invisible)

    def _build_tree(
        self,
        control: auto.Control,
        depth: int,
        include_invisible: bool
    ) -> Dict[str, Any]:
        """Build tree structure recursively."""
        try:
            rect = control.BoundingRectangle
            is_visible = rect.width() > 0 and rect.height() > 0

            if not include_invisible and not is_visible:
                return None

            node = {
                "name": control.Name or "",
                "type": control.ControlTypeName,
                "automation_id": control.AutomationId or "",
                "bounds": {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.width(),
                    "height": rect.height()
                } if is_visible else None,
                "enabled": control.IsEnabled,
                "focusable": control.IsKeyboardFocusable,
            }

            if depth > 0:
                children = []
                for child in control.GetChildren():
                    child_node = self._build_tree(
                        child, depth - 1, include_invisible
                    )
                    if child_node:
                        children.append(child_node)
                if children:
                    node["children"] = children

            return node
        except Exception as e:
            return {"error": str(e)}

    def get_windows(self) -> List[Dict[str, Any]]:
        """Get list of all top-level windows with accurate bounds."""
        windows = []

        if HAS_WIN32GUI:
            # Use win32gui for accurate window enumeration and bounds
            def enum_handler(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:  # Only include windows with titles
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            class_name = win32gui.GetClassName(hwnd)
                            # Get process ID
                            import ctypes
                            pid = ctypes.c_ulong()
                            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                            results.append({
                                "title": title,
                                "class_name": class_name,
                                "hwnd": hwnd,
                                "process_id": pid.value,
                                "is_browser": class_name in BROWSER_CLASSES,
                                "bounds": {
                                    "x": rect[0],
                                    "y": rect[1],
                                    "width": rect[2] - rect[0],
                                    "height": rect[3] - rect[1]
                                }
                            })
                        except:
                            pass
                return True

            win32gui.EnumWindows(enum_handler, windows)
        else:
            # Fallback to UI Automation
            try:
                for win in auto.GetRootControl().GetChildren():
                    if win.ControlTypeName == "WindowControl":
                        try:
                            rect = win.BoundingRectangle
                            class_name = win.ClassName or ""
                            windows.append({
                                "title": win.Name or "",
                                "class_name": class_name,
                                "automation_id": win.AutomationId or "",
                                "process_id": win.ProcessId,
                                "is_enabled": win.IsEnabled,
                                "is_browser": class_name in BROWSER_CLASSES,
                                "bounds": {
                                    "x": rect.left,
                                    "y": rect.top,
                                    "width": rect.width(),
                                    "height": rect.height()
                                }
                            })
                        except:
                            pass
            except:
                pass

        return windows

    def focus_window(self, title: str) -> Dict[str, Any]:
        """Bring a window to the foreground by title (partial match)."""
        if HAS_WIN32GUI:
            result = {"success": False}

            def enum_handler(hwnd, data):
                if win32gui.IsWindowVisible(hwnd):
                    window_title = win32gui.GetWindowText(hwnd)
                    if title.lower() in window_title.lower():
                        try:
                            # Restore if minimized
                            if win32gui.IsIconic(hwnd):
                                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            # Bring to front
                            win32gui.SetForegroundWindow(hwnd)
                            data["success"] = True
                            data["title"] = window_title
                            data["hwnd"] = hwnd
                            return False  # Stop enumeration
                        except Exception as e:
                            data["error"] = str(e)
                return True

            win32gui.EnumWindows(enum_handler, result)
            return result
        else:
            # Fallback to UI Automation
            window = auto.WindowControl(searchDepth=1, SubName=title)
            if window.Exists(1):
                window.SetFocus()
                return {"success": True, "title": window.Name}
            return {"success": False, "error": "Window not found"}

    def wait_for_element(
        self,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        automation_id: Optional[str] = None,
        condition: str = "appear",  # appear, disappear, enabled
        timeout: float = 10.0,
        poll_interval: float = 0.2
    ) -> Union[UIElement, bool]:
        """
        Wait for element to meet condition.

        Args:
            condition: "appear", "disappear", "enabled", "focused"

        Returns:
            UIElement if appear/enabled/focused, True if disappear succeeded, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            element = self.find_element(
                name=name,
                control_type=control_type,
                automation_id=automation_id,
                timeout=0.1
            )

            if condition == "appear":
                if element:
                    return element
            elif condition == "disappear":
                if not element:
                    return True
            elif condition == "enabled":
                if element and element.control.IsEnabled:
                    return element
            elif condition == "focused":
                if element and element.control.HasKeyboardFocus:
                    return element

            time.sleep(poll_interval)

        return False


# Global instance
_automation = None

def get_automation() -> UIAutomation:
    global _automation
    if _automation is None:
        _automation = UIAutomation()
    return _automation

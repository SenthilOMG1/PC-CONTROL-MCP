"""
Claude PC Control MCP Server

A powerful MCP server for semantic PC control using:
- Windows UI Automation (interact by element name/type)
- Fast screen capture (Desktop Duplication API)
- Input simulation (mouse, keyboard)

This enables Claude to control the PC intelligently by understanding
the actual UI structure, not just raw pixels.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    CallToolResult,
)

from screen import get_screen
from automation import get_automation, UIAutomation, BROWSER_CLASSES
from input import get_input, Clipboard

# Import new modules
try:
    from ocr import get_screen_ocr
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from vision import get_screen_vision
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claude-pc-mcp")

# Create MCP server
server = Server("claude-pc-mcp")


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        # Screen capture tools
        Tool(
            name="capture_screen",
            description="""Capture screenshot of the screen or a region.

MUCH faster than the default pc-control screenshot.
Uses Windows Desktop Duplication API (GPU accelerated).

Returns: Base64 encoded image + metadata (dimensions, capture time)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "integer",
                        "description": "Monitor index (0=all, 1=primary, 2+=others)",
                        "default": 1
                    },
                    "region": {
                        "type": "object",
                        "description": "Capture specific region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    },
                    "format": {
                        "type": "string",
                        "enum": ["jpeg", "png"],
                        "default": "jpeg"
                    },
                    "quality": {
                        "type": "integer",
                        "description": "JPEG quality (1-100)",
                        "default": 80
                    },
                    "scale": {
                        "type": "number",
                        "description": "Scale factor (0.5 = half size)",
                        "default": 1.0
                    },
                    "grayscale": {
                        "type": "boolean",
                        "description": "Convert to grayscale",
                        "default": False
                    }
                }
            }
        ),

        Tool(
            name="get_monitors",
            description="Get list of available monitors with their dimensions.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # UI Automation tools (THE KILLER FEATURES)
        Tool(
            name="find_element",
            description="""Find a UI element by name, type, or other properties.

This is MUCH better than coordinate clicking! You can find elements by:
- name: Button text, label text, window title
- control_type: button, edit, text, checkbox, combobox, list, menu, etc.
- automation_id: Unique ID (most reliable for apps that set it)
- contains_text: Partial name match

Returns element info including EXACT clickable coordinates.

Example: find_element(name="Submit", control_type="button")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact element name/text"
                    },
                    "control_type": {
                        "type": "string",
                        "description": "Element type: button, edit, text, checkbox, combobox, list, listitem, menu, menuitem, tab, tabitem, tree, treeitem, window, pane, hyperlink, etc.",
                        "enum": ["button", "edit", "text", "checkbox", "radiobutton", "combobox", "list", "listitem", "menu", "menuitem", "tab", "tabitem", "tree", "treeitem", "window", "pane", "group", "hyperlink", "image", "document", "scrollbar", "slider", "spinner", "statusbar", "toolbar", "tooltip", "custom"]
                    },
                    "automation_id": {
                        "type": "string",
                        "description": "Automation ID (most reliable)"
                    },
                    "class_name": {
                        "type": "string",
                        "description": "Window class name"
                    },
                    "contains_text": {
                        "type": "string",
                        "description": "Partial name match"
                    },
                    "window_title": {
                        "type": "string",
                        "description": "Scope search to specific window"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Search timeout in seconds",
                        "default": 5.0
                    }
                }
            }
        ),

        Tool(
            name="click_element",
            description="""Click a UI element by name/type (NOT coordinates!).

This is the PREFERRED way to click - much more reliable than coordinates.

Example: click_element(name="OK", control_type="button")
Example: click_element(name="File", control_type="menuitem")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Element name/text"},
                    "control_type": {"type": "string", "description": "Element type"},
                    "automation_id": {"type": "string", "description": "Automation ID"},
                    "contains_text": {"type": "string", "description": "Partial name match"},
                    "window_title": {"type": "string", "description": "Scope to window"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left"
                    },
                    "double": {
                        "type": "boolean",
                        "description": "Double click",
                        "default": False
                    }
                }
            }
        ),

        Tool(
            name="type_into_element",
            description="""Type text into a UI element (text field, search box, etc.).

Automatically finds the element, focuses it, and types.

Example: type_into_element(name="Search", text="hello world")
Example: type_into_element(control_type="edit", text="username")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Element name"},
                    "control_type": {"type": "string", "description": "Element type (usually 'edit')"},
                    "automation_id": {"type": "string", "description": "Automation ID"},
                    "window_title": {"type": "string", "description": "Scope to window"},
                    "text": {"type": "string", "description": "Text to type"},
                    "clear_first": {
                        "type": "boolean",
                        "description": "Clear existing text first",
                        "default": True
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Press Enter after typing",
                        "default": False
                    }
                },
                "required": ["text"]
            }
        ),

        Tool(
            name="get_ui_tree",
            description="""Get the UI element tree structure.

Returns a hierarchical view of all UI elements in the current window.
Useful for understanding what elements are available to interact with.

Much better than screenshots for understanding UI structure!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "window_title": {
                        "type": "string",
                        "description": "Window to inspect (default: foreground)"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Tree depth (1-10)",
                        "default": 3
                    },
                    "include_invisible": {
                        "type": "boolean",
                        "description": "Include hidden elements",
                        "default": False
                    }
                }
            }
        ),

        Tool(
            name="get_focused_element",
            description="Get information about the currently focused UI element.",
            inputSchema={"type": "object", "properties": {}}
        ),

        Tool(
            name="get_windows",
            description="Get list of all open windows with their titles and bounds.",
            inputSchema={"type": "object", "properties": {}}
        ),

        Tool(
            name="wait_for_element",
            description="""Wait for a UI element to appear, disappear, or become enabled.

Useful for:
- Waiting for dialogs to appear
- Waiting for loading indicators to disappear
- Waiting for buttons to become enabled

Example: wait_for_element(name="Loading...", condition="disappear")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Element name"},
                    "control_type": {"type": "string", "description": "Element type"},
                    "automation_id": {"type": "string", "description": "Automation ID"},
                    "condition": {
                        "type": "string",
                        "enum": ["appear", "disappear", "enabled", "focused"],
                        "default": "appear"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds",
                        "default": 10.0
                    }
                }
            }
        ),

        Tool(
            name="find_all_elements",
            description="""Find all UI elements of a type.

Returns list of all matching elements with their bounds.
Useful for getting all buttons, all list items, etc.

Example: find_all_elements(control_type="button")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "control_type": {"type": "string", "description": "Element type to find"},
                    "window_title": {"type": "string", "description": "Scope to window"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 50
                    }
                }
            }
        ),

        # Input simulation tools
        Tool(
            name="click_at",
            description="Click at specific screen coordinates (fallback when element not found).",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left"
                    },
                    "double": {"type": "boolean", "default": False}
                },
                "required": ["x", "y"]
            }
        ),

        Tool(
            name="type_text",
            description="Type text at current cursor position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        ),

        Tool(
            name="send_keys",
            description="""Send keyboard input with special key support.

Format: {KEY} for special keys
Examples:
- "{ENTER}" - Press Enter
- "{CTRL}c" - Ctrl+C
- "{ALT}{F4}" - Alt+F4
- "{SHIFT}hello" - HELLO (shifted)
- "hello{ENTER}" - Type hello then Enter""",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Keys to send"}
                },
                "required": ["keys"]
            }
        ),

        Tool(
            name="key_combo",
            description="""Press a keyboard shortcut.

Example: key_combo(["ctrl", "c"]) for Ctrl+C
Example: key_combo(["alt", "tab"]) for Alt+Tab""",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keys to press together"
                    }
                },
                "required": ["keys"]
            }
        ),

        Tool(
            name="scroll",
            description="Scroll mouse wheel at current or specified position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "integer",
                        "description": "Scroll amount (positive=up, negative=down)"
                    },
                    "x": {"type": "integer", "description": "X coordinate (optional)"},
                    "y": {"type": "integer", "description": "Y coordinate (optional)"}
                },
                "required": ["amount"]
            }
        ),

        Tool(
            name="drag",
            description="Drag from one position to another.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_x": {"type": "integer"},
                    "from_y": {"type": "integer"},
                    "to_x": {"type": "integer"},
                    "to_y": {"type": "integer"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left"
                    }
                },
                "required": ["from_x", "from_y", "to_x", "to_y"]
            }
        ),

        Tool(
            name="get_mouse_position",
            description="Get current mouse cursor position.",
            inputSchema={"type": "object", "properties": {}}
        ),

        Tool(
            name="move_mouse",
            description="Move mouse to position.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "smooth": {
                        "type": "boolean",
                        "description": "Animate movement",
                        "default": False
                    }
                },
                "required": ["x", "y"]
            }
        ),

        # Clipboard tools
        Tool(
            name="get_clipboard",
            description="Get current clipboard text content.",
            inputSchema={"type": "object", "properties": {}}
        ),

        Tool(
            name="set_clipboard",
            description="Set clipboard text content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy"}
                },
                "required": ["text"]
            }
        ),

        # Window tools
        Tool(
            name="focus_window",
            description="Bring a window to foreground by title.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title (partial match)"}
                },
                "required": ["title"]
            }
        ),

        # =================================================================
        # OCR TOOLS - For finding/clicking text (works with browsers!)
        # =================================================================
        Tool(
            name="find_text_on_screen",
            description="""Find text on screen using OCR and return its location.

THIS WORKS WITH BROWSERS! Unlike UI Automation, OCR can find any visible text.

Uses Windows built-in OCR (fast, GPU-accelerated).

Example: find_text_on_screen(text="Submit")
Returns: coordinates you can click with click_at()""",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to find"},
                    "region": {
                        "type": "object",
                        "description": "Limit search to region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    },
                    "case_sensitive": {"type": "boolean", "default": False},
                    "return_all": {
                        "type": "boolean",
                        "description": "Return all matches",
                        "default": False
                    }
                },
                "required": ["text"]
            }
        ),

        Tool(
            name="click_text",
            description="""Find text on screen and click it - single tool call!

THIS WORKS WITH BROWSERS! Perfect for clicking buttons, links, etc.

Example: click_text(text="Sign In")
Example: click_text(text="Submit", button="left")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to find and click"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "default": "left"
                    },
                    "double": {"type": "boolean", "default": False},
                    "region": {
                        "type": "object",
                        "description": "Limit search to region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    }
                },
                "required": ["text"]
            }
        ),

        Tool(
            name="get_screen_text",
            description="""Extract ALL visible text from screen with positions.

Returns every word/line visible on screen with their coordinates.
Great for understanding what's on screen without screenshots.

Works with any application including browsers!""",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "Limit to specific region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    }
                }
            }
        ),

        Tool(
            name="wait_for_text",
            description="""Wait for text to appear or disappear on screen.

Uses OCR to detect text changes. Works with browsers!

Example: wait_for_text(text="Loading", condition="disappear")
Example: wait_for_text(text="Success", timeout=30)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to wait for"},
                    "condition": {
                        "type": "string",
                        "enum": ["appear", "disappear"],
                        "default": "appear"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds",
                        "default": 10.0
                    },
                    "region": {
                        "type": "object",
                        "description": "Limit search to region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    }
                },
                "required": ["text"]
            }
        ),

        # =================================================================
        # VISION TOOLS - Image matching and screen change detection
        # =================================================================
        Tool(
            name="find_image_on_screen",
            description="""Find an image/icon on screen using template matching.

Useful for finding buttons, icons, or UI elements by their appearance.
Provide a base64 encoded template image to search for.

Returns location with confidence score.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "description": "Base64 encoded template image"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Match confidence threshold (0-1)",
                        "default": 0.8
                    },
                    "region": {
                        "type": "object",
                        "description": "Limit search to region",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    },
                    "grayscale": {
                        "type": "boolean",
                        "description": "Convert to grayscale (faster)",
                        "default": True
                    }
                },
                "required": ["template"]
            }
        ),

        Tool(
            name="wait_for_screen_change",
            description="""Wait for the screen to change.

Monitors a region and returns when significant change is detected.
Great for waiting after clicking something.

Example: wait_for_screen_change(timeout=5)
Example: wait_for_screen_change(region={...}, threshold=0.05)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "Region to monitor",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"}
                        }
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds",
                        "default": 10.0
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Change threshold (0-1)",
                        "default": 0.02
                    },
                    "poll_interval": {
                        "type": "number",
                        "description": "Check interval in seconds",
                        "default": 0.1
                    }
                }
            }
        ),
    ]


# =============================================================================
# TOOL HANDLERS
# =============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    """Handle tool calls."""

    try:
        result = await _execute_tool(name, arguments)
        return _format_result(result, name)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def _execute_tool(name: str, args: dict) -> Any:
    """Execute tool and return result."""

    screen = get_screen()
    automation = get_automation()
    input_sim = get_input()

    # Screen tools
    if name == "capture_screen":
        image_data, metadata = screen.capture(
            monitor=args.get("monitor", 1),
            region=args.get("region"),
            format=args.get("format", "jpeg"),
            quality=args.get("quality", 80),
            scale=args.get("scale", 1.0),
            grayscale=args.get("grayscale", False)
        )
        return {"image": image_data, "metadata": metadata}

    elif name == "get_monitors":
        return {"monitors": screen.get_monitors()}

    # UI Automation tools
    elif name == "find_element":
        element = automation.find_element(
            name=args.get("name"),
            control_type=args.get("control_type"),
            automation_id=args.get("automation_id"),
            class_name=args.get("class_name"),
            contains_text=args.get("contains_text"),
            window_title=args.get("window_title"),
            timeout=args.get("timeout", 5.0)
        )
        if element:
            return {"found": True, "element": element.to_dict()}
        return {"found": False, "message": "Element not found"}

    elif name == "click_element":
        element = automation.find_element(
            name=args.get("name"),
            control_type=args.get("control_type"),
            automation_id=args.get("automation_id"),
            contains_text=args.get("contains_text"),
            window_title=args.get("window_title"),
            timeout=5.0
        )
        if element:
            success = element.click(
                button=args.get("button", "left"),
                double=args.get("double", False)
            )
            return {
                "success": success,
                "element": element.to_dict()
            }
        return {"success": False, "error": "Element not found"}

    elif name == "type_into_element":
        element = automation.find_element(
            name=args.get("name"),
            control_type=args.get("control_type"),
            automation_id=args.get("automation_id"),
            window_title=args.get("window_title"),
            timeout=5.0
        )
        if element:
            success = element.type_text(
                args["text"],
                clear_first=args.get("clear_first", True)
            )
            if args.get("press_enter"):
                input_sim.press_key("enter")
            return {"success": success, "element": element.to_dict()}
        return {"success": False, "error": "Element not found"}

    elif name == "get_ui_tree":
        tree = automation.get_ui_tree(
            root=args.get("window_title"),
            depth=args.get("depth", 3),
            include_invisible=args.get("include_invisible", False)
        )
        return {"tree": tree}

    elif name == "get_focused_element":
        element = automation.get_focused_element()
        if element:
            return {"element": element.to_dict()}
        return {"element": None}

    elif name == "get_windows":
        windows = automation.get_windows()
        return {"windows": windows}

    elif name == "wait_for_element":
        result = automation.wait_for_element(
            name=args.get("name"),
            control_type=args.get("control_type"),
            automation_id=args.get("automation_id"),
            condition=args.get("condition", "appear"),
            timeout=args.get("timeout", 10.0)
        )
        if result is False:
            return {"success": False, "message": "Timeout waiting for condition"}
        elif result is True:
            return {"success": True, "message": "Condition met (element disappeared)"}
        else:
            return {"success": True, "element": result.to_dict()}

    elif name == "find_all_elements":
        elements = automation.find_all_elements(
            control_type=args.get("control_type"),
            window_title=args.get("window_title"),
            max_results=args.get("max_results", 50)
        )
        return {
            "count": len(elements),
            "elements": [e.to_dict() for e in elements]
        }

    # Input tools
    elif name == "click_at":
        count = 2 if args.get("double") else 1
        success = input_sim.click(
            args["x"], args["y"],
            button=args.get("button", "left"),
            count=count
        )
        return {"success": success}

    elif name == "type_text":
        success = input_sim.type_text(args["text"])
        return {"success": success}

    elif name == "send_keys":
        success = input_sim.send_keys(args["keys"])
        return {"success": success}

    elif name == "key_combo":
        success = input_sim.key_combo(*args["keys"])
        return {"success": success}

    elif name == "scroll":
        success = input_sim.scroll(
            args["amount"],
            x=args.get("x"),
            y=args.get("y")
        )
        return {"success": success}

    elif name == "drag":
        success = input_sim.drag(
            args["from_x"], args["from_y"],
            args["to_x"], args["to_y"],
            button=args.get("button", "left")
        )
        return {"success": success}

    elif name == "get_mouse_position":
        x, y = input_sim.get_mouse_position()
        return {"x": x, "y": y}

    elif name == "move_mouse":
        input_sim.move_mouse(
            args["x"], args["y"],
            smooth=args.get("smooth", False)
        )
        return {"success": True}

    # Clipboard tools
    elif name == "get_clipboard":
        text = Clipboard.get()
        return {"text": text}

    elif name == "set_clipboard":
        success = Clipboard.set(args["text"])
        return {"success": success}

    # Window tools
    elif name == "focus_window":
        result = automation.focus_window(args["title"])
        return result

    # =================================================================
    # OCR TOOLS
    # =================================================================
    elif name == "find_text_on_screen":
        if not HAS_OCR:
            return {"error": "OCR module not available. Install winrt or pytesseract."}
        ocr = get_screen_ocr()
        result = await ocr.find_text(
            text=args["text"],
            region=args.get("region"),
            case_sensitive=args.get("case_sensitive", False),
            return_all=args.get("return_all", False)
        )
        return result

    elif name == "click_text":
        if not HAS_OCR:
            return {"error": "OCR module not available. Install winrt or pytesseract."}
        ocr = get_screen_ocr()
        result = await ocr.find_text(
            text=args["text"],
            region=args.get("region"),
            case_sensitive=False
        )
        if result.get("found") and result.get("best_match"):
            match = result["best_match"]
            x = match["bounds"].get("center_x", match["bounds"]["x"] + match["bounds"]["width"] // 2)
            y = match["bounds"].get("center_y", match["bounds"]["y"] + match["bounds"]["height"] // 2)

            count = 2 if args.get("double") else 1
            click_success = input_sim.click(x, y, button=args.get("button", "left"), count=count)

            return {
                "success": click_success,
                "clicked_at": {"x": x, "y": y},
                "matched_text": match.get("text", args["text"])
            }
        return {"success": False, "error": f"Text '{args['text']}' not found on screen"}

    elif name == "get_screen_text":
        if not HAS_OCR:
            return {"error": "OCR module not available. Install winrt or pytesseract."}
        ocr = get_screen_ocr()
        result = await ocr.get_screen_text(region=args.get("region"))
        return result

    elif name == "wait_for_text":
        if not HAS_OCR:
            return {"error": "OCR module not available. Install winrt or pytesseract."}
        ocr = get_screen_ocr()
        result = await ocr.wait_for_text(
            text=args["text"],
            condition=args.get("condition", "appear"),
            timeout=args.get("timeout", 10.0),
            region=args.get("region")
        )
        return result

    # =================================================================
    # VISION TOOLS
    # =================================================================
    elif name == "find_image_on_screen":
        if not HAS_VISION:
            return {"error": "Vision module not available. Install opencv-python."}
        vision = get_screen_vision()
        result = vision.find_image_on_screen(
            template_data=args["template"],
            region=args.get("region"),
            threshold=args.get("threshold", 0.8),
            grayscale=args.get("grayscale", True)
        )
        return result

    elif name == "wait_for_screen_change":
        if not HAS_VISION:
            return {"error": "Vision module not available. Install opencv-python."}
        vision = get_screen_vision()
        result = await vision.wait_for_screen_change(
            region=args.get("region"),
            timeout=args.get("timeout", 10.0),
            threshold=args.get("threshold", 0.02),
            poll_interval=args.get("poll_interval", 0.1)
        )
        return result

    else:
        return {"error": f"Unknown tool: {name}"}


def _format_result(result: Any, tool_name: str) -> list[TextContent | ImageContent]:
    """Format tool result for MCP response."""

    # Handle screenshot results specially
    if tool_name == "capture_screen" and "image" in result:
        image_data = result.pop("image")
        metadata = result.get("metadata", {})

        return [
            ImageContent(
                type="image",
                data=image_data,
                mimeType=f"image/{metadata.get('format', 'jpeg')}"
            ),
            TextContent(
                type="text",
                text=f"Screenshot captured: {metadata.get('width')}x{metadata.get('height')} "
                     f"in {metadata.get('capture_time_ms')}ms ({metadata.get('size_bytes')} bytes)"
            )
        ]

    # Default JSON formatting
    return [TextContent(
        type="text",
        text=json.dumps(result, indent=2, default=str)
    )]


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================

async def main():
    """Run the MCP server."""
    logger.info("Starting Claude PC Control MCP Server...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

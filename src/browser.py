"""
Chrome DevTools Protocol (CDP) module for browser automation.

This is the KEY UPGRADE - direct access to Chrome's internals!
Unlike UI Automation which can't see browser content, CDP provides:
- Full DOM tree access
- Accessibility tree (all interactive elements)
- JavaScript execution
- CSS/computed styles
- Network interception
- Element bounds for clicking

Requirements:
- Chrome must be started with: --remote-debugging-port=9222
- Or use the connect_browser tool to launch Chrome with debugging

Usage:
    browser = get_browser()
    await browser.connect()
    elements = await browser.get_interactive_elements()
"""

import asyncio
import json
import logging
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import websockets
import aiohttp

logger = logging.getLogger("claude-pc-mcp.browser")

# Default CDP port
DEFAULT_CDP_PORT = 9222


@dataclass
class BrowserElement:
    """Represents an interactive element in the browser."""
    node_id: int
    backend_node_id: int
    name: str
    role: str
    value: str = ""
    description: str = ""
    bounds: Dict[str, int] = field(default_factory=dict)
    attributes: Dict[str, str] = field(default_factory=dict)
    selector: str = ""
    xpath: str = ""
    is_enabled: bool = True
    is_visible: bool = True
    is_focused: bool = False
    children_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "backend_node_id": self.backend_node_id,
            "name": self.name,
            "role": self.role,
            "value": self.value,
            "description": self.description,
            "bounds": self.bounds,
            "attributes": self.attributes,
            "selector": self.selector,
            "xpath": self.xpath,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
            "is_focused": self.is_focused,
            "children_count": self.children_count,
        }


@dataclass
class PageInfo:
    """Information about a browser page/tab."""
    id: str
    url: str
    title: str
    type: str
    websocket_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "type": self.type,
        }


class CDPConnection:
    """Low-level CDP WebSocket connection."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._message_id = 0
        self._pending_messages: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[callable]] = {}
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """Connect to CDP WebSocket."""
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                max_size=100 * 1024 * 1024,  # 100MB for large DOMs
                ping_interval=30,
                ping_timeout=10,
            )
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info(f"Connected to CDP: {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CDP: {e}")
            return False

    async def disconnect(self):
        """Disconnect from CDP."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def send(self, method: str, params: Dict = None) -> Dict:
        """Send CDP command and wait for response."""
        if not self.ws:
            raise ConnectionError("Not connected to CDP")

        self._message_id += 1
        msg_id = self._message_id

        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }

        future = asyncio.get_event_loop().create_future()
        self._pending_messages[msg_id] = future

        await self.ws.send(json.dumps(message))

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            del self._pending_messages[msg_id]
            raise TimeoutError(f"CDP command timed out: {method}")

    async def _receive_loop(self):
        """Background task to receive CDP messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)

                if "id" in data:
                    # Response to a command
                    msg_id = data["id"]
                    if msg_id in self._pending_messages:
                        future = self._pending_messages.pop(msg_id)
                        if "error" in data:
                            future.set_exception(Exception(data["error"].get("message", "Unknown error")))
                        else:
                            future.set_result(data.get("result", {}))

                elif "method" in data:
                    # Event
                    method = data["method"]
                    if method in self._event_handlers:
                        for handler in self._event_handlers[method]:
                            try:
                                handler(data.get("params", {}))
                            except Exception as e:
                                logger.error(f"Event handler error: {e}")
        except websockets.ConnectionClosed:
            logger.info("CDP connection closed")
        except Exception as e:
            logger.error(f"CDP receive error: {e}")

    def on_event(self, method: str, handler: callable):
        """Register event handler."""
        if method not in self._event_handlers:
            self._event_handlers[method] = []
        self._event_handlers[method].append(handler)


class BrowserAutomation:
    """High-level browser automation via CDP."""

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self.port = port
        self.connection: Optional[CDPConnection] = None
        self.current_page: Optional[PageInfo] = None
        self._dom_enabled = False
        self._accessibility_enabled = False

    async def connect(self, target_url: str = None) -> Dict[str, Any]:
        """
        Connect to Chrome browser with remote debugging.

        Args:
            target_url: Optional URL to find specific tab

        Returns:
            Connection status and page info
        """
        try:
            # Get list of available pages
            pages = await self.get_pages()

            if not pages:
                return {
                    "success": False,
                    "error": "No browser pages found. Make sure Chrome is running with --remote-debugging-port=9222"
                }

            # Find target page
            target_page = None
            if target_url:
                for page in pages:
                    if target_url.lower() in page.url.lower():
                        target_page = page
                        break

            if not target_page:
                # Use first available page
                for page in pages:
                    if page.type == "page":
                        target_page = page
                        break

            if not target_page:
                return {"success": False, "error": "No suitable page found"}

            # Connect to the page
            self.connection = CDPConnection(target_page.websocket_url)
            if not await self.connection.connect():
                return {"success": False, "error": "Failed to establish WebSocket connection"}

            self.current_page = target_page

            # Enable required CDP domains
            await self.connection.send("DOM.enable")
            await self.connection.send("Accessibility.enable")
            await self.connection.send("Runtime.enable")
            await self.connection.send("Page.enable")

            self._dom_enabled = True
            self._accessibility_enabled = True

            return {
                "success": True,
                "page": target_page.to_dict(),
                "message": f"Connected to: {target_page.title}"
            }

        except Exception as e:
            logger.exception("Failed to connect to browser")
            return {"success": False, "error": str(e)}

    async def disconnect(self):
        """Disconnect from browser."""
        if self.connection:
            await self.connection.disconnect()
            self.connection = None
            self.current_page = None

    async def get_pages(self) -> List[PageInfo]:
        """Get list of all browser pages/tabs."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{self.port}/json") as resp:
                    data = await resp.json()

            pages = []
            for item in data:
                if item.get("type") in ("page", "background_page"):
                    pages.append(PageInfo(
                        id=item.get("id", ""),
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        type=item.get("type", ""),
                        websocket_url=item.get("webSocketDebuggerUrl", "")
                    ))
            return pages
        except Exception as e:
            logger.error(f"Failed to get pages: {e}")
            return []

    async def get_interactive_elements(self) -> List[BrowserElement]:
        """
        Get all interactive elements on the page via accessibility tree.

        This is THE KEY FEATURE - returns every clickable/interactive element
        with its exact bounds, name, role, and properties.
        """
        if not self.connection:
            raise ConnectionError("Not connected to browser")

        try:
            # Get the full accessibility tree
            result = await self.connection.send("Accessibility.getFullAXTree")
            nodes = result.get("nodes", [])

            elements = []

            # Interactive roles we care about
            interactive_roles = {
                "button", "link", "textbox", "checkbox", "radio",
                "combobox", "listbox", "option", "menuitem", "menu",
                "tab", "switch", "slider", "spinbutton", "searchbox",
                "textfield", "menubar", "menuitemcheckbox", "menuitemradio",
                "treeitem", "gridcell", "rowheader", "columnheader"
            }

            for node in nodes:
                role = node.get("role", {}).get("value", "").lower()

                # Check if interactive
                is_interactive = (
                    role in interactive_roles or
                    node.get("focusable", {}).get("value", False) or
                    "clickable" in str(node.get("properties", []))
                )

                if not is_interactive:
                    continue

                # Get name
                name = node.get("name", {}).get("value", "")
                if not name:
                    # Try to get from properties
                    for prop in node.get("properties", []):
                        if prop.get("name") == "name":
                            name = prop.get("value", {}).get("value", "")
                            break

                # Get bounds
                bounds = {}
                backend_node_id = node.get("backendDOMNodeId", 0)
                if backend_node_id:
                    try:
                        box_result = await self.connection.send(
                            "DOM.getBoxModel",
                            {"backendNodeId": backend_node_id}
                        )
                        model = box_result.get("model", {})
                        content = model.get("content", [])
                        if len(content) >= 8:
                            x = min(content[0], content[2], content[4], content[6])
                            y = min(content[1], content[3], content[5], content[7])
                            x2 = max(content[0], content[2], content[4], content[6])
                            y2 = max(content[1], content[3], content[5], content[7])
                            bounds = {
                                "x": int(x),
                                "y": int(y),
                                "width": int(x2 - x),
                                "height": int(y2 - y),
                                "center_x": int((x + x2) / 2),
                                "center_y": int((y + y2) / 2)
                            }
                    except:
                        pass

                # Skip elements without valid bounds
                if not bounds or bounds.get("width", 0) <= 0:
                    continue

                # Get value
                value = node.get("value", {}).get("value", "")

                # Get description
                description = node.get("description", {}).get("value", "")

                # Check states
                is_enabled = True
                is_focused = False
                for prop in node.get("properties", []):
                    prop_name = prop.get("name", "")
                    prop_value = prop.get("value", {}).get("value", False)
                    if prop_name == "disabled":
                        is_enabled = not prop_value
                    elif prop_name == "focused":
                        is_focused = prop_value

                element = BrowserElement(
                    node_id=node.get("nodeId", 0),
                    backend_node_id=backend_node_id,
                    name=name,
                    role=role,
                    value=value,
                    description=description,
                    bounds=bounds,
                    is_enabled=is_enabled,
                    is_visible=True,
                    is_focused=is_focused,
                    children_count=len(node.get("childIds", []))
                )

                elements.append(element)

            return elements

        except Exception as e:
            logger.exception("Failed to get interactive elements")
            raise

    async def find_element(
        self,
        text: str = None,
        role: str = None,
        selector: str = None,
        contains: str = None,
        exact: bool = False
    ) -> Optional[BrowserElement]:
        """
        Find a specific element by various criteria.

        Args:
            text: Element name/text (exact or partial match)
            role: Element role (button, link, textbox, etc.)
            selector: CSS selector
            contains: Text the element contains
            exact: Require exact text match

        Returns:
            BrowserElement if found, None otherwise
        """
        # If using CSS selector, use DOM methods
        if selector:
            return await self._find_by_selector(selector)

        # Otherwise search accessibility tree
        elements = await self.get_interactive_elements()

        for element in elements:
            # Check role
            if role and element.role.lower() != role.lower():
                continue

            # Check text/name
            if text:
                if exact:
                    if element.name != text:
                        continue
                else:
                    if text.lower() not in element.name.lower():
                        continue

            # Check contains
            if contains:
                element_text = f"{element.name} {element.value} {element.description}".lower()
                if contains.lower() not in element_text:
                    continue

            return element

        return None

    async def _find_by_selector(self, selector: str) -> Optional[BrowserElement]:
        """Find element by CSS selector."""
        try:
            # Get document
            doc_result = await self.connection.send("DOM.getDocument")
            root_id = doc_result.get("root", {}).get("nodeId", 0)

            # Query selector
            result = await self.connection.send(
                "DOM.querySelector",
                {"nodeId": root_id, "selector": selector}
            )
            node_id = result.get("nodeId", 0)

            if not node_id:
                return None

            # Get node details
            node_result = await self.connection.send(
                "DOM.describeNode",
                {"nodeId": node_id}
            )
            node = node_result.get("node", {})

            # Get bounds
            try:
                box_result = await self.connection.send(
                    "DOM.getBoxModel",
                    {"nodeId": node_id}
                )
                model = box_result.get("model", {})
                content = model.get("content", [])
                if len(content) >= 8:
                    x = min(content[0], content[2], content[4], content[6])
                    y = min(content[1], content[3], content[5], content[7])
                    x2 = max(content[0], content[2], content[4], content[6])
                    y2 = max(content[1], content[3], content[5], content[7])
                    bounds = {
                        "x": int(x),
                        "y": int(y),
                        "width": int(x2 - x),
                        "height": int(y2 - y),
                        "center_x": int((x + x2) / 2),
                        "center_y": int((y + y2) / 2)
                    }
                else:
                    bounds = {}
            except:
                bounds = {}

            return BrowserElement(
                node_id=node_id,
                backend_node_id=node.get("backendNodeId", 0),
                name=node.get("nodeName", ""),
                role=node.get("nodeName", "").lower(),
                bounds=bounds,
                selector=selector,
            )

        except Exception as e:
            logger.error(f"Failed to find by selector: {e}")
            return None

    async def click_element(
        self,
        element: BrowserElement = None,
        text: str = None,
        role: str = None,
        selector: str = None,
        button: str = "left",
        click_count: int = 1
    ) -> Dict[str, Any]:
        """
        Click an element.

        Can provide element directly or search criteria.
        """
        if not element:
            element = await self.find_element(text=text, role=role, selector=selector)

        if not element:
            return {"success": False, "error": "Element not found"}

        if not element.bounds:
            return {"success": False, "error": "Element has no bounds"}

        x = element.bounds.get("center_x", 0)
        y = element.bounds.get("center_y", 0)

        # Dispatch mouse events
        try:
            # Move mouse
            await self.connection.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x,
                "y": y,
            })

            # Mouse down
            await self.connection.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            })

            # Mouse up
            await self.connection.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            })

            return {
                "success": True,
                "clicked_at": {"x": x, "y": y},
                "element": element.to_dict()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def type_text(
        self,
        text: str,
        element: BrowserElement = None,
        selector: str = None,
        clear_first: bool = True
    ) -> Dict[str, Any]:
        """Type text into an element."""
        try:
            # Focus element if provided
            if element or selector:
                if not element:
                    element = await self.find_element(selector=selector)
                if element:
                    await self.click_element(element=element)
                    await asyncio.sleep(0.1)

            # Clear existing text
            if clear_first:
                await self.connection.send("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": "a",
                    "modifiers": 2,  # Ctrl
                })
                await self.connection.send("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": "a",
                    "modifiers": 2,
                })
                await self.connection.send("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "key": "Backspace",
                })
                await self.connection.send("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "key": "Backspace",
                })

            # Type text using insertText (handles all characters)
            await self.connection.send("Input.insertText", {"text": text})

            return {"success": True, "typed": text}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_script(self, script: str) -> Dict[str, Any]:
        """
        Execute JavaScript in the page context.

        Returns the result of the script execution.
        """
        try:
            result = await self.connection.send("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            })

            if "exceptionDetails" in result:
                return {
                    "success": False,
                    "error": result["exceptionDetails"].get("text", "Script error")
                }

            return {
                "success": True,
                "result": result.get("result", {}).get("value")
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_content(self) -> Dict[str, Any]:
        """Get the full page HTML content."""
        try:
            result = await self.execute_script("document.documentElement.outerHTML")
            return {
                "success": True,
                "html": result.get("result", "")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_styles(
        self,
        element: BrowserElement = None,
        selector: str = None
    ) -> Dict[str, Any]:
        """Get computed CSS styles for an element."""
        try:
            if not element and selector:
                element = await self.find_element(selector=selector)

            if not element or not element.backend_node_id:
                return {"success": False, "error": "Element not found"}

            result = await self.connection.send(
                "CSS.getComputedStyleForNode",
                {"nodeId": element.node_id}
            )

            styles = {}
            for item in result.get("computedStyle", []):
                styles[item.get("name")] = item.get("value")

            return {"success": True, "styles": styles}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def extract_page_blueprint(self) -> Dict[str, Any]:
        """
        Extract everything needed to recreate/clone a page.

        Returns:
            - HTML structure
            - CSS styles (computed)
            - Component breakdown
            - Design tokens (colors, fonts, spacing)
        """
        try:
            # Get HTML
            html_result = await self.get_page_content()
            html = html_result.get("html", "")

            # Get all interactive elements
            elements = await self.get_interactive_elements()

            # Extract design tokens via JavaScript
            tokens_script = """
            (function() {
                const styles = getComputedStyle(document.body);
                const colors = new Set();
                const fonts = new Set();

                // Collect colors and fonts from all elements
                document.querySelectorAll('*').forEach(el => {
                    const s = getComputedStyle(el);
                    if (s.color) colors.add(s.color);
                    if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)')
                        colors.add(s.backgroundColor);
                    if (s.fontFamily) fonts.add(s.fontFamily.split(',')[0].trim());
                });

                return {
                    colors: Array.from(colors).slice(0, 20),
                    fonts: Array.from(fonts).slice(0, 10),
                    bodyFont: styles.fontFamily,
                    bodyFontSize: styles.fontSize,
                    bodyColor: styles.color,
                    bodyBackground: styles.backgroundColor,
                };
            })()
            """
            tokens_result = await self.execute_script(tokens_script)

            return {
                "success": True,
                "html": html[:50000],  # Limit size
                "elements_count": len(elements),
                "interactive_elements": [e.to_dict() for e in elements[:100]],
                "design_tokens": tokens_result.get("result", {}),
                "url": self.current_page.url if self.current_page else "",
                "title": self.current_page.title if self.current_page else "",
            }

        except Exception as e:
            logger.exception("Failed to extract blueprint")
            return {"success": False, "error": str(e)}

    async def get_network_requests(self) -> List[Dict]:
        """Get recent network requests (requires Network domain enabled)."""
        # This would need the Network domain enabled and event tracking
        # For now, return a placeholder
        return {"success": False, "error": "Network tracking not yet implemented"}

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        try:
            result = await self.connection.send("Page.navigate", {"url": url})
            return {
                "success": True,
                "frame_id": result.get("frameId"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def wait_for_element(
        self,
        text: str = None,
        role: str = None,
        selector: str = None,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Wait for an element to appear."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            element = await self.find_element(text=text, role=role, selector=selector)
            if element:
                return {
                    "success": True,
                    "element": element.to_dict()
                }
            await asyncio.sleep(0.2)

        return {"success": False, "error": "Timeout waiting for element"}


# Utility function to launch Chrome with debugging
def launch_chrome_with_debugging(
    port: int = DEFAULT_CDP_PORT,
    url: str = "about:blank",
    headless: bool = False
) -> subprocess.Popen:
    """
    Launch Chrome with remote debugging enabled.

    Args:
        port: Debugging port
        url: Initial URL to open
        headless: Run in headless mode

    Returns:
        Popen process object
    """
    import shutil

    # Find Chrome executable
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
        shutil.which("google-chrome"),
    ]

    chrome_path = None
    for path in chrome_paths:
        if path and (path == shutil.which("chrome") or
                     path == shutil.which("google-chrome") or
                     __import__("os").path.exists(path)):
            chrome_path = path
            break

    if not chrome_path:
        raise FileNotFoundError("Chrome executable not found")

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if headless:
        args.append("--headless=new")

    if url:
        args.append(url)

    return subprocess.Popen(args)


# Global instance
_browser: Optional[BrowserAutomation] = None


def get_browser(port: int = DEFAULT_CDP_PORT) -> BrowserAutomation:
    """Get global browser automation instance."""
    global _browser
    if _browser is None:
        _browser = BrowserAutomation(port)
    return _browser


async def get_browser_async(port: int = DEFAULT_CDP_PORT) -> BrowserAutomation:
    """Get and connect to browser."""
    browser = get_browser(port)
    if not browser.connection:
        await browser.connect()
    return browser

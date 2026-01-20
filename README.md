# PC Control MCP Server

**Universal MCP server for AI-powered PC automation**

Works with Claude Code, Cursor, Windsurf, and any MCP-compatible AI assistant.

A powerful MCP server for intelligent PC control using:
- **UI Automation** - Click elements by name (native Windows apps)
- **Browser CDP** - Direct Chrome control (DOM, elements, JS execution) ⭐ NEW!
- **OCR** - Find/click any text on screen (works with browsers!)
- **Vision** - Template matching, screen change detection
- **Fast capture** - GPU-accelerated screenshots

## Why This Is Better

| Feature | Old pc-control | claude-pc |
|---------|---------------|-----------|
| Click elements | By coordinates (fragile) | By name OR by text (robust) |
| Browser support | Screenshots only | **FULL CDP support!** + OCR |
| Browser elements | None | Get ALL interactive elements! |
| JavaScript | None | Execute any JS in page! |
| Page extraction | None | Extract full page blueprint! |
| Wait for changes | Manual polling | `wait_for_screen_change` |
| Screen capture | ~200ms | ~50ms (GPU accelerated) |

## Quick Start

```bash
cd claude-pc-mcp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Add to `~/.claude.json`:
```json
{
  "mcpServers": {
    "claude-pc": {
      "type": "stdio",
      "command": "C:\path\to\claude-pc-mcp\.venv\Scripts\python.exe",
      "args": ["C:\path\to\claude-pc-mcp\run.py"]
    }
  }
}
```

### For Browser CDP (Chrome Control)

Start Chrome with remote debugging:
```bash
chrome.exe --remote-debugging-port=9222
```

Or for a clean profile:
```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug
```

## Tools Overview

### 🌐 Browser Control (CDP) - NEW!
**Best for: Chrome/Edge browsers - FULL control over web content!**

| Tool | Description |
|------|-------------|
| `connect_browser` | Connect to Chrome with debugging enabled |
| `get_browser_elements` | Get ALL interactive elements with bounds! |
| `click_browser_element` | Click element by text/role/selector |
| `type_in_browser` | Type text into browser elements |
| `execute_browser_js` | Run JavaScript in page context |
| `get_page_blueprint` | Extract everything to clone a page |
| `get_browser_pages` | List all open tabs |
| `browser_navigate` | Navigate to URL |
| `wait_for_browser_element` | Wait for element to appear |

### 🖥️ Native App Control (UI Automation)
**Best for: Windows native applications (Notepad, File Explorer, etc.)**

| Tool | Description |
|------|-------------|
| `find_element` | Find element by name/type/id |
| `click_element` | Click element by selector |
| `type_into_element` | Type into element |
| `get_ui_tree` | Get UI element hierarchy |
| `wait_for_element` | Wait for element state |

### 🔤 Text/Universal Control (OCR)
**Best for: Any application with visible text (fallback for browsers without CDP)**

| Tool | Description |
|------|-------------|
| `find_text_on_screen` | Find text and get coordinates |
| `click_text` | Find and click text (one call!) |
| `get_screen_text` | Extract all visible text |
| `wait_for_text` | Wait for text to appear/disappear |

### 👁️ Vision Tools
**For image-based interaction and screen monitoring**

| Tool | Description |
|------|-------------|
| `find_image_on_screen` | Find image/icon using template matching |
| `wait_for_screen_change` | Wait for screen to update |

### ⌨️ Screen & Input
| Tool | Description |
|------|-------------|
| `capture_screen` | Fast screenshot (50ms) |
| `click_at` | Click coordinates (fallback) |
| `type_text` | Type at cursor |
| `send_keys` | Keyboard with special keys |
| `scroll` | Mouse wheel |
| `focus_window` | Bring window to front |
| `get_windows` | List windows with bounds |

## Usage Examples

### 🌐 Browser Automation with CDP (BEST!)

```python
# 1. Connect to Chrome (must be started with --remote-debugging-port=9222)
connect_browser()

# 2. Get ALL interactive elements on the page
get_browser_elements()
# Returns: buttons, links, inputs with EXACT coordinates!

# 3. Click by element text
click_browser_element(text="Sign In", role="button")

# 4. Fill a form
click_browser_element(text="Email")
type_in_browser(text="user@example.com")
click_browser_element(text="Password")
type_in_browser(text="mypassword")
click_browser_element(text="Log In")

# 5. Execute JavaScript
execute_browser_js(script="document.title")
execute_browser_js(script="document.querySelector('#submit').click()")

# 6. Extract page for cloning
get_page_blueprint()
# Returns: HTML, elements, design tokens, colors, fonts!
```

### 🖥️ Native App Control

```python
# Click a button by name
click_element(name="Submit", control_type="button")

# Type into a text field
type_into_element(name="Username", text="myuser")

# Get UI tree to explore
get_ui_tree(depth=3)
```

### 🔤 OCR Fallback (when CDP not available)

```python
# Find and click any visible text
click_text(text="Sign In")

# Wait for loading to finish
wait_for_text(text="Loading...", condition="disappear", timeout=30)
```

## When to Use What

| Scenario | Best Tool |
|----------|-----------|
| **Chrome/Edge web content** | CDP tools (`connect_browser`, `get_browser_elements`) |
| **Native Windows apps** | UI Automation (`click_element`, `find_element`) |
| **Browser without CDP** | OCR (`click_text`, `find_text_on_screen`) |
| **Any visible text** | OCR tools |
| **Image/icon matching** | Vision tools |

## Requirements

- Windows 10/11
- Python 3.10+
- Chrome/Edge for CDP features (optional)
- No admin rights needed

## Dependencies

Core:
- `mcp` - MCP SDK
- `uiautomation` - Windows UI Automation
- `mss` - Fast screen capture
- `pynput` - Input simulation
- `pywin32` - Windows API

Browser CDP (NEW!):
- `websockets` - WebSocket client for CDP
- `aiohttp` - HTTP client for CDP

OCR:
- `winrt-*` - Windows Runtime OCR (built-in to Windows)

Vision:
- `opencv-python` - Template matching
- `numpy` - Image processing

## Troubleshooting

### Browser CDP not connecting
- Make sure Chrome is started with `--remote-debugging-port=9222`
- Check if port 9222 is available: `netstat -an | find "9222"`
- Try with a clean profile: `chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\temp\chrome-debug`

### get_browser_elements returns empty
- Page might still be loading - wait a moment
- Some elements might be in iframes (not supported yet)
- Check if the page uses Shadow DOM (limited support)

### OCR not finding text
- Ensure text is clearly visible (not cut off, not too small)
- Try `get_screen_text()` to see what OCR detects
- Increase font size in target application

### click_element not working in browser
- Use CDP tools for browsers! (`click_browser_element`)
- UI Automation can't see browser internal content

### Performance tips
- CDP is fastest for browsers - use it when possible!
- Use `region` parameter for OCR to limit search area
- `wait_for_screen_change` is more efficient than polling

## Changelog

### v0.3.0 - Browser CDP Support
- NEW: Full Chrome DevTools Protocol integration
- NEW: `connect_browser` - connect to Chrome
- NEW: `get_browser_elements` - get all interactive elements
- NEW: `click_browser_element` - click by text/role/selector
- NEW: `type_in_browser` - type into browser elements
- NEW: `execute_browser_js` - run JavaScript
- NEW: `get_page_blueprint` - extract page for cloning
- NEW: `browser_navigate` - navigate to URL
- NEW: `wait_for_browser_element` - wait for elements

### v0.2.0 - OCR & Vision
- Added OCR tools for browser text interaction
- Added vision tools for template matching
- Improved window bounds detection

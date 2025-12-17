# PC Control MCP Server

**Universal MCP server for AI-powered PC automation**

Works with Claude Code, Cursor, Windsurf, and any MCP-compatible AI assistant.

A powerful MCP server for intelligent PC control using:
- **UI Automation** - Click elements by name (native Windows apps)
- **OCR** - Find/click any text on screen (works with browsers!)
- **Vision** - Template matching, screen change detection
- **Fast capture** - GPU-accelerated screenshots

## Why This Is Better

| Feature | Old pc-control | claude-pc |
|---------|---------------|-----------|
| Click elements | By coordinates (fragile) | By name OR by text (robust) |
| Browser support | Screenshots only | OCR finds/clicks any text! |
| Wait for changes | Manual polling | `wait_for_screen_change` |
| Screen capture | ~200ms | ~50ms (GPU accelerated) |
| Window info | Basic | Full bounds, process info |

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
      "command": "C:\\Users\\sedric\\claude-pc-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\sedric\\claude-pc-mcp\\run.py"]
    }
  }
}
```

## Tools Overview

### Native App Control (UI Automation)
Best for: Windows native applications (Notepad, File Explorer, etc.)

| Tool | Description |
|------|-------------|
| `find_element` | Find element by name/type/id |
| `click_element` | Click element by selector |
| `type_into_element` | Type into element |
| `get_ui_tree` | Get UI element hierarchy |
| `wait_for_element` | Wait for element state |

### Browser/Universal Control (OCR)
Best for: Browsers, web apps, any application with visible text

| Tool | Description |
|------|-------------|
| `find_text_on_screen` | Find text and get coordinates |
| `click_text` | Find and click text (one call!) |
| `get_screen_text` | Extract all visible text |
| `wait_for_text` | Wait for text to appear/disappear |

### Vision Tools
For image-based interaction and screen monitoring

| Tool | Description |
|------|-------------|
| `find_image_on_screen` | Find image/icon using template matching |
| `wait_for_screen_change` | Wait for screen to update |

### Screen & Input
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

### Click a button in native app
```python
# Preferred - by element name
click_element(name="Submit", control_type="button")
```

### Click a button in browser
```python
# Use OCR - works with any visible text!
click_text(text="Sign In")
```

### Wait for page load
```python
click_text(text="Load Data")
wait_for_text(text="Loading...", condition="disappear", timeout=30)
```

### Wait for any screen change
```python
click_at(x=500, y=300)
wait_for_screen_change(timeout=5)
```

### Fill a form
```python
# Native app
type_into_element(name="Username", text="myuser")
type_into_element(name="Password", text="mypass")
click_element(name="Login")

# Browser (using OCR)
click_text(text="Username")
type_text(text="myuser")
send_keys(keys="{TAB}")
type_text(text="mypass")
click_text(text="Log in")
```

## Important Limitations

### UI Automation (find_element, click_element, etc.)
- **Works great with**: Native Windows apps (Notepad, Explorer, Office, etc.)
- **Does NOT work with**: Browser internal content (Chrome, Edge, Firefox)
- Browsers expose only the outer window, not web page elements

### OCR Tools (find_text_on_screen, click_text, etc.)
- **Works with everything**: Any visible text on screen
- Slightly slower than UI Automation (~100-200ms for OCR)
- Requires Windows 10/11 for built-in OCR

### When to use what
1. **Native Windows app** -> Use `click_element`, `find_element`
2. **Browser/web content** -> Use `click_text`, `find_text_on_screen`
3. **Unknown/mixed** -> Try OCR tools (they work everywhere)

## Requirements

- Windows 10/11
- Python 3.10+
- No admin rights needed

## Dependencies

Core:
- `mcp` - MCP SDK
- `uiautomation` - Windows UI Automation
- `mss` - Fast screen capture
- `pynput` - Input simulation
- `pywin32` - Windows API

OCR:
- `winrt-*` - Windows Runtime OCR (built-in to Windows)

Vision:
- `opencv-python` - Template matching
- `numpy` - Image processing

## Troubleshooting

### OCR not finding text
- Ensure text is clearly visible (not cut off, not too small)
- Try `get_screen_text()` to see what OCR detects
- Increase font size in target application

### click_element not working
- Check if target is a browser (use `click_text` instead)
- Use `get_ui_tree()` to see available elements
- Some custom controls don't expose UI Automation

### Window bounds showing 0,0,0,0
- Fixed in v0.2! Now uses win32gui for accurate bounds
- Restart Claude Code to reload the MCP server

### Performance tips
- Use `region` parameter to limit search area
- OCR is faster on smaller regions
- `wait_for_screen_change` is more efficient than polling screenshots

#!/usr/bin/env python3
"""
Run the Claude PC Control MCP Server.

Usage:
    python run.py
"""

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Add src to path
sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

# Change to script directory for relative imports
os.chdir(SCRIPT_DIR)

import asyncio

async def main():
    """Run the server."""
    from server import main as server_main
    await server_main()

if __name__ == "__main__":
    asyncio.run(main())

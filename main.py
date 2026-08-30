"""Convenience entry point for running the bot via 'python main.py' from project root."""
import asyncio
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from app.main import main

if __name__ == "__main__":
    asyncio.run(main())

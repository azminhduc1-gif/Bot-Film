"""Package entry point for running via 'python -m app'."""
import asyncio
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from app.main import main

if __name__ == "__main__":
    asyncio.run(main())

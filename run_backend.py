"""
Start the Hemaya backend server.

Run this instead of `uvicorn backend.main:app --reload`.
--reload uses multiprocessing.spawn which has a known asyncio bug on Python 3.14 Windows.
This script runs the server directly without spawning a subprocess.

Usage:
    python run_backend.py
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        # NO reload=True — Python 3.14 asyncio.run() hangs in spawned subprocesses on Windows
    )

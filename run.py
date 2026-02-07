"""ThoughtLink — Launch script."""

import uvicorn
import os
import sys

# Ensure the project root is in path
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[os.path.dirname(__file__)],
    )

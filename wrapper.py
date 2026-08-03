import os
import sys

# Ensure Python can resolve modules inside src/
sys.path.insert(0, os.path.abspath("src"))

from intervals_icu_mcp.server import mcp

# In fastmcp v3, mcp.run with transport="sse" automatically handles CORS and starts the server.
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    mcp.run(transport="sse", host=host, port=port)

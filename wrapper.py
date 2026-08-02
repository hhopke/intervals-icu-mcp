import os
import sys

# Ensure Python can resolve the package inside src/
sys.path.insert(0, os.path.abspath("src"))

from starlette.middleware.cors import CORSMiddleware
from intervals_icu_mcp.server import mcp

# Grab underlying ASGI app instance
app = getattr(mcp, "_mcp_server", mcp).app if hasattr(mcp, "_mcp_server") else mcp.http_app

# Inject CORS middleware so OPTIONS preflight returns HTTP 200/204
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="sse", host=host, port=port)

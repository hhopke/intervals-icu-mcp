import os
from starlette.middleware.cors import CORSMiddleware
from intervals_icu_mcp.server import mcp

# 1. Grab the underlying ASGI/Starlette app instance from FastMCP
app = getattr(mcp, "_mcp_server", mcp).app if hasattr(mcp, "_mcp_server") else mcp.http_app

# 2. Inject CORS middleware so OPTIONS requests return HTTP 200/204
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Launch the server using FastMCP's built-in run method
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="sse", host=host, port=port)

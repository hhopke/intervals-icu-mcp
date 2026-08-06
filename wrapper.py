import os
import sys
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

# Ensure Python can resolve modules inside src/
sys.path.insert(0, os.path.abspath("src"))

from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from intervals_icu_mcp.server import mcp

import os
import sys
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse
from urllib.parse import parse_qsl

# Ensure Python can resolve modules inside src/
sys.path.insert(0, os.path.abspath("src"))

from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from intervals_icu_mcp.server import mcp

# Strict ASGI Authentication Middleware for Token Auth
class TokenAuthASGIMiddleware:
    def __init__(self, app):
        self.app = app
        self.expected_token = os.getenv("MCP_SECRET")
        if not self.expected_token:
            print("WARNING: MCP_SECRET environment variable is not set! The server will reject all requests.", flush=True)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")
            
            # Protect GET and POST on /mcp
            if path == "/mcp" and method in ("GET", "POST"):
                headers = dict(scope.get("headers", []))
                # Check for token in query parameters
                query_string = scope.get("query_string", b"").decode("utf-8")
                query_params = dict(parse_qsl(query_string))
                provided_token = query_params.get("token")
                
                # Check for token in Authorization header
                if not provided_token:
                    auth = headers.get(b"authorization", b"").decode("utf-8")
                    if auth.startswith("Bearer "):
                        provided_token = auth.split(" ")[1]

                async def reject():
                    await send({
                        "type": "http.response.start", 
                        "status": 401, 
                        "headers": [
                            (b"content-type", b"application/json")
                        ]
                    })
                    await send({
                        "type": "http.response.body", 
                        "body": b'{"detail": "Unauthorized. Please provide ?token=... in the URL."}'
                    })

                if not self.expected_token or provided_token != self.expected_token:
                    await reject()
                    return

        await self.app(scope, receive, send)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    # Use streamable-http transport for Gemini Spark compatibility
    app = mcp.http_app(transport="streamable-http")
    
    # Add ProxyHeadersMiddleware to properly resolve request.base_url in Cloud Run
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    
    # Add CORS (This handles OPTIONS requests before Auth can block them)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Wrap with our simple Token Auth middleware at the very outer edge
    protected_app = TokenAuthASGIMiddleware(app)
    
    import uvicorn
    uvicorn.run(protected_app, host=host, port=port)

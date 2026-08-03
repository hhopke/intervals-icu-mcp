import os
import sys

# Ensure Python can resolve modules inside src/
sys.path.insert(0, os.path.abspath("src"))

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware

from intervals_icu_mcp.server import mcp

# 1. Add Token Endpoint
@mcp.custom_route("/token", methods=["POST"])
async def token(request: Request):
    form = await request.form()
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    
    expected_id = os.getenv("SPARK_CLIENT_ID", "gemini-spark")
    expected_secret = os.getenv("SPARK_CLIENT_SECRET", "secret123")
    
    if client_id == expected_id and client_secret == expected_secret:
        return JSONResponse({
            "access_token": "valid_spark_token_123",
            "token_type": "Bearer",
            "expires_in": 3600
        })
    else:
        return JSONResponse({"error": "invalid_client"}, status_code=401)


# 2. Strict Authentication Middleware
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only protect /sse and /messages paths
        if request.url.path in ["/sse", "/messages"]:
            # Cloud Run / Gemini also sends OPTIONS for preflight, don't block OPTIONS!
            if request.method == "OPTIONS":
                return await call_next(request)
                
            auth_header = request.headers.get("Authorization", "")
            if auth_header != "Bearer valid_spark_token_123":
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    mcp.run(
        transport="sse", 
        host=host, 
        port=port,
        middleware=[
            Middleware(APIKeyAuthMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ]
    )

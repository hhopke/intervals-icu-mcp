import os
import sys
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

# Ensure Python can resolve modules inside src/
sys.path.insert(0, os.path.abspath("src"))

from starlette.middleware.cors import CORSMiddleware
from intervals_icu_mcp.server import mcp

def get_oauth_protected_resource():
    return JSONResponse({
        "authorization_servers": [
            "https://accounts.google.com"
        ]
    })

# Add RFC 9289 OAuth Protected Resource Metadata
@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_resource_root(request: Request):
    return get_oauth_protected_resource()

@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def oauth_protected_resource_mcp(request: Request):
    return get_oauth_protected_resource()


# Strict ASGI Authentication Middleware for Google OAuth
class GoogleOAuthASGIMiddleware:
    def __init__(self, app):
        self.app = app
        # Optional: Set this environment variable in Cloud Run to bypass validation during testing
        self.skip_validation = os.getenv("SKIP_AUTH_VALIDATION", "false").lower() == "true"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")
            
            # We now protect /mcp instead of /sse since we are using streamable-http
            if path == "/mcp":
                if method != "OPTIONS":
                    headers = dict(scope.get("headers", []))
                    # Headers in ASGI are lowercase bytes
                    auth = headers.get(b"authorization", b"").decode("utf-8")
                    
                    async def reject(reason="invalid_token"):
                        await send({
                            "type": "http.response.start", 
                            "status": 401, 
                            "headers": [
                                (b"content-type", b"application/json"),
                                (b"www-authenticate", f'Bearer error="{reason}"'.encode("utf-8"))
                            ]
                        })
                        await send({
                            "type": "http.response.body", 
                            "body": b'{"detail": "Unauthorized"}'
                        })

                    if not auth.startswith("Bearer "):
                        # Require Bearer token
                        await reject("invalid_request")
                        return
                    
                    token = auth.split(" ")[1]
                    
                    # Validate the token with Google
                    if not self.skip_validation:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")
                            if resp.status_code != 200:
                                await reject("invalid_token")
                                return

        await self.app(scope, receive, send)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    # Use streamable-http transport for Gemini Spark compatibility
    app = mcp.http_app(transport="streamable-http")
    
    # Add CORS (This handles OPTIONS requests before Auth can block them)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Wrap with our guaranteed Google Auth middleware at the very outer edge
    protected_app = GoogleOAuthASGIMiddleware(app)
    
    import uvicorn
    uvicorn.run(protected_app, host=host, port=port)

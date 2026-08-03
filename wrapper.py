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

def get_base_url(request: Request) -> str:
    # Use headers to construct the real base URL if behind a proxy
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.hostname)
    return f"{scheme}://{host}"

def get_oauth_discovery_document(request: Request):
    base_url = get_base_url(request)
    return JSONResponse({
        "issuer": base_url,
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    })
# Add OAuth Discovery endpoints for Gemini Spark (RFC 8414 & OpenID)
@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_authorization_server(request: Request):
    return get_oauth_discovery_document(request)

@mcp.custom_route("/.well-known/openid-configuration", methods=["GET"])
async def openid_configuration(request: Request):
    return get_oauth_discovery_document(request)

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
            
            # We protect /sse for standard SSE transport
            if path == "/sse":
                if method != "OPTIONS":
                    headers = dict(scope.get("headers", []))
                    # Headers in ASGI are lowercase bytes
                    auth = headers.get(b"authorization", b"").decode("utf-8")
                    
                    async def reject():
                        await send({
                            "type": "http.response.start", 
                            "status": 401, 
                            "headers": [
                                (b"content-type", b"application/json"),
                                (b"www-authenticate", b"Bearer")
                            ]
                        })
                        await send({
                            "type": "http.response.body", 
                            "body": b'{"detail": "Unauthorized"}'
                        })

                    if not auth.startswith("Bearer "):
                        # Require Bearer token
                        await reject()
                        return
                    
                    token = auth.split(" ")[1]
                    
                    # Validate the token with Google
                    if not self.skip_validation:
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")
                            if resp.status_code != 200:
                                await reject()
                                return

        await self.app(scope, receive, send)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    # Use sse transport for Gemini Spark compatibility
    app = mcp.http_app(transport="sse")
    
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
    
    # Wrap with our guaranteed Google Auth middleware at the very outer edge
    protected_app = GoogleOAuthASGIMiddleware(app)
    
    import uvicorn
    uvicorn.run(protected_app, host=host, port=port)

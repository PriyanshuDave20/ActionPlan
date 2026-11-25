import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Optional bearer-token authentication.

    If ``tokens`` is empty, authentication is disabled for local development.
    In production, set ``API_TOKENS`` to a comma-separated list and callers
    must send ``Authorization: Bearer <token>``.
    """

    def __init__(self, app, tokens: str | None = None) -> None:
        super().__init__(app)
        self.tokens = [token.strip() for token in (tokens or "").split(",") if token.strip()]

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.tokens or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not any(
            hmac.compare_digest(token, expected) for expected in self.tokens
        ):
            return JSONResponse(
                {"detail": "Missing or invalid API token."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

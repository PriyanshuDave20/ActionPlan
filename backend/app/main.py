from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.middleware import SecurityHeadersMiddleware, TokenAuthMiddleware
from app.api.routes.documents import router as documents_router
from app.api.routes.goals import router as goals_router
from app.api.routes.workflows import router as workflows_router
from app.config import get_settings

app = FastAPI(title="AI Workplace Operations Agent", version="0.1.0")

settings = get_settings()

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
            return JSONResponse(
                {"detail": f"Request body exceeds {self.max_bytes} bytes."},
                status_code=413,
            )
        return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TokenAuthMiddleware, tokens=settings.api_tokens)

app.include_router(goals_router)
app.include_router(workflows_router)
app.include_router(documents_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve the built web frontend at "/" when it exists. API routes are
# registered before this mount so they always take precedence.
if settings.frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")

"""CSP frame-ancestors middleware to allow embedding from hankel.ai."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        origins = get_settings().embed_origins_list
        ancestors = " ".join(["'self'"] + origins)
        response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
        return response

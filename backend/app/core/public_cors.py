"""CORS for the public widget endpoints (/api/v1/public/*), which run on customers' own websites.

They authenticate with a short-lived widget token in the Authorization header and never use cookies, so any
origin may call them (no credentials). Everything else keeps the strict CORS_ORIGINS list. This middleware must
sit outside CORSMiddleware so it answers public preflights before the strict check rejects unknown origins.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_PREFIX = "/api/v1/public/"
_ALLOW = [
    (b"access-control-allow-origin", b"*"),
    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
    (b"access-control-allow-headers", b"authorization, content-type"),
    (b"access-control-max-age", b"600"),
]


class PublicCORSMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(PUBLIC_PREFIX):
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":  # preflight
            await send({"type": "http.response.start", "status": 204, "headers": _ALLOW})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if not k.lower().startswith(b"access-control-")]
                message = {**message, "headers": headers + _ALLOW}
            await send(message)

        await self.app(scope, receive, send_with_cors)

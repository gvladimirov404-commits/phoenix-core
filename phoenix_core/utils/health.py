"""
Health check utilities for monitoring and Docker health checks.
"""
import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from aiohttp import web

from phoenix_core._version import __version__ as _PHOENIX_VERSION


class HealthStatus:
    """Health status information"""
    def __init__(self) -> None:
        """Create a fresh, initially-healthy status snapshot with no checks yet."""
        self.status: str = "healthy"
        self.timestamp: str = datetime.utcnow().isoformat()
        self.version: str = _PHOENIX_VERSION
        self.checks: Dict[str, Any] = {}

    def add_check(self, name: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record one check's result; any non-"healthy" check marks the overall status unhealthy."""
        self.checks[name] = {
            "status": status,
            "details": details or {},
        }
        if status != "healthy":
            self.status = "unhealthy"

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict representation suitable for a JSON response."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "checks": self.checks,
        }


class HealthServer:
    """Simple HTTP health check server"""
    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Build the aiohttp application and register /health and /ready routes.

        Note: no socket is opened until start() is called.
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/ready", self.ready_handler)
        self._checks: Dict[str, Callable[[], Any]] = {}

    def add_check(self, name: str, check_func: Callable[[], Any]) -> None:
        """Register a named check. check_func may be sync or async and takes no args."""
        self._checks[name] = check_func

    async def health_handler(self, request: web.Request) -> web.Response:
        """Run all registered checks and return an aggregated health status."""
        status = HealthStatus()
        status.add_check("core", "healthy", {"uptime": "running"})

        for name, check_func in self._checks.items():
            try:
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                status.add_check(name, "healthy", result)
            except Exception as e:
                status.add_check(name, "unhealthy", {"error": str(e)})

        return web.json_response(status.to_dict(), status=200 if status.status == "healthy" else 503)

    async def ready_handler(self, request: web.Request) -> web.Response:
        """Simple readiness probe — always reports ready once the server responds."""
        return web.json_response({"ready": True}, status=200)

    async def start(self) -> None:
        """Start the HTTP server and run until cancelled, then clean up the runner."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"Health server running on http://{self.host}:{self.port}")

        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

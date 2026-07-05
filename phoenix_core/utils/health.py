"""
Health check utilities for monitoring and Docker health checks.
"""
import asyncio
from datetime import datetime
from typing import Any, Dict

from aiohttp import web


class HealthStatus:
    """Health status information"""
    def __init__(self):
        self.status = "healthy"
        self.timestamp = datetime.utcnow().isoformat()
        self.version = "1.0.0"
        self.checks: Dict[str, Any] = {}

    def add_check(self, name: str, status: str, details: Dict[str, Any] = None) -> None:
        self.checks[name] = {
            "status": status,
            "details": details or {},
        }
        if status != "healthy":
            self.status = "unhealthy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "checks": self.checks,
        }


class HealthServer:
    """Simple HTTP health check server"""
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/ready", self.ready_handler)
        self._checks: Dict[str, Any] = {}

    def add_check(self, name: str, check_func: Any) -> None:
        self._checks[name] = check_func

    async def health_handler(self, request: web.Request) -> web.Response:
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
        return web.json_response({"ready": True}, status=200)

    async def start(self) -> None:
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"Health server running on http://{self.host}:{self.port}")
        
        while True:
            await asyncio.sleep(3600)

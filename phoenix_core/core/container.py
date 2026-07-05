"""
Dependency Injection Container using the Dependency Inversion Principle.
Manages all service dependencies and their lifecycles.
"""
from typing import Any, Dict, Optional, Type, TypeVar

from phoenix_core.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class Container:
    """Simple DI container for managing service dependencies"""
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Any] = {}
        self._singletons: Dict[str, Any] = {}

    def register(self, name: str, instance: Any) -> None:
        """Register a service instance"""
        self._services[name] = instance
        logger.debug(f"Registered service: {name}")

    def register_factory(self, name: str, factory: Any, singleton: bool = False) -> None:
        """Register a factory function for lazy initialization"""
        self._factories[name] = {"factory": factory, "singleton": singleton}
        if singleton:
            self._singletons[name] = None
        logger.debug(f"Registered factory: {name} (singleton={singleton})")

    def resolve(self, name: str) -> Any:
        """Resolve a service by name"""
        if name in self._services:
            return self._services[name]
        if name in self._singletons:
            if self._singletons[name] is None:
                self._singletons[name] = self._factories[name]["factory"]()
            return self._singletons[name]
        if name in self._factories:
            return self._factories[name]["factory"]()
        raise KeyError(f"Service '{name}' not found in container")

    def resolve_typed(self, service_type: Type[T]) -> T:
        """Resolve a service by type"""
        for service in self._services.values():
            if isinstance(service, service_type):
                return service
        raise KeyError(f"Service of type {service_type.__name__} not found")

    def has(self, name: str) -> bool:
        """Check if a service is registered"""
        return name in self._services or name in self._factories

    def unregister(self, name: str) -> None:
        """Unregister a service"""
        self._services.pop(name, None)
        self._factories.pop(name, None)
        self._singletons.pop(name, None)
        logger.debug(f"Unregistered service: {name}")

    def clear(self) -> None:
        """Clear all registered services"""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        logger.debug("Cleared all services from container")

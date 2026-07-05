"""
Custom exceptions for Phoenix Core.
"""


class PhoenixError(Exception):
    """Base exception for all Phoenix Core errors"""
    pass


class ConfigurationError(PhoenixError):
    """Raised when configuration is invalid or missing"""
    pass


class AIProviderError(PhoenixError):
    """Raised when AI provider encounters an error"""
    pass


class AIProviderNotFoundError(AIProviderError):
    """Raised when requested AI provider is not found"""
    pass


class AIProviderRateLimitError(AIProviderError):
    """Raised when AI provider rate limit is exceeded"""
    pass


class TelegramError(PhoenixError):
    """Raised when Telegram operation fails"""
    pass


class GitHubError(PhoenixError):
    """Raised when GitHub operation fails"""
    pass


class PluginError(PhoenixError):
    """Raised when plugin operation fails"""
    pass


class PluginNotFoundError(PluginError):
    """Raised when plugin is not found"""
    pass


class SecurityError(PhoenixError):
    """Raised when security check fails"""
    pass


class ValidationError(PhoenixError):
    """Raised when data validation fails"""
    pass


class TermuxCompatibilityError(PhoenixError):
    """Raised when Termux compatibility issue occurs"""
    pass

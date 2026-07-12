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


class AIProviderTimeoutError(AIProviderError):
    """Raised when a request to an AI provider times out"""
    pass


class AIProviderConnectionError(AIProviderError):
    """Raised when a network/connection error occurs while contacting an AI provider"""
    pass


class AIProviderInvalidResponseError(AIProviderError):
    """Raised when an AI provider returns a malformed or unexpected response"""
    pass


class TelegramError(PhoenixError):
    """Raised when Telegram operation fails"""
    pass


class GitHubError(PhoenixError):
    """Raised when GitHub operation fails"""
    pass


class GitHubConfigurationError(GitHubError):
    """Raised when the GitHub client is missing required configuration (token/owner/repo)"""
    pass


class GitHubAuthenticationError(GitHubError):
    """Raised when GitHub authentication fails (401 Unauthorized)"""
    pass


class GitHubForbiddenError(GitHubError):
    """Raised when GitHub access is forbidden (403, not rate-limit related)"""
    pass


class GitHubNotFoundError(GitHubError):
    """Raised when the requested GitHub repository or resource is not found (404)"""
    pass


class GitHubRateLimitError(GitHubError):
    """Raised when the GitHub API rate limit is exceeded"""
    pass


class GitHubTimeoutError(GitHubError):
    """Raised when a request to GitHub times out"""
    pass


class GitHubConnectionError(GitHubError):
    """Raised when a network/connection error occurs while contacting GitHub"""
    pass


class GitHubInvalidResponseError(GitHubError):
    """Raised when GitHub returns a malformed or unexpected response"""
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


class GuardError(PhoenixError):
    """Raised when the AI Guard Layer blocks a request before it reaches a provider"""
    pass


class StorageError(PhoenixError):
    """Raised when a Conversation Memory storage backend cannot be opened or used
    (e.g. a corrupted SQLite database file) — see Task 013 error-scenario audit"""
    pass


class RateLimitExceededError(GuardError):
    """Raised when a caller exceeds the configured AI request rate limit"""
    pass


class PromptTooLargeError(GuardError):
    """Raised when a single prompt exceeds the configured size limit"""
    pass


class ContextTooLargeError(GuardError):
    """Raised when the assembled conversation context exceeds the configured size limit"""
    pass

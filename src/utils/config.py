# src/utils/config.py
"""
Configuration Management

Handles application settings and Azure Key Vault integration for secrets.

Version: 2.8.1 - Code review security and reliability fixes
"""
import atexit
import re
from functools import lru_cache
from types import TracebackType
from typing import Optional, Type

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings

from src.utils.constants import (
    DEFAULT_MAX_TOKENS,
    CACHE_TTL_DAYS as DEFAULT_CACHE_TTL_DAYS,
    AZURE_DEVOPS_TIMEOUT,
)
from src.utils.logging import get_logger

# Application version - single source of truth
__version__ = "2.8.1"

logger = get_logger(__name__)

# Pre-compiled pattern for secret name validation
_SECRET_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9-]{1,127}$")


class Settings(BaseSettings):
    """
    Application settings from environment variables.

    These are non-secret configuration values that can be stored
    in Function App settings or .env file.
    """

    # Azure Configuration
    KEYVAULT_URL: str = Field(..., description="Azure Key Vault URL")
    AZURE_STORAGE_ACCOUNT_NAME: str = Field(
        ..., min_length=3, max_length=24, description="Storage account name"
    )
    AZURE_DEVOPS_ORG: str = Field(
        ..., min_length=1, max_length=255, description="Azure DevOps organization"
    )

    # AI Configuration
    OPENAI_MODEL: str = Field(default="gpt-4o", description="Model name or deployment")
    OPENAI_MAX_TOKENS: int = Field(
        default=DEFAULT_MAX_TOKENS, ge=1, le=128000, description="Max tokens"
    )

    # Application Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    ENVIRONMENT: str = Field(default="production", description="Environment name")

    # Azure AI Foundry (Recommended - set these for Azure OpenAI)
    AZURE_AI_ENDPOINT: Optional[str] = Field(
        default=None, description="Azure OpenAI endpoint URL"
    )
    AZURE_AI_DEPLOYMENT: Optional[str] = Field(
        default=None, description="Azure OpenAI deployment name"
    )

    # Cache Configuration
    CACHE_TTL_DAYS: int = Field(
        default=DEFAULT_CACHE_TTL_DAYS, ge=1, le=30, description="Cache TTL in days"
    )

    # Concurrency Configuration
    MAX_CONCURRENT_REVIEWS: int = Field(
        default=10, ge=1, le=100, description="Max parallel file reviews"
    )

    # Timer Trigger Retry Configuration
    TIMER_MAX_RETRIES: int = Field(
        default=3, ge=0, le=10, description="Max retries for timer trigger"
    )
    TIMER_RETRY_DELAY_SECONDS: int = Field(
        default=30, ge=1, le=300, description="Delay between retries"
    )

    @field_validator("KEYVAULT_URL")
    @classmethod
    def validate_keyvault_url(cls, v: str) -> str:
        """Validate Key Vault URL format."""
        if not v:
            raise ValueError("KEYVAULT_URL cannot be empty")
        if not v.startswith("https://"):
            raise ValueError("KEYVAULT_URL must use HTTPS protocol")
        if not v.endswith(".vault.azure.net/") and not v.endswith(".vault.azure.net"):
            raise ValueError(
                "KEYVAULT_URL must be an Azure Key Vault URL "
                "(format: https://<vault-name>.vault.azure.net/)"
            )
        return v.rstrip("/") + "/"

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("AZURE_AI_ENDPOINT")
    @classmethod
    def validate_azure_ai_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate Azure AI endpoint URL format."""
        if v is None:
            return v
        if not v.startswith("https://"):
            raise ValueError("AZURE_AI_ENDPOINT must use HTTPS protocol")
        return v.rstrip("/")

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are loaded only once
    per function instance.

    Returns:
        Settings object with all configuration
    """
    return Settings()


class SecretManager:
    """
    Manages secrets from Azure Key Vault.

    Uses Managed Identity for authentication (no credentials needed).
    Implements in-memory caching for performance.
    """

    def __init__(self) -> None:
        """Initialize Secret Manager with Managed Identity."""
        settings = get_settings()

        # Use DefaultAzureCredential for Managed Identity
        # Store credential to ensure proper cleanup
        self._credential = DefaultAzureCredential()

        self.client = SecretClient(
            vault_url=settings.KEYVAULT_URL, credential=self._credential
        )

        self._cache: dict[str, str] = {}

        logger.info("secret_manager_initialized", vault_url=settings.KEYVAULT_URL)

    def get_secret(self, secret_name: str) -> str:
        """
        Get secret from Key Vault with caching and validation.

        Secrets are cached in memory for the lifetime of the function instance.
        This reduces Key Vault API calls and improves performance.

        Args:
            secret_name: Name of secret in Key Vault (e.g., OPENAI-API-KEY)
                        Must match pattern: ^[a-zA-Z0-9-]{1,127}$

        Returns:
            Secret value (guaranteed non-empty)

        Raises:
            ValueError: If secret name is invalid or secret is empty
            Exception: If secret doesn't exist or access denied
        """
        # Validate secret name format
        if not secret_name or not isinstance(secret_name, str):
            raise ValueError("Secret name must be a non-empty string")

        if not _SECRET_NAME_PATTERN.match(secret_name):
            raise ValueError(
                f"Invalid secret name '{secret_name}'. "
                "Must contain only alphanumeric characters and hyphens, "
                "and be 1-127 characters long."
            )

        # Return from cache if available
        if secret_name in self._cache:
            logger.debug("secret_cache_hit", secret_name=secret_name)
            return self._cache[secret_name]

        # Fetch from Key Vault
        try:
            logger.debug("secret_fetch_start", secret_name=secret_name)

            secret = self.client.get_secret(secret_name)

            # Validate secret value
            if not secret.value:
                raise ValueError(f"Secret '{secret_name}' is empty")

            secret_value = secret.value.strip()
            self._cache[secret_name] = secret_value

            logger.info(
                "secret_fetched",
                secret_name=secret_name,
                version=getattr(secret.properties, "version", "unknown"),
            )

            return secret_value

        except ValueError:
            # Re-raise validation errors without wrapping
            raise
        except Exception as e:
            logger.error(
                "secret_fetch_failed",
                secret_name=secret_name,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def clear_cache(self) -> None:
        """Clear the secret cache."""
        self._cache.clear()
        logger.info("secret_cache_cleared")

    def close(self) -> None:
        """Close the credential to prevent resource leaks."""
        if hasattr(self, "_credential") and self._credential:
            self._credential.close()
            logger.info("secret_manager_credential_closed")

    def __enter__(self) -> "SecretManager":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        """Context manager exit - ensure cleanup."""
        try:
            self.close()
        except Exception as cleanup_error:
            logger.error(
                "secret_manager_cleanup_failed",
                error=str(cleanup_error),
                error_type=type(cleanup_error).__name__,
                original_exception_type=type(exc_val).__name__ if exc_val else None,
            )
            # Don't suppress the original exception
        return False


# Module-level singleton for backwards compatibility
_secret_manager_instance: Optional[SecretManager] = None
_cleanup_registered: bool = False


def get_secret_manager() -> SecretManager:
    """
    Get Secret Manager instance.

    Note: This creates a module-level singleton for backwards compatibility.
    For better resource management, use SecretManager() as a context manager:

        with SecretManager() as sm:
            secret = sm.get_secret("MY_SECRET")

    Returns:
        SecretManager instance
    """
    global _secret_manager_instance, _cleanup_registered

    if _secret_manager_instance is None:
        _secret_manager_instance = SecretManager()
        # Register cleanup on module unload
        if not _cleanup_registered:
            atexit.register(cleanup_secret_manager)
            _cleanup_registered = True

    return _secret_manager_instance


def cleanup_secret_manager() -> None:
    """
    Clean up the global secret manager instance.

    Should be called on application shutdown to prevent resource leaks.
    """
    global _secret_manager_instance

    if _secret_manager_instance is not None:
        _secret_manager_instance.close()
        _secret_manager_instance = None
        logger.info("secret_manager_singleton_cleaned_up")

# src/utils/config.py
"""
Configuration Management

Handles application settings and Azure Key Vault integration for secrets.

Version: 1.0.0
"""
from pydantic_settings import BaseSettings
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from functools import lru_cache
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    """
    Application settings from environment variables.

    These are non-secret configuration values that can be stored
    in Function App settings or .env file.
    """

    # Azure Configuration
    KEYVAULT_URL: str
    AZURE_STORAGE_ACCOUNT_NAME: str  # For Managed Identity access
    AZURE_DEVOPS_ORG: str
    
    # AI Configuration
    OPENAI_MODEL: str = "gpt-4o"  # Model name or deployment name
    OPENAI_MAX_TOKENS: int = 4000
    
    # Application Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"
    
    # Azure AI Foundry (Recommended - set these for Azure OpenAI)
    AZURE_AI_ENDPOINT: Optional[str] = None  # e.g., https://your-resource.openai.azure.com
    AZURE_AI_DEPLOYMENT: Optional[str] = None  # Your deployment name (e.g., gpt-4o-review)
    
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

    def __init__(self):
        """Initialize Secret Manager with Managed Identity."""
        settings = get_settings()

        # Use DefaultAzureCredential for Managed Identity
        # Store credential to ensure proper cleanup
        self._credential = DefaultAzureCredential()

        self.client = SecretClient(
            vault_url=settings.KEYVAULT_URL,
            credential=self._credential
        )

        self._cache = {}

        logger.info(
            "secret_manager_initialized",
            vault_url=settings.KEYVAULT_URL
        )
    
    def get_secret(self, secret_name: str) -> str:
        """
        Get secret from Key Vault with caching.
        
        Secrets are cached in memory for the lifetime of the function instance.
        This reduces Key Vault API calls and improves performance.
        
        Args:
            secret_name: Name of secret in Key Vault (e.g., OPENAI-API-KEY)
            
        Returns:
            Secret value
            
        Raises:
            Exception: If secret doesn't exist or access denied
        """
        # Return from cache if available
        if secret_name in self._cache:
            logger.debug("secret_cache_hit", secret_name=secret_name)
            return self._cache[secret_name]
        
        # Fetch from Key Vault
        try:
            logger.debug("secret_fetch_start", secret_name=secret_name)
            
            secret = self.client.get_secret(secret_name)
            self._cache[secret_name] = secret.value
            
            logger.info(
                "secret_fetched",
                secret_name=secret_name,
                version=secret.properties.version
            )
            
            return secret.value
            
        except Exception as e:
            logger.error(
                "secret_fetch_failed",
                secret_name=secret_name,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def clear_cache(self):
        """Clear the secret cache."""
        self._cache.clear()
        logger.info("secret_cache_cleared")

    def close(self):
        """Close the credential to prevent resource leaks."""
        if hasattr(self, '_credential') and self._credential:
            self._credential.close()
            logger.info("secret_manager_credential_closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup."""
        self.close()
        return False


# Module-level singleton for backwards compatibility
_secret_manager_instance: Optional[SecretManager] = None


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
    global _secret_manager_instance

    if _secret_manager_instance is None:
        _secret_manager_instance = SecretManager()

    return _secret_manager_instance

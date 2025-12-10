# src/utils/table_storage.py
"""
Azure Table Storage Utilities

Helper functions for interacting with Azure Table Storage using Managed Identity.

Version: 2.7.6 - Enhanced OData sanitization, input validation, retry logic
"""
from azure.data.tables import TableServiceClient, TableClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import (
    ResourceExistsError,
    ServiceRequestError,
    HttpResponseError,
)
from typing import Dict, Any, Generator, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from src.utils.config import get_settings
from src.utils.constants import (
    REQUIRED_TABLES,
    TABLE_STORAGE_RETRY_ATTEMPTS,
    TABLE_STORAGE_RETRY_MIN_WAIT,
    TABLE_STORAGE_RETRY_MAX_WAIT,
    TABLE_STORAGE_BATCH_SIZE,
    RETRY_BACKOFF_MULTIPLIER,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Maximum OData value length (DoS protection)
MAX_ODATA_VALUE_LENGTH = 1000


def sanitize_odata_value(value: str, max_length: int = MAX_ODATA_VALUE_LENGTH) -> str:
    """
    Sanitize string value for use in OData query filters.

    Prevents OData injection attacks by validating and escaping values.

    Args:
        value: String value to sanitize
        max_length: Maximum allowed length (default: 1000)

    Returns:
        Sanitized string safe for use in OData queries

    Raises:
        TypeError: If value is not a string
        ValueError: If value contains null bytes or exceeds max length

    Example:
        >>> sanitize_odata_value("O'Reilly")
        "O''Reilly"
        >>> sanitize_odata_value("normal-repo-name")
        "normal-repo-name"

    Security Note:
        Always use this function when interpolating user-controlled values
        into OData query filters to prevent injection attacks.
    """
    if not isinstance(value, str):
        raise TypeError(f"Expected string, got {type(value).__name__}")

    # Check for null bytes (security)
    if "\x00" in value:
        raise ValueError("Value contains null bytes")

    # Check length to prevent DoS
    if len(value) > max_length:
        raise ValueError(f"Value exceeds maximum length of {max_length}")

    # Escape single quotes by doubling them (OData/SQL standard)
    return value.replace("'", "''")


def _is_transient_error(exception: Exception) -> bool:
    """Check if exception is a transient error worth retrying."""
    if isinstance(exception, ServiceRequestError):
        return True
    if isinstance(exception, HttpResponseError):
        # Retry on 5xx server errors and 429 rate limit
        return exception.status_code >= 500 or exception.status_code == 429
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    return False


class TableServiceClientManager:
    """
    Singleton manager for Table Service Client with proper resource management.

    Fixes resource leak by properly managing DefaultAzureCredential lifecycle.
    """

    _instance: Optional["TableServiceClientManager"] = None
    _credential: Optional[DefaultAzureCredential] = None
    _client: Optional[TableServiceClient] = None

    def __new__(cls) -> "TableServiceClientManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self) -> TableServiceClient:
        """
        Get or create Table Service client.

        Returns:
            TableServiceClient instance

        Raises:
            ValueError: If AZURE_STORAGE_ACCOUNT_NAME is not configured
        """
        if self._client is None:
            settings = get_settings()

            if not settings.AZURE_STORAGE_ACCOUNT_NAME:
                raise ValueError(
                    "AZURE_STORAGE_ACCOUNT_NAME environment variable not set"
                )

            # Create credential (will be reused)
            self._credential = DefaultAzureCredential()

            # Construct the table service endpoint
            table_endpoint = (
                f"https://{settings.AZURE_STORAGE_ACCOUNT_NAME}.table.core.windows.net"
            )

            self._client = TableServiceClient(
                endpoint=table_endpoint, credential=self._credential
            )

            logger.info(
                "table_service_client_created",
                storage_account=settings.AZURE_STORAGE_ACCOUNT_NAME,
                auth_method="managed_identity",
            )

        return self._client

    def close(self) -> None:
        """Close credential and client to prevent resource leaks."""
        if self._credential:
            self._credential.close()
            self._credential = None
        self._client = None
        logger.info("table_service_client_closed")


# Global singleton instance
_manager = TableServiceClientManager()


def get_table_service_client() -> TableServiceClient:
    """
    Get cached Table Service client using Managed Identity.

    Returns:
        TableServiceClient instance

    Raises:
        ValueError: If AZURE_STORAGE_ACCOUNT_NAME is not configured
    """
    return _manager.get_client()


def get_table_client(table_name: str) -> TableClient:
    """
    Get Table client for specific table.

    Args:
        table_name: Name of table (e.g., 'feedback', 'reviewhistory')

    Returns:
        TableClient instance for the specified table
    """
    service = get_table_service_client()
    return service.get_table_client(table_name)


@retry(
    stop=stop_after_attempt(TABLE_STORAGE_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=RETRY_BACKOFF_MULTIPLIER,
        min=TABLE_STORAGE_RETRY_MIN_WAIT,
        max=TABLE_STORAGE_RETRY_MAX_WAIT,
    ),
    retry=retry_if_exception(_is_transient_error),
    reraise=True,
)
def ensure_table_exists(table_name: str) -> None:
    """
    Create table if it doesn't exist with automatic retry on transient errors.

    This is idempotent - safe to call multiple times.

    Args:
        table_name: Name of table to create

    Raises:
        ValueError: If table_name is invalid
        RuntimeError: If table creation fails after retries
    """
    # Validate table name
    if not table_name:
        raise ValueError("table_name cannot be empty")
    if "\x00" in table_name or ".." in table_name:
        raise ValueError(f"Invalid table name: {table_name}")

    try:
        service = get_table_service_client()
        service.create_table_if_not_exists(table_name)

        logger.info("table_ensured", table_name=table_name)

    except Exception as e:
        # Any error is critical - fail fast
        logger.error(
            "table_creation_failed",
            table_name=table_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise RuntimeError(
            f"Failed to ensure table '{table_name}' exists: {str(e)}"
        ) from e


def ensure_all_tables_exist() -> None:
    """
    Ensure all required tables exist.

    Called during application startup to ensure database schema.

    Creates all tables required for v2.2.0:
    - feedback: Developer feedback on AI suggestions
    - reviewhistory: Historical PR review data
    - idempotency: Request deduplication (v2.2.0)
    - responsecache: AI response caching (v2.2.0)

    Raises:
        RuntimeError: If any required table cannot be created
    """
    failed_tables = []

    for table_name in REQUIRED_TABLES:
        try:
            ensure_table_exists(table_name)
        except Exception as e:
            logger.error(
                "table_initialization_failed", table_name=table_name, error=str(e)
            )
            failed_tables.append(table_name)

    if failed_tables:
        raise RuntimeError(
            f"Failed to initialize required tables: {', '.join(failed_tables)}"
        )

    logger.info(
        "all_tables_ensured", tables=REQUIRED_TABLES, count=len(REQUIRED_TABLES)
    )


def query_entities_paginated(
    table_client: TableClient,
    query_filter: Optional[str] = None,
    page_size: int = TABLE_STORAGE_BATCH_SIZE,
) -> Generator[Dict[str, Any], None, None]:
    """
    Query entities with pagination to avoid loading all results into memory.

    This is a generator that yields entities in batches, which is more memory-efficient
    than using list(query_entities(...)) for large datasets.

    Args:
        table_client: TableClient instance
        query_filter: Optional OData query filter
        page_size: Number of entities to fetch per page (default: 100)

    Yields:
        Entity dictionaries

    Example:
        >>> for entity in query_entities_paginated(table_client, "PartitionKey eq 'myrepo'"):
        >>>     process_entity(entity)
    """
    if query_filter:
        pages = table_client.query_entities(
            query_filter=query_filter, results_per_page=page_size
        ).by_page()
    else:
        pages = table_client.list_entities(results_per_page=page_size).by_page()

    for page in pages:
        for entity in page:
            yield entity


def cleanup_table_storage() -> None:
    """
    Cleanup table storage resources.

    Call this on application shutdown to prevent resource leaks.

    Note: This is a synchronous function that can be called from
    synchronous contexts like atexit handlers.
    """
    _manager.close()
    logger.info("table_storage_cleanup_completed")

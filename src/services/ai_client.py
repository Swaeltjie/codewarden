# src/services/ai_client.py
"""
AI Client for Code Review

Handles interactions with OpenAI API for code review analysis.
Includes retry logic, rate limiting, structured response parsing,
and circuit breaker protection.

Version: 2.6.5 - Type hints for inner functions
"""
import asyncio
from openai import AsyncOpenAI
from typing import Optional, Dict, List, Any
import json
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import openai

from src.utils.config import get_secret_manager, get_settings
from src.services.circuit_breaker import CircuitBreakerManager, CircuitBreakerError
from src.utils.constants import (
    AI_CLIENT_TIMEOUT,
    AI_REQUEST_TIMEOUT,
    MAX_PROMPT_LENGTH,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS,
    COST_PER_1K_PROMPT_TOKENS,
    COST_PER_1K_COMPLETION_TOKENS,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AIClient:
    """Client for Azure AI Foundry / OpenAI API code reviews with retry logic."""
    
    def __init__(self) -> None:
        self.secret_manager = get_secret_manager()
        self.settings = get_settings()
        self._client: Optional[AsyncOpenAI] = None
        self.use_azure: bool = bool(self.settings.AZURE_AI_ENDPOINT)
    
    @property
    def client(self) -> AsyncOpenAI:
        """Lazy-initialized OpenAI client with connection pooling."""
        if self._client is None:
            if self.use_azure:
                # Azure AI Foundry (Azure OpenAI)
                from openai import AsyncAzureOpenAI
                api_key = self.secret_manager.get_secret("AZURE-OPENAI-KEY")
                self._client = AsyncAzureOpenAI(
                    api_key=api_key,
                    api_version="2024-10-21",  # Latest GA version
                    azure_endpoint=self.settings.AZURE_AI_ENDPOINT,
                    max_retries=0,  # We handle retries ourselves with tenacity
                    timeout=float(AI_CLIENT_TIMEOUT)
                )
                logger.info(
                    "azure_ai_client_initialized",
                    endpoint=self.settings.AZURE_AI_ENDPOINT,
                    api_version="2024-10-21"
                )
            else:
                # Direct OpenAI API
                api_key = self.secret_manager.get_secret("OPENAI-API-KEY")
                self._client = AsyncOpenAI(
                    api_key=api_key,
                    max_retries=0,
                    timeout=float(AI_CLIENT_TIMEOUT)
                )
                logger.info("openai_client_initialized")
        
        return self._client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError
        )),
        reraise=True
    )
    async def review_code(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> Dict:
        """
        Review code using OpenAI API with automatic retry logic.
        
        Uses exponential backoff for retries on rate limits and timeouts.
        
        Args:
            prompt: Full review prompt with code and context
            model: Model to use (defaults to settings.OPENAI_MODEL)
            max_tokens: Max tokens in response (defaults to settings.OPENAI_MAX_TOKENS)
            
        Returns:
            Parsed JSON response from AI containing:
                - issues: List of found issues
                - recommendation: approve, request_changes, or comment
                - summary: Overall assessment
                
        Raises:
            openai.RateLimitError: If rate limited (retries automatically)
            openai.APIError: If API request fails after retries
            ValueError: If response is not valid JSON
        """
        model = model or self.settings.OPENAI_MODEL
        max_tokens = max_tokens or self.settings.OPENAI_MAX_TOKENS

        # Validate model parameter
        if not model or not isinstance(model, str) or not model.strip():
            logger.error("invalid_model_parameter", model=model)
            raise ValueError(
                "Invalid model parameter. Must be a non-empty string. "
                "Configure OPENAI_MODEL environment variable."
            )

        # Validate max_tokens
        if max_tokens <= 0 or max_tokens > 128000:
            logger.warning(
                "invalid_max_tokens",
                max_tokens=max_tokens,
                using_default=DEFAULT_MAX_TOKENS
            )
            max_tokens = DEFAULT_MAX_TOKENS

        # Validate prompt parameter (prevent memory exhaustion from huge prompts)
        if not prompt or not isinstance(prompt, str):
            logger.error("invalid_prompt_parameter", prompt_type=type(prompt).__name__)
            raise ValueError("Prompt must be a non-empty string")

        if len(prompt) > MAX_PROMPT_LENGTH:
            logger.error(
                "prompt_too_large",
                length=len(prompt),
                max_length=MAX_PROMPT_LENGTH
            )
            raise ValueError(
                f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters. "
                f"Current length: {len(prompt)}. Reduce PR size or use chunking."
            )

        # For Azure AI Foundry, model parameter is the deployment name
        # For direct OpenAI, it's the model name (e.g., gpt-4o)
        if self.use_azure:
            # Use AZURE_AI_DEPLOYMENT if set, otherwise fall back to OPENAI_MODEL
            deployment_name = getattr(self.settings, 'AZURE_AI_DEPLOYMENT', model)
            model = deployment_name
            logger.debug(
                "using_azure_deployment",
                deployment=deployment_name,
                endpoint=self.settings.AZURE_AI_ENDPOINT
            )
        
        # Estimate prompt tokens (rough approximation: 4 chars per token)
        prompt_tokens_estimate = len(prompt) // 4
        
        logger.info(
            "ai_review_started",
            model=model,
            use_azure=self.use_azure,
            prompt_length=len(prompt),
            estimated_tokens=prompt_tokens_estimate
        )
        
        try:
            # Get circuit breaker for OpenAI service
            breaker = await CircuitBreakerManager.get_breaker(
                service_name="openai",
                failure_threshold=DEFAULT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                timeout_seconds=DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS
            )

            # Define the API call function for circuit breaker
            async def make_api_call() -> Any:
                # Add per-request timeout to prevent hanging
                return await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert Infrastructure as Code and Configuration reviewer. "
                                    "You specialize in Terraform, Ansible, Azure Pipelines, and JSON configurations. "
                                    "Focus on security, best practices, and potential issues. "
                                    "Always respond with valid JSON."
                                )
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        temperature=DEFAULT_TEMPERATURE,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"}  # Enforce JSON response
                    ),
                    timeout=float(AI_REQUEST_TIMEOUT)
                )

            # Execute with circuit breaker protection
            response = await breaker.call(make_api_call)
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            
            # Calculate cost (approximate for GPT-4 Turbo)
            cost = (prompt_tokens * COST_PER_1K_PROMPT_TOKENS / 1000) + \
                   (completion_tokens * COST_PER_1K_COMPLETION_TOKENS / 1000)
            
            logger.info(
                "ai_review_completed",
                model=model,
                tokens_used=tokens_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost=f"${cost:.4f}"
            )
            
            # Parse JSON response
            try:
                result = json.loads(content)

                # Comprehensive response validation
                if not isinstance(result, dict):
                    logger.error("ai_response_not_dict", type=type(result).__name__)
                    raise ValueError("AI response must be a JSON object")

                # Validate required fields
                if 'issues' not in result:
                    logger.error("ai_response_missing_issues", keys=list(result.keys()))
                    raise ValueError("AI response missing required field: 'issues'")

                if 'recommendation' not in result:
                    logger.error("ai_response_missing_recommendation", keys=list(result.keys()))
                    raise ValueError("AI response missing required field: 'recommendation'")

                # Validate issues structure
                if not isinstance(result['issues'], list):
                    logger.error("ai_response_issues_not_list")
                    raise ValueError("AI response 'issues' must be a list")

                # Validate each issue has required fields
                for idx, issue in enumerate(result['issues']):
                    if not isinstance(issue, dict):
                        logger.error("ai_response_issue_not_dict", index=idx)
                        raise ValueError(f"Issue at index {idx} is not a dictionary")

                    required_issue_fields = ['severity', 'message', 'file_path', 'issue_type']
                    for field in required_issue_fields:
                        if field not in issue:
                            logger.error(
                                "ai_response_issue_missing_field",
                                index=idx,
                                field=field
                            )
                            raise ValueError(f"Issue at index {idx} missing required field: {field}")

                # Validate recommendation value
                valid_recommendations = ['approve', 'request_changes', 'comment']
                if result['recommendation'] not in valid_recommendations:
                    logger.warning(
                        "ai_response_invalid_recommendation",
                        value=result['recommendation'],
                        valid=valid_recommendations
                    )
                    result['recommendation'] = 'comment'  # Fallback to safe default

                # Add metadata
                result['_metadata'] = {
                    'tokens_used': tokens_used,
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'estimated_cost': cost,
                    'model': model
                }

                return result

            except json.JSONDecodeError as e:
                logger.error("ai_response_invalid_json", error_type=type(e).__name__)
                raise ValueError(f"AI returned invalid JSON: {str(e)}")

        except CircuitBreakerError as e:
            # Circuit breaker is open - fail fast
            logger.error(
                "openai_circuit_breaker_open",
                error=str(e),
                model=model
            )
            raise Exception(f"OpenAI service temporarily unavailable: {str(e)}")

        except openai.RateLimitError as e:
            retry_after = getattr(e, 'retry_after', DEFAULT_CIRCUIT_BREAKER_TIMEOUT_SECONDS)
            logger.warning(
                "openai_rate_limited",
                retry_after=retry_after,
                model=model
            )
            # Tenacity will retry automatically
            raise

        except openai.APITimeoutError as e:
            logger.warning(
                "openai_timeout",
                model=model,
                timeout=AI_CLIENT_TIMEOUT
            )
            # Tenacity will retry automatically
            raise
        
        except openai.APIConnectionError as e:
            logger.warning(
                "openai_connection_error",
                error=str(e)
            )
            # Tenacity will retry automatically
            raise
        
        except Exception as e:
            logger.exception(
                "ai_review_failed",
                error=str(e),
                error_type=type(e).__name__,
                model=model
            )
            raise
    
    async def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Count tokens for text using tiktoken library for accurate counts.

        Args:
            text: Text to count tokens for
            model: Model to use for counting (defaults to settings.OPENAI_MODEL)

        Returns:
            Token count
        """
        try:
            import tiktoken

            model = model or self.settings.OPENAI_MODEL

            # Get the appropriate encoding for the model
            # For Azure deployments, use the base model name
            if model.startswith('gpt-4'):
                encoding_name = 'cl100k_base'  # GPT-4, GPT-3.5-turbo
            elif model.startswith('gpt-3.5'):
                encoding_name = 'cl100k_base'
            else:
                # Default to cl100k_base for newer models
                encoding_name = 'cl100k_base'

            encoding = tiktoken.get_encoding(encoding_name)
            return len(encoding.encode(text))

        except ImportError:
            logger.warning("tiktoken_not_available", fallback_to_approximation=True)
            # Fallback to rough approximation if tiktoken not available
            return len(text) // 4
        except Exception as e:
            logger.warning("token_counting_failed", error=str(e), fallback_to_approximation=True)
            return len(text) // 4
    
    async def close(self) -> None:
        """Close the OpenAI client."""
        if self._client:
            try:
                await self._client.close()
                logger.debug("ai_client_closed")
            except Exception as e:
                logger.warning("ai_client_close_error", error=str(e))
            finally:
                self._client = None

    async def __aenter__(self) -> "AIClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Async context manager exit."""
        await self.close()
        return False  # Don't suppress exceptions

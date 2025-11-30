# tests/performance/test_benchmarks.py
"""
Performance Benchmarks

Measures performance of critical code paths to detect regressions.

Usage:
    pytest tests/performance/test_benchmarks.py --benchmark-only
    pytest tests/performance/test_benchmarks.py --benchmark-compare

Version: 2.2.0
"""
import pytest
import asyncio
from datetime import datetime, timezone

# Sample test data
SMALL_DIFF = """
--- a/main.tf
+++ b/main.tf
@@ -1,5 +1,6 @@
 resource "azurerm_resource_group" "example" {
   name     = "example-resources"
   location = "West Europe"
+  tags     = { Environment = "Production" }
 }
"""

MEDIUM_DIFF = SMALL_DIFF * 10  # ~100 lines
LARGE_DIFF = SMALL_DIFF * 100  # ~1000 lines


class TestDiffParsingBenchmarks:
    """Benchmarks for diff parsing operations."""

    @pytest.mark.benchmark(group="diff-parsing")
    def test_parse_small_diff(self, benchmark):
        """Benchmark parsing a small diff (~10 lines)."""
        from src.services.diff_parser import DiffParser

        parser = DiffParser()

        def parse_diff():
            return asyncio.run(parser.parse_diff(SMALL_DIFF))

        result = benchmark(parse_diff)
        assert len(result) > 0

    @pytest.mark.benchmark(group="diff-parsing")
    def test_parse_medium_diff(self, benchmark):
        """Benchmark parsing a medium diff (~100 lines)."""
        from src.services.diff_parser import DiffParser

        parser = DiffParser()

        def parse_diff():
            return asyncio.run(parser.parse_diff(MEDIUM_DIFF))

        result = benchmark(parse_diff)
        assert len(result) > 0

    @pytest.mark.benchmark(group="diff-parsing")
    def test_parse_large_diff(self, benchmark):
        """Benchmark parsing a large diff (~1000 lines)."""
        from src.services.diff_parser import DiffParser

        parser = DiffParser()

        def parse_diff():
            return asyncio.run(parser.parse_diff(LARGE_DIFF))

        result = benchmark(parse_diff)
        assert len(result) > 0


class TestCacheBenchmarks:
    """Benchmarks for response cache operations."""

    @pytest.mark.benchmark(group="cache")
    @pytest.mark.asyncio
    async def test_cache_hash_generation(self, benchmark):
        """Benchmark content hash generation for caching."""
        from src.models.reliability import CacheEntity

        def generate_hash():
            return CacheEntity.create_content_hash(
                diff_content=LARGE_DIFF,
                file_path="terraform/main.tf"
            )

        result = benchmark(generate_hash)
        assert len(result) == 64  # SHA256 hash length

    @pytest.mark.benchmark(group="cache")
    def test_cache_entity_creation(self, benchmark):
        """Benchmark cache entity creation."""
        from src.models.reliability import CacheEntity
        from src.models.review_result import ReviewResult

        review_result = ReviewResult(
            pr_id=12345,
            issues=[],
            recommendation="approve",
            summary="No issues found"
        )

        def create_entity():
            return CacheEntity.from_review_result(
                repository="my-repo",
                diff_content=MEDIUM_DIFF,
                file_path="main.tf",
                file_type="terraform",
                review_result=review_result,
                tokens_used=500,
                estimated_cost=0.0025,
                model_used="gpt-4o",
                ttl_days=7
            )

        result = benchmark(create_entity)
        assert result.PartitionKey == "my-repo"


class TestIdempotencyBenchmarks:
    """Benchmarks for idempotency checking operations."""

    @pytest.mark.benchmark(group="idempotency")
    def test_request_id_generation(self, benchmark):
        """Benchmark request ID generation."""
        from src.models.reliability import IdempotencyEntity

        def generate_id():
            return IdempotencyEntity.create_request_id(
                pr_id=12345,
                repository="my-repo",
                event_type="pr.updated",
                source_commit_id="abc123def456"
            )

        result = benchmark(generate_id)
        assert result.startswith("pr12345_")

    @pytest.mark.benchmark(group="idempotency")
    def test_idempotency_entity_creation(self, benchmark):
        """Benchmark idempotency entity creation."""
        from src.models.reliability import IdempotencyEntity

        def create_entity():
            return IdempotencyEntity.from_pr_event(
                pr_id=12345,
                repository="my-repo",
                project="my-project",
                event_type="pr.updated",
                source_commit_id="abc123",
                result_summary="approved: 0 issues"
            )

        result = benchmark(create_entity)
        assert result.pr_id == 12345


class TestTokenCountingBenchmarks:
    """Benchmarks for token counting and estimation."""

    @pytest.mark.benchmark(group="tokens")
    def test_token_estimation_small(self, benchmark):
        """Benchmark token estimation for small text."""
        from src.services.context_manager import ContextManager

        manager = ContextManager()

        def estimate_tokens():
            return manager._estimate_tokens_for_files([])

        benchmark(estimate_tokens)

    @pytest.mark.benchmark(group="tokens")
    def test_prompt_building(self, benchmark):
        """Benchmark prompt building for file review."""
        from src.prompts.factory import PromptFactory
        from src.models.pr_event import FileChange, FileType
        from src.services.diff_parser import DiffSection

        factory = PromptFactory()

        file_change = FileChange(
            path="main.tf",
            file_type=FileType.TERRAFORM,
            diff_content=MEDIUM_DIFF,
            changed_sections=[
                DiffSection(
                    start_line=1,
                    end_line=10,
                    added_lines=["  tags = { Environment = 'Production' }"],
                    removed_lines=[],
                    context_lines=[]
                )
            ]
        )

        def build_prompt():
            return factory.build_file_prompt(
                file=file_change,
                learning_context={"high_value_issue_types": ["SecurityIssue"]}
            )

        result = benchmark(build_prompt)
        assert "terraform" in result.lower()


class TestCircuitBreakerBenchmarks:
    """Benchmarks for circuit breaker operations."""

    @pytest.mark.benchmark(group="circuit-breaker")
    @pytest.mark.asyncio
    async def test_circuit_breaker_state_check(self, benchmark):
        """Benchmark circuit breaker state checking."""
        from src.services.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(
            service_name="test-service",
            failure_threshold=5,
            timeout_seconds=60
        )

        def check_state():
            return breaker.state.should_allow_request()

        result = benchmark(check_state)
        assert result is True

    @pytest.mark.benchmark(group="circuit-breaker")
    def test_circuit_breaker_success_recording(self, benchmark):
        """Benchmark success recording in circuit breaker."""
        from src.services.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker(
            service_name="test-service",
            failure_threshold=5,
            timeout_seconds=60
        )

        def record_success():
            breaker.state.record_success()

        benchmark(record_success)


class TestModelCreationBenchmarks:
    """Benchmarks for Pydantic model creation and validation."""

    @pytest.mark.benchmark(group="models")
    def test_review_result_creation(self, benchmark):
        """Benchmark ReviewResult model creation."""
        from src.models.review_result import ReviewResult, ReviewIssue

        def create_review():
            issues = [
                ReviewIssue(
                    severity="high",
                    message="Test issue",
                    file_path="main.tf",
                    line_number=10,
                    issue_type="SecurityIssue",
                    suggestion="Fix this"
                )
                for _ in range(10)
            ]

            return ReviewResult(
                pr_id=12345,
                issues=issues,
                recommendation="request_changes",
                summary="Found 10 issues"
            )

        result = benchmark(create_review)
        assert len(result.issues) == 10

    @pytest.mark.benchmark(group="models")
    def test_pr_event_parsing(self, benchmark):
        """Benchmark PREvent model parsing from webhook."""
        from src.models.pr_event import PREvent

        webhook_data = {
            "resource": {
                "pullRequestId": 12345,
                "title": "Test PR",
                "description": "Test description",
                "sourceRefName": "refs/heads/feature",
                "targetRefName": "refs/heads/main",
                "repository": {
                    "id": "repo-123",
                    "name": "my-repo",
                    "project": {
                        "id": "project-123",
                        "name": "my-project"
                    }
                },
                "createdBy": {
                    "displayName": "Test User"
                }
            },
            "eventType": "git.pullrequest.updated"
        }

        def parse_event():
            return PREvent.from_webhook(webhook_data)

        result = benchmark(parse_event)
        assert result.pr_id == 12345


# Performance thresholds (for regression detection)
PERFORMANCE_THRESHOLDS = {
    "diff-parsing": {
        "small": 0.001,   # 1ms
        "medium": 0.01,   # 10ms
        "large": 0.1      # 100ms
    },
    "cache": {
        "hash_generation": 0.001,  # 1ms
        "entity_creation": 0.001   # 1ms
    },
    "idempotency": {
        "request_id": 0.0001,      # 0.1ms
        "entity_creation": 0.001   # 1ms
    },
    "tokens": {
        "estimation": 0.001,       # 1ms
        "prompt_building": 0.01    # 10ms
    },
    "circuit_breaker": {
        "state_check": 0.0001,     # 0.1ms
        "record_success": 0.0001   # 0.1ms
    },
    "models": {
        "review_result": 0.001,    # 1ms
        "pr_event": 0.001          # 1ms
    }
}


def test_performance_thresholds_documented():
    """Ensure performance thresholds are documented for all benchmarks."""
    assert len(PERFORMANCE_THRESHOLDS) > 0
    assert "diff-parsing" in PERFORMANCE_THRESHOLDS
    assert "cache" in PERFORMANCE_THRESHOLDS
    assert "idempotency" in PERFORMANCE_THRESHOLDS

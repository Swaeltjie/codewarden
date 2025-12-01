# tests/test_diff_parser.py
"""
Unit tests for diff parser.
"""
import pytest
from src.services.diff_parser import DiffParser


class TestDiffParser:
    """Tests for DiffParser class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DiffParser()

    @pytest.mark.asyncio
    async def test_parse_simple_diff(self, sample_diff_content):
        """Test parsing a simple unified diff."""
        result = await self.parser.parse_diff(sample_diff_content)

        assert len(result) > 0
        section = result[0]

        # Verify section properties (diff parser returns path without leading slash)
        assert section.file_path == "main.tf"
        assert len(section.added_lines) > 0
        assert len(section.removed_lines) > 0

    @pytest.mark.asyncio
    async def test_parse_empty_diff(self):
        """Test parsing an empty diff."""
        result = await self.parser.parse_diff("")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_parse_malformed_diff(self):
        """Test parsing a malformed diff."""
        malformed = "not a valid diff"

        result = await self.parser.parse_diff(malformed)

        # Should handle gracefully, not crash
        assert isinstance(result, list)

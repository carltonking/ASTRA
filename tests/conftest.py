"""Shared test fixtures and configuration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_llm_provider_factory():
    """Mock create_llm_provider globally so it never tries real API calls."""
    mock_provider = MagicMock()
    mock_provider.generate.return_value = "mocked response"
    with patch("astra.ui.backend.main.create_llm_provider", return_value=mock_provider):
        yield

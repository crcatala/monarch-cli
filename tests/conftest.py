"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_fixture() -> str:
    """Sample fixture placeholder."""
    return "test"

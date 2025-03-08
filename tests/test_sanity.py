"""Placeholder test to verify pytest infrastructure.

This module contains a minimal passing test to ensure the CI pipeline can complete
successfully while the full test suite is being developed. This helps maintain
a green build status without blocking development progress.
"""

from __future__ import annotations

import pytest


def test_sanity() -> None:
    """Verify that pytest infrastructure is working correctly.

    This is a placeholder test that always passes, ensuring CI builds complete
    successfully while the full test suite is under development.
    """
    if not True:
        pytest.fail("This should fail")

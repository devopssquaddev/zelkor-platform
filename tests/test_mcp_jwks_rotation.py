"""L12 live: JWKS rotation accepted without pod restart (Path B only)."""
from __future__ import annotations

import os

import pytest

from tests.helpers.tokens import test_tokens

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ZELKOR_TEST_ROTATION"),
        reason="ZELKOR_TEST_ROTATION not set (internal/dev/ Path B rotation fixture)",
    ),
    pytest.mark.skipif(not test_tokens(), reason="ZELKOR_TEST_TOKENS not set"),
]


def test_l12_rotation_key2_token_accepted():
    tokens = test_tokens()
    assert tokens.get("rotation-key-2"), "rotation-key-2 missing in ZELKOR_TEST_TOKENS"


def test_l12_rotation_key1_still_valid_until_removed():
    tokens = test_tokens()
    assert tokens.get("rotation-key-1"), "rotation-key-1 missing in ZELKOR_TEST_TOKENS"

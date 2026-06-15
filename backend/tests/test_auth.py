from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domain.auth import verify_token


def test_verify_token_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        verify_token("")
    assert exc.value.status_code == 401


def test_verify_token_rejects_garbage():
    with pytest.raises(HTTPException) as exc:
        verify_token("not-a-valid-token")
    assert exc.value.status_code == 401

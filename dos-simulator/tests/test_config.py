"""Validation tests for SimulationConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import settings
from app.models.simulation import SimulationConfig


def base_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_url": "http://localhost:8001",
        "endpoint": "/data",
        "method": "GET",
        "total_requests": 1000,
        "target_rps": 100,
        "concurrency": 20,
        "timeout": 5,
    }
    payload.update(overrides)
    return payload


def test_valid_configuration_is_accepted() -> None:
    config = SimulationConfig(**base_payload())

    assert config.target_url == "http://localhost:8001"
    assert config.method == "GET"
    assert config.full_url == "http://localhost:8001/data"


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_url": "not-a-url"},
        {"target_url": "ftp://localhost:8001"},
        {"target_url": "localhost:8001"},
        {"endpoint": "data"},
        {"endpoint": ""},
        {"total_requests": 0},
        {"total_requests": -5},
        {"target_rps": 0},
        {"target_rps": -1},
        {"concurrency": 0},
        {"concurrency": -1},
        {"timeout": 0},
        {"timeout": -1},
        {"method": "DELETE"},
        {"method": "PUT"},
        {"total_requests": settings.MAX_TOTAL_REQUESTS + 1},
        {"target_rps": settings.MAX_RPS + 1},
        {"concurrency": settings.MAX_CONCURRENCY + 1},
        {"timeout": settings.MAX_TIMEOUT_SECONDS + 1},
        {"unknown_field": 1},
    ],
)
def test_invalid_configuration_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SimulationConfig(**base_payload(**overrides))


def test_method_is_case_insensitive() -> None:
    config = SimulationConfig(**base_payload(method="get"))

    assert config.method == "GET"


def test_post_method_is_supported() -> None:
    config = SimulationConfig(**base_payload(method="POST"))

    assert config.method == "POST"


def test_target_url_trailing_slash_is_normalized() -> None:
    config = SimulationConfig(**base_payload(target_url="http://localhost:8001/"))

    assert config.target_url == "http://localhost:8001"


def test_values_at_the_safety_limit_are_accepted() -> None:
    config = SimulationConfig(
        **base_payload(
            total_requests=settings.MAX_TOTAL_REQUESTS,
            target_rps=settings.MAX_RPS,
            concurrency=settings.MAX_CONCURRENCY,
        )
    )

    assert config.total_requests == settings.MAX_TOTAL_REQUESTS

"""Thin HTTP client wrapper used by simulation workers."""

from app.http.client import RequestOutcome, classify_status, send_request

__all__ = ["RequestOutcome", "classify_status", "send_request"]

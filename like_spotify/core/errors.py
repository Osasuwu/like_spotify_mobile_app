class AuthError(Exception):
    """Token expired or revoked. Host should trigger re-auth."""


class RateLimited(Exception):
    """Provider returned 429. Host should back off."""


class TransientError(Exception):
    """Network blip / 5xx. Host may retry with jitter."""

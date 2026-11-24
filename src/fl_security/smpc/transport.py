"""Transport validation and HTTPS-preserving HTTP helpers for MPC services."""
from __future__ import annotations

import ipaddress
import urllib.error
import urllib.parse
import urllib.request


def validate_transport_url(url: str) -> str:
    """Require TLS except for literal loopback URLs used by local simulations."""
    try:
        parsed = urllib.parse.urlsplit(url)
        hostname = parsed.hostname
    except (TypeError, ValueError) as exc:
        raise ValueError("MPC service URL is invalid") from exc
    if not hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("MPC service URL must include a host and no embedded credentials")
    if parsed.scheme == "https":
        return url
    if parsed.scheme == "http":
        normalized_host = hostname.rstrip(".").lower()
        try:
            is_loopback = ipaddress.ip_address(normalized_host).is_loopback
        except ValueError:
            is_loopback = normalized_host == "localhost"
        if is_loopback:
            return url
    raise ValueError("MPC service URLs must use HTTPS except for loopback HTTP")


class _SecureRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        if (
            urllib.parse.urlsplit(request.full_url).scheme == "https"
            and urllib.parse.urlsplit(new_url).scheme != "https"
        ):
            raise urllib.error.URLError("HTTPS MPC request cannot downgrade")
        validate_transport_url(new_url)
        return super().redirect_request(request, file, code, message, headers, new_url)


def urlopen_secure(request: urllib.request.Request, timeout: float):
    validate_transport_url(request.full_url)
    opener = urllib.request.build_opener(_SecureRedirectHandler())
    return opener.open(request, timeout=timeout)

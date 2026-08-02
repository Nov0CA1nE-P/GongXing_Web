#!/usr/bin/env python3
"""Reject local or loopback restic repositories without logging credentials."""

from __future__ import annotations

import ipaddress
import re
import socket
import sys
from urllib.parse import urlsplit


def repository_host(repository: str) -> tuple[str, int | None]:
    if not repository or repository != repository.strip():
        raise ValueError("malformed repository")
    if repository.startswith(("s3:https://", "s3:http://")):
        parsed = urlsplit(repository[3:])
    elif repository.startswith(("rest:https://", "rest:http://")):
        parsed = urlsplit(repository[5:])
    elif repository.startswith("s3:"):
        parsed = urlsplit("//" + repository[3:])
    elif repository.startswith("sftp:"):
        value = repository[5:]
        match = re.fullmatch(
            r"(?:(?P<user>[^@/:\[\]]+)@)?(?P<host>\[[^\]]+\]|[^/:]+)(?::(?P<port>\d+))?:(?P<path>/.*)",
            value,
        )
        if match is None:
            raise ValueError("malformed sftp repository")
        host = match.group("host")
        if host.startswith("["):
            host = host[1:-1]
        port = int(match.group("port")) if match.group("port") else 22
        return host, port
    else:
        raise ValueError("unsupported or local repository")
    if not parsed.hostname:
        raise ValueError("repository host is missing")
    return parsed.hostname, parsed.port


def resolved_addresses(host: str, port: int | None) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        direct = ipaddress.ip_address(host)
    except ValueError:
        direct = None
    if direct is not None:
        return {direct}
    records = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    if not records:
        raise ValueError("repository host did not resolve")
    return {ipaddress.ip_address(record[4][0].split("%", 1)[0]) for record in records}


def is_loopback(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_loopback:
        return True
    return isinstance(address, ipaddress.IPv6Address) and (
        address.ipv4_mapped is not None and address.ipv4_mapped.is_loopback
    )


def validate(repository: str) -> None:
    host, port = repository_host(repository)
    addresses = resolved_addresses(host, port)
    if any(is_loopback(address) for address in addresses):
        raise ValueError("loopback repository")


def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError("repository argument is required")
    validate(sys.argv[1])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("error: approved repository must be a resolvable non-loopback remote", file=sys.stderr)
        raise SystemExit(1) from None

import ipaddress
from urllib.parse import urlsplit


def normalize_origin(
    value: str,
    *,
    allow_path_and_query: bool = False,
) -> str | None:
    """将 HTTP(S) 来源规范化为小写主机并省略默认端口。"""
    if not value or "," in value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.netloc.endswith(":")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (
            not allow_path_and_query
            and (parsed.path or parsed.query)
        )
    ):
        return None
    if port is not None and not 1 <= port <= 65535:
        return None

    hostname = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            normalized_host = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    else:
        normalized_host = address.compressed
        if address.version == 6:
            normalized_host = f"[{normalized_host}]"

    effective_port = port if port is not None else (
        80 if scheme == "http" else 443
    )
    default_port = 80 if scheme == "http" else 443
    port_suffix = "" if effective_port == default_port else f":{effective_port}"
    return f"{scheme}://{normalized_host}{port_suffix}"

"""Build inactive bounded ASGI servers; activation belongs to Phase 8/9."""

import ipaddress

from discordbot.platform.errors import ConfigurationError
from discordbot.watch.adapters.web_runtime import WatchWebResource


def build_servers(resource: WatchWebResource, public_port: int, control_port: int, host: str = "127.0.0.1"):
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        if public_port == control_port or any(type(port) is not int or not 1024 <= port <= 65535 for port in (public_port, control_port)):
            raise ValueError
    except ValueError:
        raise ConfigurationError("Watch servers require distinct loopback ports") from None
    import uvicorn
    servers = []
    for app, port in ((resource.public_app, public_port), (resource.control_app, control_port)):
        config = uvicorn.Config(app, host=host, port=port, access_log=False, log_config=None,
            proxy_headers=False, ws_max_size=resource.service.limits.message_bytes, ws_max_queue=4,
            limit_concurrency=96, backlog=64, timeout_keep_alive=5, timeout_graceful_shutdown=5,
            lifespan="off")
        servers.append(uvicorn.Server(config))
    return tuple(servers)

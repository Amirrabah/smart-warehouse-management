from slowapi import Limiter
from starlette.requests import Request

from app.config import settings


def client_ip(request: Request) -> str:
    """The address to rate-limit on.

    Locally the socket address is the client. Behind a proxy (TRUST_PROXY_HEADERS=true, e.g. on
    Railway) the socket address is the proxy, so use the last X-Forwarded-For entry: that one is
    added by the proxy itself. Earlier entries come from the client and could be faked to dodge
    the limit, so they are ignored.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)

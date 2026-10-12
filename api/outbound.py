"""Public HTTPS-only webhook delivery with DNS pinning for user-provided URLs."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


def validate_webhook_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Webhook URL must use public HTTPS on port 443')
    return parsed


async def post_public_webhook(url, body, headers):
    parsed = validate_webhook_url(url)
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443, type=socket.SOCK_STREAM)
    ips = {entry[4][0] for entry in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Webhook destination must resolve to public IP addresses')
    ip = sorted(ips)[0]
    target = httpx.URL(url).copy_with(host=ip)
    headers = {**headers, 'Host': parsed.hostname}
    # Connect to the validated address while checking TLS against the URL hostname.
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        return await client.post(target, content=body, headers=headers,
                                 extensions={'sni_hostname': parsed.hostname})

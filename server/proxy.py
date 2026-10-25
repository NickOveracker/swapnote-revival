"""Optional HTTP proxy mode, so a 3DS can point its proxy setting at this server
(directly, or through a relay such as the Raspberry Pi in relay/).

Requests for our own server name are answered locally (hpp_server.py). Requests for
other hosts are passed through unchanged (plain HTTP, or CONNECT tunnels for HTTPS) if
the host matches [proxy] allow_hosts; hpp_server.py checks that before calling here.
Destinations are only logged in verbose mode.
"""
import http.client
import logging
import select
import socket
import urllib.parse

log = logging.getLogger('proxy')

HOP_BY_HOP = {'connection', 'keep-alive', 'proxy-authorization', 'proxy-connection',
              'te', 'trailer', 'transfer-encoding', 'upgrade'}


def tunnel(handler):
    """Handle CONNECT host:port by relaying bytes in both directions."""
    host, _, port = handler.path.rpartition(':')
    log.debug('proxy: CONNECT %s:%s from %s', host, port, handler.client_address[0])
    try:
        upstream = socket.create_connection((host, int(port)), timeout=15)
    except OSError as e:
        log.info('proxy: connect to %s failed: %s', host, e)
        handler.send_error(502)
        return
    handler.send_response(200, 'Connection established')
    handler.end_headers()
    handler.close_connection = True
    client = handler.connection
    socks = [client, upstream]
    try:
        while True:
            ready, _, broken = select.select(socks, [], socks, 120)
            if broken or not ready:
                break
            for s in ready:
                data = s.recv(65536)
                if not data:
                    return
                (upstream if s is client else client).sendall(data)
    except OSError:
        pass
    finally:
        upstream.close()


def forward(handler, body):
    """Forward an absolute-URI plain HTTP request to its real destination."""
    url = urllib.parse.urlsplit(handler.path)
    log.debug('proxy: %s %s from %s', handler.command, handler.path, handler.client_address[0])
    path = url.path or '/'
    if url.query:
        path += '?' + url.query
    headers = {k: v for k, v in handler.headers.items() if k.lower() not in HOP_BY_HOP}
    try:
        conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=30)
        conn.request(handler.command, path, body=body or None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
    except OSError as e:
        log.info('proxy: %s failed: %s', url.hostname, e)
        handler.send_error(502)
        return
    log.debug('proxy:   -> %d (%d bytes)', resp.status, len(data))
    handler.send_response(resp.status, resp.reason)
    for k, v in resp.getheaders():
        if k.lower() not in HOP_BY_HOP and k.lower() != 'content-length':
            handler.send_header(k, v)
    handler.send_header('Content-Length', str(len(data)))
    handler.end_headers()
    if handler.command != 'HEAD':
        handler.wfile.write(data)

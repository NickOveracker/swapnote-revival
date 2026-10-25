#!/usr/bin/env python3
"""Self-hosted HPP (NEX over HTTP) DataStore server for Swapnote friend notes.

The 3DS BOSS (SpotPass) module, patched by patches/0004013000003402-boss, sends
Swapnote's DataStore calls to http://hpp-00051600-l1.<server_name>/hpp/ and fetches its
SpotPass policy list from http://<server_name>/p01/policylist/... . This server answers
both, stores notes in the data directory, and can act as the HTTP proxy the consoles use
to reach it (see [proxy] in the config).

usage: hpp_server.py CONFIG.toml        (see server.example.toml)
"""
import base64
import hmac
import http.server
import logging
import socketserver
import struct
import sys
import threading
import time
import urllib.parse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config  # noqa: E402
import datastore  # noqa: E402
import policy  # noqa: E402
import proxy  # noqa: E402

log = logging.getLogger('hpp')

# Swapnote's NEX access key ("a1a0778a"), used to check request signature1.
ACCESS_KEY = bytes.fromhex('a1a0778a')
CORE_NOT_IMPLEMENTED = 0x80010002
MAX_BODY = datastore.MAX_OBJECT_SIZE + 64 * 1024      # note upload + multipart overhead
CLEANUP_INTERVAL = 3600

METHOD_NAMES = {1: 'PrepareGetObjectV1', 2: 'PreparePostObjectV1', 3: 'CompletePostObjectV1',
                13: 'GetNotificationUrl', 14: 'GetNewArrivedNotificationsV1',
                20: 'GetSpecificMetaV1'}


def parse_rmc(body):
    """Return (protocol, call_id, method_id, params) from an HPP RMC request body."""
    size, proto = struct.unpack_from('<IB', body)
    if size != len(body) - 4:
        raise ValueError(f'RMC size {size} != body {len(body) - 4}')
    if not proto & 0x80:
        raise ValueError('not an RMC request')
    proto &= 0x7f
    pos = 5
    if proto == 0x7f:
        proto, = struct.unpack_from('<H', body, pos)
        pos += 2
    call_id, method_id = struct.unpack_from('<II', body, pos)
    return proto, call_id, method_id, body[pos + 8:]


def rmc_response(call_id, method_id, data=None, error=None):
    """HPP RMC responses carry no protocol ID byte (unlike PRUDP)."""
    if error is None:
        payload = b'\x01' + struct.pack('<II', call_id, method_id | 0x8000) + data
    else:
        payload = b'\x00' + struct.pack('<II', error, call_id)
    return struct.pack('<I', len(payload)) + payload


def signature1_ok(rmc, header):
    """signature1 = HMAC-MD5 of the RMC message keyed with the hex-decoded access key."""
    want = hmac.new(ACCESS_KEY, rmc, 'md5').hexdigest()
    return hmac.compare_digest(want, (header or '').lower())


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'swapnote-hpp/1.0'
    protocol_version = 'HTTP/1.1'

    @property
    def cfg(self):
        return self.server.cfg

    def log_message(self, fmt, *args):
        log.debug('%s %s', self.address_string(), fmt % args)

    def _send(self, code, body=b'', ctype='application/octet-stream', headers=()):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self._send(413)
            self.close_connection = True
            return None
        return self.rfile.read(length)

    def _allowed_client(self):
        if self.cfg.client_allowed(self.client_address[0]):
            return True
        log.warning('refused client %s', self.client_address[0])
        self._send(403)
        self.close_connection = True
        return False

    def _proxy_auth_ok(self):
        if not self.cfg.proxy_username:
            return True
        want = base64.b64encode(f'{self.cfg.proxy_username}:{self.cfg.proxy_password}'
                                .encode()).decode()
        got = self.headers.get('Proxy-Authorization', '')
        if hmac.compare_digest(got.encode(), f'Basic {want}'.encode()):
            return True
        self._send(407, headers=[('Proxy-Authenticate', 'Basic realm="swapnote"')])
        self.close_connection = True
        return False

    def _record(self, body):
        if self.cfg.log_requests:
            self.server.store.record_request(self.command, self.path, dict(self.headers), body)

    def _own_host(self):
        host = self.headers.get('Host', '')
        return host if self.cfg.is_own_host(host) else self.cfg.server_name

    def proxied(self, body):
        """Handle proxy-style requests (absolute URI). Returns True if fully handled."""
        if not self.path.startswith('http://'):
            return False
        url = urllib.parse.urlsplit(self.path)
        if self.cfg.is_own_host(url.hostname):
            self.path = (url.path or '/') + ('?' + url.query if url.query else '')
            return False
        if not self.cfg.proxy_enabled or not self._proxy_auth_ok():
            if not self.cfg.proxy_enabled:
                self._send(403)
            return True
        if not self.cfg.proxy_host_allowed(url.hostname):
            log.info('proxy: refused http://%s', url.hostname)
            self._send(403)
            return True
        proxy.forward(self, body)
        return True

    def do_CONNECT(self):
        if not self._allowed_client():
            return
        host = self.path.rpartition(':')[0]
        if not self.cfg.proxy_enabled:
            return self._send(403)
        if not self._proxy_auth_ok():
            return
        if not self.cfg.proxy_host_allowed(host):
            log.info('proxy: refused CONNECT %s', host)
            return self._send(403)
        proxy.tunnel(self)

    def do_HEAD(self):
        if self._allowed_client() and not self.proxied(b''):
            self._send(404)

    def do_POST(self):
        if not self._allowed_client():
            return
        body = self._body()
        if body is None or self.proxied(body):
            return
        self._record(body)
        if self.path.rstrip('/') == '/hpp':
            return self.hpp(body)
        if self.path.startswith('/upload/'):
            return self._send(*self.server.store.http_upload(self.path, self.headers, body))
        self._send(404)

    def do_PUT(self):
        if not self._allowed_client():
            return
        body = self._body()
        if body is None or self.proxied(body):
            return
        self._record(body)
        if self.path.startswith('/upload/'):
            return self._send(*self.server.store.http_upload(self.path, self.headers, body))
        self._send(404)

    def do_GET(self):
        if not self._allowed_client() or self.proxied(b''):
            return
        self._record(b'')
        if self.path.startswith(('/object/', '/notify/')):
            return self._send(*self.server.store.http_download(self.path))
        if self.path.startswith('/p01/policylist/'):
            status, body = policy.policy_list(self.path)
            return self._send(status, body, 'application/xml; charset=utf-8')
        self._send(404)

    def hpp(self, body):
        rmc = datastore.parse_multipart(self.headers.get('Content-Type', ''), body).get('file')
        try:
            proto, call_id, method_id, params = parse_rmc(rmc or b'')
        except (ValueError, struct.error) as e:
            log.warning('bad HPP request from %s (%s)', self.client_address[0], e)
            return self._send(400)
        if not signature1_ok(rmc, self.headers.get('signature1')):
            log.warning('signature1 mismatch from %s (not Swapnote?)', self.client_address[0])
            return self._send(400)
        try:
            pid = int(self.headers.get('pid', '0'))
        except ValueError:
            return self._send(400)
        if not self.cfg.pid_allowed(pid):
            log.warning('refused console with friend PID %d (not in allowed_pids)', pid)
            return self._send(403)
        name = METHOD_NAMES.get(method_id, f'method {method_id}')
        log.debug('RMC pid=%d %s params=%s', pid, name, params.hex())
        ctx = datastore.Context(pid=pid, host=self._own_host(), store=self.server.store)
        try:
            data = datastore.dispatch(ctx, proto, method_id, params)
            resp = rmc_response(call_id, method_id, data=data)
            log.info('pid %d %s: ok', pid, name)
        except datastore.NexError as e:
            resp = rmc_response(call_id, method_id, error=e.code)
            log.info('pid %d %s: error %#010x (%s)', pid, name, e.code, e)
        except Exception:
            log.exception('pid %d %s: handler crashed', pid, name)
            resp = rmc_response(call_id, method_id, error=CORE_NOT_IMPLEMENTED)
        self._send(200, resp)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def cleanup_loop(store):
    while True:
        try:
            n = store.cleanup()
            if n:
                log.info('retention: deleted %d note(s)', n)
        except Exception:
            log.exception('retention cleanup failed')
        time.sleep(CLEANUP_INTERVAL)


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith('-'):
        sys.exit(__doc__)
    cfg = config.load(sys.argv[1])
    logging.basicConfig(level=logging.DEBUG if cfg.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    if not cfg.allowed_pids:
        log.warning('access.allowed_pids is empty: ANY console that reaches this server '
                    'can send and receive notes')
    if cfg.log_requests:
        log.warning('debug.log_requests is on: raw requests, including notes, are stored')

    srv = Server((cfg.bind, cfg.port), Handler)
    srv.cfg = cfg
    srv.store = datastore.Store(cfg.data, cfg)
    threading.Thread(target=cleanup_loop, args=(srv.store,), daemon=True).start()
    log.info('listening on %s:%d for %s (proxy %s), data in %s', cfg.bind, cfg.port,
             cfg.server_name, 'on' if cfg.proxy_enabled else 'off', cfg.data)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end test: fake a sender and a recipient console against a running server.

Expects the server to run with tests/test.toml (allowed PIDs 1111111111 and 2222222222).

Requests are built the way BOSS builds them (multipart 'file' field, HMAC-MD5
signature1 keyed with the access key), using the PreparePostObjectV1 parameter layout
seen in a real capture.  usage: flow_test.py [http://127.0.0.1:8080]
"""
import hmac
import pathlib
import struct
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from nex import Reader, Writer  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080'
KEY = bytes.fromhex('a1a0778a')
SENDER, RECIPIENT, STRANGER = 1111111111, 2222222222, 3333333333
OUTSIDER = 4044444444   # not on the server's allowlist
BOUNDARY = '--------BOUNDARY--------0123456789ABCDEF'
call = 0


# URLs the server hands out use its server_name; like a 3DS, reach them via the proxy.
VIA_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({'http': BASE}))


def http(method, url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    opener = urllib.request if url.startswith(BASE) else VIA_PROXY
    try:
        with opener.urlopen(req) if opener is urllib.request else opener.open(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def multipart(fields):
    out = b''
    for name, value in fields:
        out += (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                .encode() + value + b'\r\n')
    return out + f'--{BOUNDARY}--\r\n'.encode()


def rmc(pid, method_id, params):
    global call
    call += 1
    body = struct.pack('<B', 0x73 | 0x80) + struct.pack('<II', call, method_id) + params
    msg = struct.pack('<I', len(body)) + body
    status, resp = http('POST', BASE + '/hpp/', multipart([('file', msg)]), {
        'pid': str(pid), 'version': 'NEX_2_4_1_S25', 'token': 'normaltoken',
        'signature1': hmac.new(KEY, msg, 'md5').hexdigest().upper(),
        'signature2': '0' * 32,
        'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'})
    if status != 200:
        return status, None
    r = Reader(resp)
    assert r.u32() == len(resp) - 4
    if not r.u8():
        return r.u32(), None
    assert r.u32() == call and r.u32() == method_id | 0x8000
    return 0, r


def kv_list(r):
    return r.list(lambda r: (r.string(), r.string()))


note = b'swapnote test note ' * 100

# Sender: PreparePostObjectV1 with the field layout from the capture
p = (Writer().u32(len(note)).string('').u16(1).qbuffer(b'')
     .u8(2).list([RECIPIENT], Writer.u32)          # permission: Specified, [recipient]
     .u8(3).list([], Writer.u32)                   # delPermission: Private
     .u32(0x8).u16(30).u32(0).list([], Writer.string).u32(0)).bytes()
err, r = rmc(SENDER, 2, p)
assert not err, hex(err)
data_id, url = r.u32(), r.string()
req_headers, form = kv_list(r), kv_list(r)
r.buffer()
print('prepared', data_id, url, form)
status, _ = http('POST', url, multipart([(k, v.encode()) for k, v in form] + [('file', note)]),
                 {'Content-Type': f'multipart/form-data; boundary={BOUNDARY}'})
assert status == 204, status
err, _ = rmc(SENDER, 3, Writer().u32(data_id).bool(True).bytes())
assert not err, hex(err)
err, _ = rmc(SENDER, 3, Writer().u32(data_id).bool(True).bytes())
assert err == 0x80690001, 'second completion must fail'

# Recipient: notification URL + file
err, r = rmc(RECIPIENT, 13, Writer().string('').bytes())
assert not err
nurl = r.string() + r.string() + r.string()
status, body = http('GET', nurl)
print('notification file', nurl, body)
latest = int(body.split(b',')[0])
assert latest >= 100000000

err, r = rmc(RECIPIENT, 14, Writer().u64(0).u16(10).bytes())
notes = r.list(lambda r: (r.u64(), r.u32()))
has_next = r.u8()
print('new arrivals', notes, has_next)
assert (latest, data_id) in notes

err, r = rmc(RECIPIENT, 20, Writer().list([data_id], Writer.u32).bytes())
metas = r.list(lambda r: (r.u32(), r.u32(), r.u32(), r.u16(), r.u16()))
assert metas == [(data_id, SENDER, len(note), 1, 0)], metas

err, r = rmc(RECIPIENT, 1, Writer().u32(data_id).u32(0).bytes())
assert not err
gurl, _, size = r.string(), kv_list(r), r.u32()
status, got = http('GET', gurl)
assert status == 200 and got == note and size == len(note)

# An allowed console that is not a recipient may not read it
err, _ = rmc(STRANGER, 1, Writer().u32(data_id).u32(0).bytes())
assert err == 0x80690003, hex(err)
err, r = rmc(STRANGER, 14, Writer().u64(0).u16(10).bytes())
assert r.list(lambda r: (r.u64(), r.u32())) == []

# A console that is not on the allowlist is refused outright
err, _ = rmc(OUTSIDER, 14, Writer().u64(0).u16(10).bytes())
assert err == 403, err
assert http('GET', f'{BASE}/notify/{OUTSIDER}')[0] == 404

# Notes to recipients outside the allowlist are refused
p_out = (Writer().u32(len(note)).string('').u16(1).qbuffer(b'')
         .u8(2).list([OUTSIDER], Writer.u32).u8(3).list([], Writer.u32)
         .u32(0x8).u16(30).u32(0).list([], Writer.string).u32(0)).bytes()
err, _ = rmc(SENDER, 2, p_out)
assert err == 0x80690003, hex(err)

# Proxying to hosts outside allow_hosts is refused (absolute-URI request, as a 3DS sends)
import http.client as httpclient  # noqa: E402
u = urllib.parse.urlsplit(BASE)
c = httpclient.HTTPConnection(u.hostname, u.port)
c.request('GET', 'http://example.com/')
assert c.getresponse().status == 403
c = httpclient.HTTPConnection(u.hostname, u.port)
c.request('GET', 'http://hpp-00051600-l1.test.invalid/notify/2222222222')
assert c.getresponse().status == 200, 'own server name must be served via the proxy path'

# Unknown method -> NotImplemented
err, _ = rmc(SENDER, 8, b'')
assert err == 0x80010002, hex(err)
print('ALL OK')

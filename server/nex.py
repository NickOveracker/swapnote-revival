# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal NEX encoding helpers (little-endian) for the HPP DataStore server.

Only what Swapnote's SpotPass tasks need. NEX version here is 2.4.1, which predates
structure headers, so Structures are encoded as their plain fields.
"""
import struct
import time


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError('truncated NEX data')
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def _unpack(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def u8(self): return self._unpack('B')
    def u16(self): return self._unpack('H')
    def u32(self): return self._unpack('I')
    def u64(self): return self._unpack('Q')
    def s32(self): return self._unpack('i')
    def bool(self): return self.u8() != 0

    def string(self):
        n = self.u16()
        return self.take(n).rstrip(b'\0').decode('utf-8', 'replace') if n else ''

    def buffer(self):
        return self.take(self.u32())

    def qbuffer(self):
        return self.take(self.u16())

    def list(self, item):
        return [item(self) for _ in range(self.u32())]

    def remaining(self):
        return self.data[self.pos:]


class Writer:
    def __init__(self):
        self.out = bytearray()

    def _pack(self, fmt, v):
        self.out += struct.pack('<' + fmt, v)
        return self

    def u8(self, v): return self._pack('B', v)
    def u16(self, v): return self._pack('H', v)
    def u32(self, v): return self._pack('I', v)
    def u64(self, v): return self._pack('Q', v)
    def s32(self, v): return self._pack('i', v)
    def bool(self, v): return self.u8(1 if v else 0)

    def string(self, s):
        raw = s.encode('utf-8') + b'\0'
        self.u16(len(raw))
        self.out += raw
        return self

    def buffer(self, b):
        self.u32(len(b))
        self.out += b
        return self

    def qbuffer(self, b):
        self.u16(len(b))
        self.out += b
        return self

    def list(self, items, write):
        self.u32(len(items))
        for item in items:
            write(self, item)
        return self

    def raw(self, b):
        self.out += b
        return self

    def bytes(self):
        return bytes(self.out)


def datetime(t=None):
    """NEX DateTime (u64 bit-packed calendar time, UTC)."""
    tm = time.gmtime(time.time() if t is None else t)
    return (tm.tm_sec | tm.tm_min << 6 | tm.tm_hour << 12 | tm.tm_mday << 17
            | tm.tm_mon << 22 | tm.tm_year << 26)

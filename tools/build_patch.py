#!/usr/bin/env python3
"""Build Luma3DS code.ips files from the commented assembly sources in patches/.

Layout: one folder per patched title, named <TitleID>-<name>, e.g.
    patches/0004000000051700-swapnote/01-service-status.s
    patches/0004013000003402-boss/01-hpp-redirect.s
Each folder becomes the IPS file at the path Luma3DS (13.x) loads it from, under
build/sd/ (copy the contents of build/sd/ to the root of the SD card):
    games:          luma/titles/<TitleID>/code.ips  (needs "Enable game patching")
    system modules: luma/sysmodules/<TitleID>.ips   (needs "Enable loading external FIRMs
                    and modules"; see Luma3DS sysmodules/loader/source/patcher.c)

Patch source format (ARM, GNU-style '@' comments):

    .thumb                 @ optional: assemble following blocks as Thumb (default ARM)
    .org 0x001d874c        @ virtual address in the module's code (base 0x100000)
        mov r0, #1
        bx  lr
    .org 0x00147e59
        .server 23         @ the --server value as ASCII, NUL-padded to 23 bytes
        .server 36 http:// @ same, with a fixed prefix

Each `.org` starts a new block; the lines that follow are assembled at that address
with Keystone and become one IPS record. `.server N` is the only non-Keystone
directive (an optional second argument is a fixed text prefix). Nothing from the original modules is read while building, so the output
contains only bytes produced from these sources (plus the --server text you supply).

usage: build_patch.py --server NAME [--pretendo] [--without PATCH ...]
                      [--check FILE...] [--apply FILE OUT]
  --server    the name of your Swapnote server, as set in server.toml (server_name)
  --pretendo  for consoles that use Pretendo Network (Nimbus): leave out the policy-list
              redirect, Pretendo's own policy list already allows SpotPass tasks
  --without   leave out patches by file name, e.g. --without 03-ink-colour-lr
              (patches 03 and 04 are optional extras)
  --check     verify that decompressed code files are the exact builds these patches
              target (optional; see tools/gm9/check_versions.gm9 for an on-console check)
  --apply     also write a patched copy of a code file (for local testing / disassembly)
"""
import argparse
import hashlib
import pathlib
import re
import struct
import sys

from keystone import KS_ARCH_ARM, KS_MODE_ARM, KS_MODE_THUMB, Ks

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATCH_DIR = ROOT / 'patches'
BUILD_DIR = ROOT / 'build' / 'sd'
TEXT_BASE = 0x100000

# SHA-256 of the decompressed .code of every build we patch. Patches are only valid
# for these exact builds.
TARGETS = {
    # Swapnote US v3.3.0 (TMD version 3120)
    '0004000000051700': '83f38eab63efa6ed7d5cf7feb1977bda4a2005b17c61fcea57552bcaf84ac108',
    # BOSS (SpotPass) system module, TMD version 14337 (system update 11.17.0)
    '0004013000003402': '0243e1dfe80fb477fd77b21a509f346f5434bf667ff28b927779b640053ec434',
}

# Characters allowed in --server: a DNS name, optionally with :port.
SERVER_RE = re.compile(r'[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:[0-9]{1,5})?')


def parse(path):
    """Yield (address, thumb, lines, source_location) blocks from one patch source."""
    addr, thumb, lines, start = None, False, [], 0
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split('@', 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r'\.org\s+(0x[0-9a-fA-F]+)', line)
        if m or line in ('.thumb', '.arm'):
            if addr is not None:
                yield addr, thumb, lines, f'{path.name}:{start}'
                addr = None
            if m:
                addr, lines, start = int(m.group(1), 16), [], n
            else:
                thumb = line == '.thumb'
        elif addr is None:
            sys.exit(f'{path.name}:{n}: instruction before any .org')
        else:
            lines.append(line)
    if addr is not None:
        yield addr, thumb, lines, f'{path.name}:{start}'


def assemble(addr, thumb, lines, where, server):
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB if thumb else KS_MODE_ARM)
    out = bytearray()
    pending = []

    def flush():
        if pending:
            encoding, _ = ks.asm('\n'.join(pending), addr + len(out))
            out.extend(encoding or b'')
            pending.clear()

    for line in lines:
        m = re.fullmatch(r'\.server\s+(\d+)(?:\s+(\S+))?', line)
        if not m:
            pending.append(line)
            continue
        flush()
        size = int(m.group(1))
        if server is None:
            sys.exit(f'{where}: this patch needs --server')
        text = (m.group(2) or '') + server
        if len(text) >= size:
            sys.exit(f'--server is too long for {where} (at most {size - 1} characters'
                     f' including the prefix {m.group(2) or ""!r})')
        out += text.encode('ascii').ljust(size, b'\0')
    flush()
    if not out:
        sys.exit(f'{where}: empty block')
    return bytes(out)


# Patches that are not needed (or not wanted) for every setup.
OPTIONAL = {'03-ink-colour-lr', '04-unlock-stationery', '02-policylist-redirect'}
PRETENDO_SKIP = {'02-policylist-redirect'}


def build(server, without=frozenset()):
    """Return {title_id: [(addr, bytes, where), ...]} for every patch folder."""
    result = {}
    for folder in sorted(p for p in PATCH_DIR.iterdir() if p.is_dir()):
        tid = folder.name.split('-', 1)[0]
        if tid not in TARGETS:
            sys.exit(f'{folder.name}: unknown title ID (add it to TARGETS)')
        records = []
        for path in sorted(folder.glob('*.s')):
            if path.stem in without:
                print(f'skipping {folder.name}/{path.name}')
                continue
            for addr, thumb, lines, where in parse(path):
                records.append((addr, assemble(addr, thumb, lines, where, server), where))
        records.sort()
        for (a1, d1, w1), (a2, _, w2) in zip(records, records[1:]):
            if a1 + len(d1) > a2:
                sys.exit(f'overlapping patches: {w1} and {w2}')
        result[tid] = records
    return result


def ips_path(tid):
    """Path (relative to the SD card root) where Luma3DS looks for this title's IPS."""
    if tid.startswith('00040130'):
        return f'luma/sysmodules/{tid.upper()}.ips'
    return f'luma/titles/{tid.upper()}/code.ips'


def to_ips(records):
    out = bytearray(b'PATCH')
    for addr, data, _ in records:
        off = addr - TEXT_BASE
        if not 0 <= off < 0x1000000 or len(data) > 0xFFFF:
            sys.exit(f'record at {addr:#x} out of IPS range')
        out += off.to_bytes(3, 'big') + struct.pack('>H', len(data)) + data
    out += b'EOF'
    return bytes(out)


def identify(code_path):
    """Return the title ID whose supported build matches this file, or exit."""
    digest = hashlib.sha256(pathlib.Path(code_path).read_bytes()).hexdigest()
    for tid, want in TARGETS.items():
        if digest == want:
            print(f'{code_path}: matches supported build of {tid}')
            return tid
    sys.exit(f'{code_path}: SHA-256 {digest} does not match any supported build')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--server', required=True)
    ap.add_argument('--pretendo', action='store_true')
    ap.add_argument('--without', nargs='+', default=[], metavar='PATCH')
    ap.add_argument('--check', nargs='+', default=[])
    ap.add_argument('--apply', nargs=2, metavar=('CODE', 'OUT'))
    args = ap.parse_args()
    if args.server is not None and not SERVER_RE.fullmatch(args.server):
        sys.exit('--server must be a lowercase host name, optionally with :port')

    without = set(args.without) | (PRETENDO_SKIP if args.pretendo else set())
    unknown = without - OPTIONAL
    if unknown:
        sys.exit(f'--without: not an optional patch: {", ".join(sorted(unknown))} '
                 f'(optional: {", ".join(sorted(OPTIONAL))})')
    import shutil
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    built = build(args.server, without)
    for tid, records in built.items():
        for addr, data, where in records:
            shown = data.hex() if len(data) <= 16 else data[:16].hex() + '…'
            print(f'{tid}  {addr:#010x}  {len(data):3d} bytes  {shown}  ({where})')
        out = BUILD_DIR / ips_path(tid)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(to_ips(records))
        print(f'wrote {out.relative_to(ROOT)}')
    print(f'\nCopy everything inside {BUILD_DIR.relative_to(ROOT)}/ to the root of your SD card.')

    for path in args.check:
        identify(path)
    if args.apply:
        src, dst = args.apply
        tid = identify(src)
        code = bytearray(pathlib.Path(src).read_bytes())
        for addr, data, _ in built[tid]:
            code[addr - TEXT_BASE:addr - TEXT_BASE + len(data)] = data
        pathlib.Path(dst).write_bytes(code)
        print(f'wrote patched copy {dst}')


if __name__ == '__main__':
    main()

"""DataStore protocol (NEX protocol 0x73) handlers and note storage.

BOSS (NEX 2.4.1) uses the V1 methods. Flow of a friend note (confirmed on hardware;
it matches a public capture of the same BOSS code uploading a Swapdoodle note, see
docs/HOW-IT-WORKS.md):

  sender:     PreparePostObjectV1 -> HTTP POST of the note to the URL we return
              -> CompletePostObjectV1
  recipient:  GetNotificationUrl -> HTTP GET of a small notification file
              -> GetNewArrivedNotificationsV1 -> GetSpecificMetaV1
              -> PrepareGetObjectV1 -> HTTP GET of the note

Storage layout under the data directory:
    swapnote.db        SQLite: objects, notifications, deliveries (+ optional debug log)
    objects/<id>.bin   note data exactly as uploaded by the console

Privacy: note files are deleted after delivery (plus a grace period for retries) or after
a maximum age (see [retention] in the config). Object and notification rows are kept
(without note data) so IDs only ever increase: consoles remember the last notification
ID they saw, and a reused ID would make them miss a note.
"""
import dataclasses
import hmac
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse

from nex import Reader, Writer

log = logging.getLogger('datastore')

DATASTORE = 0x73

# Error codes are sent with bit 31 set.
NOT_IMPLEMENTED = 0x80010002     # Core::NotImplemented
INVALID_ARGUMENT = 0x8001000A    # Core::InvalidArgument
DS_UNKNOWN = 0x80690001          # DataStore::Unknown
DS_PERMISSION_DENIED = 0x80690003
DS_NOT_FOUND = 0x80690004

PERMISSION_SPECIFIED = 2
FIRST_NOTIFICATION_ID = 100000000   # low IDs reportedly confuse clients
FIRST_DATA_ID = 1000000

# Third field of the notification file. Its meaning is unknown (it looks like a Unix
# timestamp; other games' servers use a fixed value). Kept fixed.
NOTIFICATION_FILE_CONSTANT = 1479103557

MAX_OBJECT_SIZE = 4 * 1024 * 1024
INCOMPLETE_UPLOAD_HOURS = 6         # unfinished uploads are discarded after this
DELETED = -2                        # objects.completed value once the note data is gone


class NexError(Exception):
    def __init__(self, code, msg=''):
        super().__init__(msg or f'{code:#x}')
        self.code = code


@dataclasses.dataclass
class Context:
    pid: int
    host: str
    store: 'Store'

    def url(self, path):
        return f'http://{self.host}/{path}'


class Store:
    def __init__(self, root, cfg=None):
        self.root = root
        self.cfg = cfg
        (root / 'objects').mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(root / 'swapnote.db', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(f'''
            CREATE TABLE IF NOT EXISTS objects (
                id INTEGER PRIMARY KEY,
                owner INTEGER NOT NULL,
                recipients TEXT NOT NULL,         -- JSON list of PIDs
                data_type INTEGER NOT NULL,
                size INTEGER NOT NULL,
                flag INTEGER NOT NULL,
                period INTEGER NOT NULL,
                secret TEXT NOT NULL,             -- authorises the HTTP upload/download
                param BLOB NOT NULL,              -- unused (kept empty)
                created REAL NOT NULL,
                uploaded INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0  -- 0 open, 1 done, -1 failed, -2 deleted
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                data_id INTEGER NOT NULL,
                pid INTEGER NOT NULL,
                t REAL NOT NULL,
                PRIMARY KEY (data_id, pid)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY,
                pid INTEGER NOT NULL,
                data_id INTEGER NOT NULL,
                created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requests (
                t REAL, method TEXT, path TEXT, headers TEXT, body BLOB
            );
            INSERT OR IGNORE INTO objects (id, owner, recipients, data_type, size, flag,
                period, secret, param, created, completed)
                VALUES ({FIRST_DATA_ID - 1}, 0, '[]', 0, 0, 0, 0, '', x'', 0, -1);
            INSERT OR IGNORE INTO notifications VALUES ({FIRST_NOTIFICATION_ID - 1}, 0, 0, 0);
        ''')
        self.db.commit()

    def sql(self, query, *args):
        with self.lock:
            cur = self.db.execute(query, args)
            self.db.commit()
            return cur

    def record_request(self, method, path, headers, body):
        if not (self.cfg and self.cfg.log_requests):
            return
        self.sql('INSERT INTO requests VALUES (?,?,?,?,?)',
                 time.time(), method, path, json.dumps(headers), body)

    def add_completed(self, owner, recipients, data, data_type=1, flag=0x8, period=90):
        """Store a finished object and notify its recipients (used by tests and admin.py)."""
        data_id = self.sql(
            'INSERT INTO objects (owner, recipients, data_type, size, flag, period, secret,'
            ' param, created, uploaded, completed) VALUES (?,?,?,?,?,?,?,?,?,1,1)',
            owner, json.dumps(recipients), data_type, len(data), flag, period,
            secrets.token_hex(16), b'', time.time()).lastrowid
        self.path(data_id).write_bytes(data)
        for pid in recipients:
            self.sql('INSERT INTO notifications (pid, data_id, created) VALUES (?,?,?)',
                     pid, data_id, time.time())
        return data_id

    def obj(self, data_id):
        row = self.sql('SELECT * FROM objects WHERE id=? AND completed>=0', data_id).fetchone()
        if row is None:
            raise NexError(DS_NOT_FOUND, f'no object {data_id}')
        return row

    def path(self, data_id):
        return self.root / 'objects' / f'{data_id}.bin'

    # ---- plain HTTP endpoints (URLs handed out by the DataStore methods) ----

    def http_upload(self, path, headers, body):
        """POST /upload/<id>: multipart form with our 'secret' field and the 'file'."""
        m = re.fullmatch(r'/upload/(\d+)', path)
        if not m:
            return 404, b''
        fields = parse_multipart(headers.get('Content-Type', ''), body)
        row = self.sql('SELECT * FROM objects WHERE id=?', int(m.group(1))).fetchone()
        if (row is None or row['completed']
                or not hmac.compare_digest(fields.get('secret', b''), row['secret'].encode())):
            return 403, b''
        data = fields.get('file')
        if data is None or len(data) > MAX_OBJECT_SIZE:
            return 400, b''
        self.path(row['id']).write_bytes(data)
        self.sql('UPDATE objects SET uploaded=1, size=? WHERE id=?', len(data), row['id'])
        return 204, b''

    def http_download(self, path):
        """GET /object/<id>?s=<secret> and GET /notify/<pid>."""
        url = urllib.parse.urlsplit(path)
        q = urllib.parse.parse_qs(url.query)
        m = re.fullmatch(r'/object/(\d+)', url.path)
        if m:
            row = self.sql('SELECT * FROM objects WHERE id=? AND completed=1',
                           int(m.group(1))).fetchone()
            if row is None or not hmac.compare_digest(q.get('s', [''])[0].encode(),
                                                      row['secret'].encode()):
                return 404, b''
            return 200, self.path(row['id']).read_bytes()
        m = re.fullmatch(r'/notify/(\d+)', url.path)
        if m:
            pid = int(m.group(1))
            if self.cfg and not self.cfg.pid_allowed(pid):
                return 404, b''
            last = self.sql('SELECT max(id) FROM notifications WHERE pid=?', pid).fetchone()[0]
            body = f'{last or 0},{pid},{NOTIFICATION_FILE_CONSTANT}'.encode()
            return 200, body
        return 404, b''

    def mark_prepared(self, data_id, pid):
        """A recipient asked for the note's download URL; count it as delivered."""
        self.sql('INSERT OR IGNORE INTO deliveries VALUES (?,?,?)', data_id, pid, time.time())

    def delete_object(self, data_id):
        self.path(data_id).unlink(missing_ok=True)
        self.sql("UPDATE objects SET completed=?, secret='', param=x'' WHERE id=?",
                 DELETED, data_id)

    def cleanup(self, now=None):
        """Delete note data that is delivered (after the grace period), too old, or never
        finished uploading. Returns the number of notes deleted."""
        now = time.time() if now is None else now
        grace = (self.cfg.delivered_grace_hours if self.cfg else 24) * 3600
        max_age = (self.cfg.max_age_days if self.cfg else 30) * 86400
        doomed = []
        for row in self.sql('SELECT * FROM objects WHERE completed IN (0, 1, -1) AND id >= ?',
                            FIRST_DATA_ID).fetchall():
            if row['completed'] == 0 and now - row['created'] > INCOMPLETE_UPLOAD_HOURS * 3600:
                doomed.append(row['id'])
            elif row['completed'] == -1 or now - row['created'] > max_age:
                doomed.append(row['id'])
            elif row['completed'] == 1:
                recipients = set(json.loads(row['recipients']))
                got = {r['pid']: r['t'] for r in self.sql(
                    'SELECT pid, t FROM deliveries WHERE data_id=?', row['id'])}
                if recipients and recipients <= got.keys() and now - max(got.values()) > grace:
                    doomed.append(row['id'])
        for data_id in doomed:
            self.delete_object(data_id)
        if self.cfg and self.cfg.log_requests:
            self.sql('DELETE FROM requests WHERE t < ?', now - max_age)
        return len(doomed)


def parse_multipart(content_type, body):
    """Return {name: bytes} from a multipart/form-data body (no files with filenames needed)."""
    m = re.search(r'boundary=("?)([^";]+)\1', content_type)
    if not m:
        return {}
    sep = b'--' + m.group(2).encode()
    fields = {}
    for part in body.split(sep)[1:]:
        if part.startswith(b'--'):
            break
        head, _, value = part.partition(b'\r\n\r\n')
        name = re.search(rb'name="([^"]*)"', head)
        if name:
            fields[name.group(1).decode()] = value[:-2] if value.endswith(b'\r\n') else value
    return fields


# ---- RMC method handlers ----

HANDLERS = {}


def method(method_id):
    def register(fn):
        HANDLERS[method_id] = fn
        return fn
    return register


def dispatch(ctx, proto, method_id, params):
    if proto != DATASTORE or method_id not in HANDLERS:
        raise NexError(NOT_IMPLEMENTED, f'protocol {proto:#x} method {method_id}')
    w = Writer()
    HANDLERS[method_id](ctx, Reader(params), w)
    return w.bytes()


def read_permission(r):
    return r.u8(), r.list(Reader.u32)


def write_key_values(w, pairs):
    w.list(pairs, lambda w, kv: w.string(kv[0]).string(kv[1]))


def can_read(row, pid):
    return row['owner'] == pid or pid in json.loads(row['recipients'])


@method(2)
def prepare_post_object_v1(ctx, r, w):
    size = r.u32()
    r.string()                      # name
    data_type = r.u16()
    r.qbuffer()                     # metaBinary
    perm, recipients = read_permission(r)
    read_permission(r)              # delPermission
    flag = r.u32()
    period = r.u16()
    r.u32()                         # referDataId
    r.list(Reader.string)           # tags
    if r.u32():                     # ratingInitParams
        raise NexError(INVALID_ARGUMENT, 'ratings not supported')
    if size > MAX_OBJECT_SIZE:
        raise NexError(INVALID_ARGUMENT, f'object too large: {size}')
    if perm != PERMISSION_SPECIFIED:
        recipients = []
    cfg = ctx.store.cfg
    if cfg:
        refused = [p for p in recipients if not cfg.pid_allowed(p)]
        if refused:
            log.warning('note from %d: dropping recipients not on the allowlist: %s',
                        ctx.pid, refused)
        recipients = [p for p in recipients if cfg.pid_allowed(p)]
    if not recipients:
        raise NexError(DS_PERMISSION_DENIED, 'no allowed recipients')
    secret = secrets.token_hex(16)
    data_id = ctx.store.sql(
        'INSERT INTO objects (owner, recipients, data_type, size, flag, period, secret,'
        ' param, created) VALUES (?,?,?,?,?,?,?,?,?)',
        ctx.pid, json.dumps(recipients), data_type, size, flag, period, secret,
        b'', time.time()).lastrowid

    w.u32(data_id)
    w.string(ctx.url(f'upload/{data_id}'))
    write_key_values(w, [])                         # requestHeaders
    write_key_values(w, [('secret', secret)])       # formFields, sent before 'file'
    w.buffer(b'')                                   # rootCaCert (unused over http)


@method(3)
def complete_post_object_v1(ctx, r, w):
    data_id, ok = r.u32(), r.bool()
    row = ctx.store.obj(data_id)
    if row['owner'] != ctx.pid:
        raise NexError(DS_PERMISSION_DENIED, 'not the owner')
    if row['completed']:
        raise NexError(DS_UNKNOWN, 'already completed')
    if not ok:
        ctx.store.sql('UPDATE objects SET completed=-1 WHERE id=?', data_id)
        ctx.store.path(data_id).unlink(missing_ok=True)
        return
    if not row['uploaded']:
        raise NexError(DS_UNKNOWN, 'object data was never uploaded')
    ctx.store.sql('UPDATE objects SET completed=1 WHERE id=?', data_id)
    now = time.time()
    for pid in json.loads(row['recipients']):
        ctx.store.sql('INSERT INTO notifications (pid, data_id, created) VALUES (?,?,?)',
                      pid, data_id, now)


@method(1)
def prepare_get_object_v1(ctx, r, w):
    data_id = r.u32()
    r.u32()                         # lockId
    row = ctx.store.obj(data_id)
    if row['completed'] != 1:
        raise NexError(DS_NOT_FOUND, 'not completed')
    if not can_read(row, ctx.pid):
        raise NexError(DS_PERMISSION_DENIED, 'not a recipient')
    if ctx.pid != row['owner']:
        ctx.store.mark_prepared(data_id, ctx.pid)
    w.string(ctx.url(f'object/{data_id}?s={row["secret"]}'))
    write_key_values(w, [])         # requestHeaders
    w.u32(row['size'])
    w.buffer(b'')                   # rootCaCert


@method(20)
def get_specific_meta_v1(ctx, r, w):
    infos = []
    for data_id in r.list(Reader.u32):
        row = ctx.store.sql('SELECT * FROM objects WHERE id=? AND completed=1',
                            data_id).fetchone()
        if row is not None and can_read(row, ctx.pid):
            infos.append(row)
    w.list(infos, lambda w, row: w.u32(row['id']).u32(row['owner']).u32(row['size'])
           .u16(row['data_type']).u16(0))


@method(13)
def get_notification_url(ctx, r, w):
    r.string()                      # previousUrl
    w.string(ctx.url(''))
    w.string(f'notify/{ctx.pid}')
    w.string('')
    w.buffer(b'')


@method(14)
def get_new_arrived_notifications_v1(ctx, r, w):
    last, limit = r.u64(), r.u16()
    limit = max(1, min(limit or 1, 100))
    rows = ctx.store.sql(
        'SELECT n.id, n.data_id FROM notifications n JOIN objects o ON o.id = n.data_id'
        ' WHERE n.pid=? AND n.id>? AND o.completed=1 ORDER BY n.id LIMIT ?',
        ctx.pid, last, limit + 1).fetchall()
    w.list(rows[:limit], lambda w, row: w.u64(row['id']).u32(row['data_id']))
    w.bool(len(rows) > limit)

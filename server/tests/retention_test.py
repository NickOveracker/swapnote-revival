#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retention: delivered notes are deleted after the grace period, old notes after
max_age_days, unfinished uploads after a few hours; IDs keep increasing afterwards."""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import datastore  # noqa: E402

DAY = 86400
with tempfile.TemporaryDirectory() as tmp:
    cfg = config.Config(data=pathlib.Path(tmp), server_name='t', delivered_grace_hours=24,
                        max_age_days=30)
    s = datastore.Store(pathlib.Path(tmp), cfg)
    now = 1_000_000_000.0

    delivered = s.add_completed(1, [2], b'a')
    s.sql('UPDATE objects SET created=? WHERE id=?', now - 2 * DAY, delivered)
    s.sql('INSERT INTO deliveries VALUES (?,?,?)', delivered, 2, now - 2 * DAY)
    waiting = s.add_completed(1, [2], b'b')
    s.sql('UPDATE objects SET created=? WHERE id=?', now - 2 * DAY, waiting)
    old = s.add_completed(1, [2], b'c')
    s.sql('UPDATE objects SET created=? WHERE id=?', now - 31 * DAY, old)
    unfinished = s.sql("INSERT INTO objects (owner, recipients, data_type, size, flag, period,"
                       " secret, param, created) VALUES (1,'[2]',1,1,8,90,'x',x'',?)",
                       now - DAY).lastrowid

    assert s.cleanup(now) == 3
    gone = {r['id'] for r in s.sql('SELECT id FROM objects WHERE completed=?', datastore.DELETED)}
    assert gone == {delivered, old, unfinished}, gone
    assert not s.path(delivered).exists() and s.path(waiting).exists()
    newer = s.add_completed(1, [2], b'd')
    assert newer > unfinished, 'object IDs must keep increasing'
    last = s.sql('SELECT max(id) FROM notifications').fetchone()[0]
    assert s.sql('SELECT data_id FROM notifications WHERE id=?', last).fetchone()[0] == newer
    print('retention OK', json.dumps(sorted(gone)))

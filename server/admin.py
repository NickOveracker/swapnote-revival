#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small admin tool for the Swapnote server's data directory.

usage:
  admin.py CONFIG.toml list            list stored notes (no contents)
  admin.py CONFIG.toml cleanup         apply the retention rules now
  admin.py CONFIG.toml delete DATA_ID  delete one note's data
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config  # noqa: E402
import datastore  # noqa: E402

STATES = {0: 'uploading', 1: 'stored', -1: 'failed', datastore.DELETED: 'deleted'}


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cfg = config.load(sys.argv[1])
    store = datastore.Store(cfg.data, cfg)
    cmd = sys.argv[2]
    if cmd == 'list':
        rows = store.sql('SELECT * FROM objects WHERE id >= ? ORDER BY id',
                         datastore.FIRST_DATA_ID).fetchall()
        for row in rows:
            got = [r['pid'] for r in store.sql('SELECT pid FROM deliveries WHERE data_id=?',
                                               row['id'])]
            when = datetime.datetime.fromtimestamp(row['created']).strftime('%Y-%m-%d %H:%M')
            print(f"{row['id']}  {when}  {STATES.get(row['completed'], '?'):9}  from "
                  f"{row['owner']} to {json.loads(row['recipients'])}  delivered to {got}  "
                  f"{row['size']} bytes")
    elif cmd == 'cleanup':
        print(f'deleted {store.cleanup()} note(s)')
    elif cmd == 'delete' and len(sys.argv) == 4:
        store.delete_object(int(sys.argv[3]))
        print('deleted')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()

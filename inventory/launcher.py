"""Single-PC launcher: verified backup before serving existing data."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid
from .backup import backup
from .server import serve


def prepare(path, backup_dir=None):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        destination=Path(backup_dir) if backup_dir else path.parent/'backups'
        destination.mkdir(parents=True, exist_ok=True)
        name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3'
        return backup(path,destination/name)
    return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default='data/prototype.sqlite3')
    parser.add_argument('--backup-dir')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    try:
        saved=prepare(args.db,args.backup_dir)
        if saved:print(f'Backup verified: {saved}',flush=True)
        server=serve(args.db,args.port)
    except (OSError,sqlite3.Error,ValueError) as exc:
        parser.exit(1,f'起動できません。元データを保持しています: {exc}\n')
    print(f'Local prototype: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()

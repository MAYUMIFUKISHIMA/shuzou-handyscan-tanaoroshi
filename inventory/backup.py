"""Create a verified SQLite backup without replacing an existing file."""
import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def backup(source, target):
    source, target = Path(source), Path(target)
    if not source.is_file():
        raise ValueError('元DBがありません')
    # Exclusive creation protects existing backups, including symlink targets.
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True)) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('元DBの整合性検証に失敗しました')
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('バックアップの検証に失敗しました')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('target')
    args = parser.parse_args()
    try:
        print(backup(args.source,args.target))
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f'バックアップ失敗（既存データは保持）: {exc}\n')

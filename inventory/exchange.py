"""Explicit local file exchange for the dedicated inventory app; no FTP assumptions."""
import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .core import Store
from .handheld import distribution, receive_batch
from .validation import text

MAX_FILE_BYTES = 4_000_000


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSONの項目が重複しています')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('非有限JSON数値は使用できません')


def read_json(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('交換ファイルは4MB以内です')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('UTF-8の完全なJSONファイルが必要です') from exc
    if not isinstance(value, dict):
        raise ValueError('JSONオブジェクトが必要です')
    return value


def publish_json(path, value):
    """Publish a complete file without replacing existing data, including on retry."""
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('交換ファイルは4MB以内です')
    fd, temporary = tempfile.mkstemp(prefix='.inventory-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A same-directory hard link publishes atomically and never overwrites.
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or read_json(path) != value:
                raise ValueError('出力先に異なるファイルがあります。上書きしません')
        return path
    finally:
        os.unlink(temporary)


def export_distribution(store, session_id, target):
    package = distribution(store.load(session_id))
    publish_json(target, package)
    return package


def export_terminal_batch(terminal, target):
    batch = terminal.batch()
    publish_json(target, batch)
    return batch


def import_batch(store, source, receipt_path, actor):
    batch = read_json(source)
    receipt = receive_batch(store, batch, actor)
    # If writing fails after DB commit, resend the same input and actor to recover.
    publish_json(receipt_path, receipt)
    return receipt


def import_receipt(terminal, batch_path, receipt_path):
    terminal.acknowledge(read_json(batch_path), read_json(receipt_path))


def resolve_conflict(store, proposal, actor, request_id):
    text(request_id, '操作ID')
    required = {'session_id', 'revision', 'code', 'location', 'quantity', 'supersedes', 'reason'}
    if not isinstance(proposal, dict) or set(proposal) != required:
        raise ValueError('競合解決案の項目が不正です')
    record = dict(id=request_id, device='PC-REVIEW', operator=actor,
                  **{k:proposal[k] for k in ('code', 'location', 'quantity', 'supersedes')})
    request = dict(request_id=request_id, proposal=proposal, actor=actor)
    def operation():
        result = store.change(proposal['session_id'], proposal['revision'], 'resolve_conflict', actor,
                              dict(reason=proposal['reason'], record=record))
        return dict(session_id=result['id'], revision=result['revision'], record_id=record['id'])
    return store.execute_once(request, operation)


def reconciliation(store, session_id):
    session = store.load(session_id)
    superseded = {old for record in session['records'] for old in record['supersedes']}
    active = {}
    for record in session['records']:
        if record['id'] not in superseded:
            active.setdefault((record['code'], record['location']), []).append(record)
    cells = []
    for item in session['items']:
        for location in session['locations']:
            records = active.get((item['code'], location), [])
            cells.append(dict(code=item['code'], name=item['name'], location=location,
                              status='missing' if not records else 'counted' if len(records) == 1 else 'conflict',
                              quantity=records[0]['quantity'] if len(records) == 1 else None,
                              records=records))
    return dict(session_id=session_id, revision=session['revision'], state=session['state'],
                cells=cells, summary=store.summary(session), history=session['records'], audit=session['audit'],
                held=session.get('held', []))


def main(argv=None):
    parser = argparse.ArgumentParser(description='棚卸専用PCファイル交換（実機FTP未接続）')
    parser.add_argument('--db', required=True, help='既存のPC棚卸DB')
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('distribute', help='対象一覧のJSONを出力')
    export.add_argument('--session', required=True)
    export.add_argument('--output', required=True)
    receive = commands.add_parser('receive', help='実績JSONを一括回収し受領JSONを出力')
    receive.add_argument('--input', required=True)
    receive.add_argument('--receipt', required=True)
    receive.add_argument('--actor', required=True)
    report = commands.add_parser('report', help='未入力・ゼロ・競合・履歴をJSONへ出力')
    report.add_argument('--session', required=True)
    report.add_argument('--output', required=True)
    resolve = commands.add_parser('resolve-conflict', help='確認した実数と理由で競合を解決')
    resolve.add_argument('--input', required=True)
    resolve.add_argument('--actor', required=True)
    resolve.add_argument('--request-id', required=True)
    args = parser.parse_args(argv)
    try:
        if not Path(args.db).is_file():
            raise ValueError('既存のPC棚卸DBを指定してください')
        with closing(Store(args.db)) as store:
            if args.command == 'distribute':
                export_distribution(store, args.session, args.output)
            elif args.command == 'receive':
                import_batch(store, args.input, args.receipt, args.actor)
            elif args.command == 'resolve-conflict':
                resolve_conflict(store, read_json(args.input), args.actor, args.request_id)
            else:
                publish_json(args.output, reconciliation(store, args.session))
        print('完了: ' + args.command)
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        parser.exit(1, f'処理失敗: {exc}\n入力ファイルは保持しています。回収の再試行は同じ入力・担当者を指定してください。\n')


if __name__ == '__main__':
    main()

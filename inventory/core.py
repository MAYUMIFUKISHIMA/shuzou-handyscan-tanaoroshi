"""Transactional stocktake model. Quantities are decimal strings, never floats."""
import csv
import base64
from .csv_export import render_import_csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from .validation import text, headers, MAX_ITEMS, MAX_RECORDS, MAX_BATCH, MAX_LOCATIONS
from datetime import datetime, timezone
from decimal import Decimal


def now():
    return datetime.now(timezone.utc).isoformat()


def quantity(value, negative=False):
    if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]{1,12}(\.[0-9]{1,6})?', value):
        raise ValueError('数量は12桁以内、小数6桁以内の数値文字列で指定してください')
    n = Decimal(value)
    if n < 0 and not negative:
        raise ValueError('実数は負にできません')
    return format(n, 'f')


def read_csv(raw, encoding='utf-8-sig', columns=None):
    headers(raw, encoding)
    columns = columns if columns is not None else {'code': '商品番号', 'name': '名称', 'baseline': '数量'}
    if not isinstance(columns, dict) or any(not isinstance(v, str) for v in columns.values()) or set(columns) != {'code', 'name', 'baseline'} or len(set(columns.values())) != 3:
        raise ValueError('列対応が不正です')
    reader = csv.DictReader(io.StringIO(raw.decode(encoding), newline=''), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('ヘッダーがないか重複しています')
    if not set(columns.values()) <= set(reader.fieldnames):
        raise ValueError('必要な列がありません')
    result, seen, errors = [], set(), []
    for number, row in enumerate(reader, 1):
        if number > MAX_ITEMS:
            raise ValueError('CSVは5000件以内にしてください')
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('列数が一致しません')
            item = {key: row[col] for key, col in columns.items()}
            text(item['code'], '商品番号')
            text(item['name'], '名称', 512)
            if not item['code'] or not item['name'] or item['code'] != item['code'].strip():
                raise ValueError('商品番号・名称が空、または番号の前後に空白があります')
            if item['code'] in seen:
                raise ValueError('商品番号が重複しています。倉庫区分等の仕様確認が必要です')
            item['baseline'] = quantity(item['baseline'], negative=True)
            seen.add(item['code'])
            result.append(item)
        except ValueError as exc:
            errors.append(f'{reader.line_num}行: {exc}')
            if len(errors) >= 100:
                raise ValueError('\n'.join(errors) + '\nエラー100件で検証を中断しました')
    if errors:
        raise ValueError('\n'.join(errors))
    if not result:
        raise ValueError('対象データがありません')
    return result


def capacity_plan(item_count, locations, reserve=None):
    if not isinstance(locations, list) or not 0 < len(locations) <= MAX_LOCATIONS:
        raise ValueError('区画は1〜20件の配列が必要です')
    for loc in locations:
        text(loc, '区画')
        if loc != loc.strip():
            raise ValueError('区画の前後に空白は使用できません')
    if len(set(locations)) != len(locations):
        raise ValueError('区画が重複しています')
    initial = item_count * len(locations)
    # Prototype default allows one complete recount. D05 must approve production limits.
    reserve = initial if reserve is None else reserve
    if type(reserve) is not int or reserve < 1:
        raise ValueError('訂正・再棚卸の追加件数は1以上の整数で指定してください')
    if initial + reserve > MAX_RECORDS:
        raise ValueError(f'初回{initial}件＋訂正予約{reserve}件が保存上限{MAX_RECORDS}件を超えます。対象範囲を見直してください')
    return dict(initial=initial, reserve=reserve, required=initial+reserve, limit=MAX_RECORDS)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=1)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
            ''')
        except sqlite3.Error:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        if self.db.in_transaction:
            yield
        else:
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                yield

    def execute_once(self, request, operation):
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.transaction():
            row = self.db.execute('SELECT * FROM receipts WHERE id=?', (request['request_id'],)).fetchone()
            if row:
                if row['fingerprint'] != fingerprint:
                    raise ValueError('再送識別IDが同じで内容が異なります')
                return json.loads(row['result'])
            result = operation()
            self.db.execute('INSERT INTO receipts VALUES (?,?,?)', (request['request_id'], fingerprint, json.dumps(result)))
            return result

    def close(self):
        self.db.close()

    def load(self, sid):
        row = self.db.execute('SELECT body FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('棚卸がありません')
        return self.decode(row['body'])

    @staticmethod
    def decode(body):
        try:
            value = json.loads(body)
            if not isinstance(value, dict) or not {'id','state','revision','items','records','locations','completed','audit'} <= value.keys():
                raise ValueError('invalid stored session')
            return value
        except (ValueError, TypeError) as exc:
            raise sqlite3.DatabaseError('保存データが不正です') from exc

    def list(self):
        return [self.decode(r['body']) for r in self.db.execute('SELECT body FROM sessions ORDER BY rowid DESC')]

    def create(self, raw, locations, actor, encoding='utf-8-sig', columns=None, source_name='', correction_reserve=None):
        items = read_csv(raw, encoding, columns)
        text(actor, '担当者')
        text(source_name, 'ファイル名', 255, empty=True)
        if not isinstance(locations, list) or not 0 < len(locations) <= MAX_LOCATIONS or any(not isinstance(x, str) for x in locations) or len(set(locations)) != len(locations) or any(not x.strip() for x in locations):
            raise ValueError('担当者と重複のない区画を指定してください')
        for loc in locations:
            text(loc, '区画')
        plan = capacity_plan(len(items), locations, correction_reserve)
        sid = str(uuid.uuid4())
        s = dict(id=sid, state='counting', revision=0, source_hash=hashlib.sha256(raw).hexdigest(),
                 encoding=encoding, columns=columns, source_name=source_name, items=items, locations=locations,
                 capacity=plan, created_at=now(), result_version=0, mode='prototype', records=[], completed=[], audit=[dict(action='create', actor=actor, time=now())])
        with self.transaction():
            self.db.execute('INSERT INTO sessions VALUES (?,?)', (sid, json.dumps(s, ensure_ascii=False)))
            self.db.execute('INSERT INTO sources VALUES (?,?)', (sid, raw))
        return s

    def change(self, sid, revision, action, actor, payload):
        text(actor, '担当者')
        text(sid, '棚卸ID')
        if type(revision) is not int or revision < 0:
            raise ValueError('revisionは非負整数です')
        with self.transaction():
            s = self.load(sid)
            if revision != s['revision']:
                raise ValueError('別の操作で更新されています。再読込してください')
            if action == 'receive':
                self._receive(s, payload)
            elif action == 'resolve_conflict':
                if not isinstance(payload, dict) or set(payload) != {'reason', 'record'}:
                    raise ValueError('競合解決には理由と記録が必要です')
                text(payload['reason'], '確認・再計数の理由', 512)
                record = payload['record']
                if not isinstance(record, dict):
                    raise ValueError('競合解決の記録が不正です')
                if not isinstance(record.get('supersedes'), list) or any(not isinstance(x, str) for x in record['supersedes']):
                    raise ValueError('競合候補IDは文字列の配列が必要です')
                active = self.active(s, record.get('code'), record.get('location'))
                if len(active) < 2:
                    raise ValueError('複数の採用候補がある競合を選択してください')
                if set(record.get('supersedes', [])) != {r['id'] for r in active}:
                    raise ValueError('競合候補が変わっています。再確認してください')
                self._receive(s, [record])
            elif action == 'hold':
                self._editable(s)
                required = {'id','device','code','location','quantity','operator'}
                if not isinstance(payload, dict) or set(payload) != required:
                    raise ValueError('保留記録の項目が不正です')
                for key in required:
                    text(payload[key], key)
                quantity(payload['quantity'])
                if payload['location'] not in s['locations']:
                    raise ValueError('区画がありません')
                if payload['code'] in {i['code'] for i in s['items']}:
                    raise ValueError('登録済み商品は通常の記録を使用してください')
                held = s.setdefault('held', [])
                if len(held) >= MAX_BATCH or any(x['id'] == payload['id'] for x in held):
                    raise ValueError('保留IDの重複または上限です')
                held.append(dict(payload, status='open', time=now()))
            elif action in ('resolve', 'dismiss'):
                self._editable(s)
                expected = {'id','reason','record'} if action == 'resolve' else {'id','reason'}
                if not isinstance(payload, dict) or set(payload) != expected:
                    raise ValueError('保留処理の項目が不正です')
                text(payload['reason'], '処理理由', 512)
                held = next((x for x in s.get('held', []) if x['id'] == payload['id'] and x['status'] == 'open'), None)
                if held is None:
                    raise ValueError('未解決の保留がありません')
                if action == 'resolve':
                    record = payload['record']
                    if not isinstance(record, dict) or record.get('location') != held['location'] or record.get('quantity') != held['quantity']:
                        raise ValueError('保留の区画・数量を保持してください')
                    self._receive(s, [record])
                    held['resolved_record'] = record['id']
                held.update(status=action, reason=payload['reason'], resolved_by=actor, resolved_at=now())
            elif action == 'complete':
                self._editable(s)
                if not isinstance(payload, dict) or set(payload) != {'location'}:
                    raise ValueError('区画を指定してください')
                location = payload['location']
                if location not in s['locations']:
                    raise ValueError('区画がありません')
                superseded = {i for r in s['records'] for i in r['supersedes']}
                counts = {}
                for r in s['records']:
                    if r['location'] == location and r['id'] not in superseded:
                        counts[r['code']] = counts.get(r['code'], 0) + 1
                if any(counts.get(item['code'], 0) != 1 for item in s['items']):
                    raise ValueError('未棚卸または競合があります')
                if location not in s['completed']:
                    s['completed'].append(location)
                if set(s['completed']) == set(s['locations']):
                    s['state'] = 'reviewing'
            elif action == 'finalize':
                self._editable(s)
                if any(x['status'] == 'open' for x in s.get('held', [])):
                    raise ValueError('未解決のバーコードがあります')
                if set(s['completed']) != set(s['locations']):
                    raise ValueError('全区画の完了確認が必要です')
                rows = self.summary(s)
                if any(r['count'] is None for r in rows):
                    raise ValueError('未棚卸または競合があります')
                s['result_version'] = s.get('result_version', 0) + 1
                s['finalized_by'] = actor
                s['finalized_at'] = now()
                s['result'] = rows
                s['state'] = 'finalized'
            elif action == 'reopen':
                if s['state'] != 'finalized':
                    raise ValueError('出力済みの訂正は外部取り込み状況の確認が必要です')
                if not isinstance(payload, dict) or set(payload) != {'reason'}:
                    raise ValueError('訂正理由が必要です')
                text(payload['reason'], '訂正理由', 512)
                s.setdefault('previous_results', []).append(dict(result=s.pop('result'), version=s.get('result_version', 0), finalized_by=s.get('finalized_by'), finalized_at=s.get('finalized_at'), reason=payload['reason'], actor=actor, time=now()))
                s['state'] = 'counting'
                s['completed'] = []
            elif action == 'export_import':
                if s['state'] not in ('finalized','exported','exported_import'):
                    raise ValueError('確定が必要です')
                if s['state'] == 'exported_import':
                    if s['import_artifact']['profile'] != payload:
                        raise ValueError('出力済みの形式変更はできません。旧ファイルの取り込み状況を確認してください')
                else:
                    raw = render_import_csv(s['result'],payload)
                    s['import_artifact'] = dict(profile=payload, data=base64.b64encode(raw).decode('ascii'),
                        sha256=hashlib.sha256(raw).hexdigest(), result_version=s['result_version'],
                        created_by=actor, created_at=now(), count=len(s['result']))
                s['state'] = 'exported_import'
            elif action == 'export':
                if s['state'] not in ('finalized', 'exported'):
                    raise ValueError('確定が必要です')
                if 'csv' not in s:
                    out = io.StringIO(newline='')
                    writer = csv.writer(out)
                    writer.writerow(['商品番号', '名称', '基準数量', '実数', '差異'])
                    writer.writerows([r[k] for k in ('code','name','baseline','count','difference')] for r in s['result'])
                    s['csv'] = out.getvalue()
                    s['export_manifest'] = dict(session_id=sid, result_version=s.get('result_version', 0), kind='confirmation_only', created_by=actor, created_at=now(), count=len(s['result']))
                    s['export_hash'] = hashlib.sha256(s['csv'].encode('utf-8-sig')).hexdigest()
                s['state'] = 'exported'
            else:
                raise ValueError('未対応の操作です')
            s['revision'] += 1
            event = dict(action=action, actor=actor, time=now())
            if action == 'resolve_conflict':
                event.update(reason=payload['reason'], record_id=record['id'],
                             supersedes=record['supersedes'], code=record['code'], location=record['location'])
            s['audit'].append(event)
            self.db.execute('UPDATE sessions SET body=? WHERE id=?', (json.dumps(s, ensure_ascii=False), sid))
        return s

    @staticmethod
    def _editable(s):
        if s['state'] not in ('counting', 'reviewing'):
            raise ValueError('確定後は変更できません')

    def _receive(self, s, records):
        if not isinstance(records, list) or not 0 < len(records) <= MAX_BATCH:
            raise ValueError('記録の配列が必要です')
        for r in records:
            required = {'id','device','code','location','quantity','operator','supersedes'}
            if not isinstance(r, dict) or set(r) != required:
                raise ValueError('転送記録の項目が不正です')
            if any(not isinstance(r[k], str) or not r[k].strip() for k in required - {'supersedes'}):
                raise ValueError('記録の必須文字列が空です')
            if not isinstance(r['supersedes'], list) or any(not isinstance(x, str) for x in r['supersedes']):
                raise ValueError('訂正元はIDの配列です')
            for key in required - {'supersedes'}:
                text(r[key], key)
            if len(r['supersedes']) > MAX_BATCH or len(set(r['supersedes'])) != len(r['supersedes']):
                raise ValueError('訂正元が重複または多すぎます')
            old = next((x for x in s['records'] if x['id'] == r['id']), None)
            if old:
                if old != r:
                    raise ValueError('同じ記録IDで内容が異なります')
                continue
            self._editable(s)
            if len(s['records']) >= MAX_RECORDS:
                raise ValueError('記録数の上限20000件です')
            quantity(r['quantity'])
            if r['code'] not in [x['code'] for x in s['items']] or r['location'] not in s['locations']:
                raise ValueError('未登録商品または区画です')
            active = self.active(s, r['code'], r['location'])
            if r['supersedes'] and set(r['supersedes']) != {x['id'] for x in active}:
                raise ValueError('訂正元が最新ではありません。競合を確認してください')
            s['records'].append(r)
            s['state'] = 'counting'
            if r['location'] in s['completed']:
                s['completed'].remove(r['location'])

    @staticmethod
    def active(s, code, location):
        records = [r for r in s['records'] if r['code'] == code and r['location'] == location]
        superseded = {i for r in records for i in r['supersedes']}
        return [r for r in records if r['id'] not in superseded]

    def _cell(self, s, code, location, required=False):
        records = self.active(s, code, location)
        if len(records) != 1:
            if required:
                raise ValueError('未棚卸または競合があります')
            return None
        return Decimal(records[0]['quantity'])

    def summary(self, s):
        rows = []
        superseded = {i for r in s['records'] for i in r['supersedes']}
        cells = {}
        for r in s['records']:
            if r['id'] not in superseded:
                cells.setdefault((r['code'], r['location']), []).append(Decimal(r['quantity']))
        for item in s['items']:
            groups = [cells.get((item['code'], loc), []) for loc in s['locations']]
            values = [v[0] if len(v) == 1 else None for v in groups]
            count = sum(values, Decimal(0)) if all(x is not None for x in values) else None
            rows.append(dict(item, count=None if count is None else str(count),
                             difference=None if count is None else str(count - Decimal(item['baseline']))))
        return rows

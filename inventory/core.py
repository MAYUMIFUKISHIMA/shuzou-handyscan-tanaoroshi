"""Transactional stocktake model. Quantities are decimal strings, never floats."""
import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal


def now():
    return datetime.now(timezone.utc).isoformat()


def quantity(value, negative=False):
    if not isinstance(value, str) or not re.fullmatch(r'-?\d{1,12}(\.\d{1,6})?', value):
        raise ValueError('数量は12桁以内、小数6桁以内の数値文字列で指定してください')
    n = Decimal(value)
    if n < 0 and not negative:
        raise ValueError('実数は負にできません')
    return format(n, 'f')


def read_csv(raw, encoding='utf-8-sig', columns=None):
    columns = columns or {'code': '商品番号', 'name': '名称', 'baseline': '数量'}
    if set(columns) != {'code', 'name', 'baseline'} or len(set(columns.values())) != 3:
        raise ValueError('列対応が不正です')
    reader = csv.DictReader(io.StringIO(raw.decode(encoding), newline=''), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('ヘッダーがないか重複しています')
    if not set(columns.values()) <= set(reader.fieldnames):
        raise ValueError('必要な列がありません')
    result, seen, errors = [], set(), []
    for row in reader:
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('列数が一致しません')
            item = {key: row[col] for key, col in columns.items()}
            if not item['code'] or not item['name'] or item['code'] != item['code'].strip():
                raise ValueError('商品番号・名称が空、または番号の前後に空白があります')
            if item['code'] in seen:
                raise ValueError('商品番号が重複しています。倉庫区分等の仕様確認が必要です')
            item['baseline'] = quantity(item['baseline'], negative=True)
            seen.add(item['code'])
            result.append(item)
        except ValueError as exc:
            errors.append(f'{reader.line_num}行: {exc}')
    if errors:
        raise ValueError('\n'.join(errors))
    if not result:
        raise ValueError('対象データがありません')
    return result


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, raw BLOB NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def load(self, sid):
        row = self.db.execute('SELECT body FROM sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('棚卸がありません')
        return json.loads(row['body'])

    def list(self):
        return [json.loads(r['body']) for r in self.db.execute('SELECT body FROM sessions ORDER BY rowid DESC')]

    def create(self, raw, locations, actor, encoding='utf-8-sig', columns=None):
        items = read_csv(raw, encoding, columns)
        if not actor or not locations or len(set(locations)) != len(locations) or any(not x.strip() for x in locations):
            raise ValueError('担当者と重複のない区画を指定してください')
        sid = str(uuid.uuid4())
        s = dict(id=sid, state='counting', revision=0, source_hash=hashlib.sha256(raw).hexdigest(),
                 encoding=encoding, columns=columns, items=items, locations=locations,
                 records=[], completed=[], audit=[dict(action='create', actor=actor, time=now())])
        with self.db:
            self.db.execute('INSERT INTO sessions VALUES (?,?)', (sid, json.dumps(s, ensure_ascii=False)))
            self.db.execute('INSERT INTO sources VALUES (?,?)', (sid, raw))
        return s

    def change(self, sid, revision, action, actor, payload):
        if not actor or not isinstance(actor, str):
            raise ValueError('担当者が必要です')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            s = self.load(sid)
            if revision != s['revision']:
                raise ValueError('別の操作で更新されています。再読込してください')
            if action == 'receive':
                self._receive(s, payload)
            elif action == 'complete':
                self._editable(s)
                location = payload['location']
                if location not in s['locations']:
                    raise ValueError('区画がありません')
                for item in s['items']:
                    self._cell(s, item['code'], location, required=True)
                if location not in s['completed']:
                    s['completed'].append(location)
            elif action == 'finalize':
                self._editable(s)
                if set(s['completed']) != set(s['locations']):
                    raise ValueError('全区画の完了確認が必要です')
                rows = self.summary(s)
                if any(r['count'] is None for r in rows):
                    raise ValueError('未棚卸または競合があります')
                s['result'] = rows
                s['state'] = 'finalized'
            elif action == 'export':
                if s['state'] not in ('finalized', 'exported'):
                    raise ValueError('確定が必要です')
                if 'csv' not in s:
                    out = io.StringIO(newline='')
                    writer = csv.writer(out)
                    writer.writerow(['商品番号', '名称', '基準数量', '実数', '差異'])
                    writer.writerows([r[k] for k in ('code','name','baseline','count','difference')] for r in s['result'])
                    s['csv'] = out.getvalue()
                    s['export_hash'] = hashlib.sha256(s['csv'].encode('utf-8-sig')).hexdigest()
                s['state'] = 'exported'
            else:
                raise ValueError('未対応の操作です')
            s['revision'] += 1
            s['audit'].append(dict(action=action, actor=actor, time=now()))
            self.db.execute('UPDATE sessions SET body=? WHERE id=?', (json.dumps(s, ensure_ascii=False), sid))
        return s

    @staticmethod
    def _editable(s):
        if s['state'] != 'counting':
            raise ValueError('確定後は変更できません')

    def _receive(self, s, records):
        if not isinstance(records, list) or not records:
            raise ValueError('記録の配列が必要です')
        for r in records:
            required = {'id','device','code','location','quantity','operator','supersedes'}
            if not isinstance(r, dict) or set(r) != required:
                raise ValueError('転送記録の項目が不正です')
            if any(not isinstance(r[k], str) or not r[k].strip() for k in required - {'supersedes'}):
                raise ValueError('記録の必須文字列が空です')
            if not isinstance(r['supersedes'], list) or any(not isinstance(x, str) for x in r['supersedes']):
                raise ValueError('訂正元はIDの配列です')
            old = next((x for x in s['records'] if x['id'] == r['id']), None)
            if old:
                if old != r:
                    raise ValueError('同じ記録IDで内容が異なります')
                continue
            self._editable(s)
            quantity(r['quantity'])
            if r['code'] not in [x['code'] for x in s['items']] or r['location'] not in s['locations']:
                raise ValueError('未登録商品または区画です')
            active = self.active(s, r['code'], r['location'])
            if r['supersedes'] and set(r['supersedes']) != {x['id'] for x in active}:
                raise ValueError('訂正元が最新ではありません。競合を確認してください')
            s['records'].append(r)
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
        for item in s['items']:
            values = [self._cell(s, item['code'], loc) for loc in s['locations']]
            count = sum(values, Decimal(0)) if all(x is not None for x in values) else None
            rows.append(dict(item, count=None if count is None else str(count),
                             difference=None if count is None else str(count - Decimal(item['baseline']))))
        return rows

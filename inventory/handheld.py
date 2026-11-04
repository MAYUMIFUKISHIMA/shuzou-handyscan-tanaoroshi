"""Host-only handheld simulator and transport contract. Not executable on BT-W250."""
import hashlib
import json
import sqlite3
import uuid
from .core import quantity
from .validation import text, MAX_BATCH


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def distribution(session):
    if session['state'] not in ('counting', 'reviewing'):
        raise ValueError('確定済みの棚卸は配布できません')
    data=dict(schema=1, session_id=session['id'], source_hash=session['source_hash'], generation=session.get('result_version',0),
              items=session['items'], locations=session['locations'])
    return dict(data, distribution_id=digest(data))


class TerminalSimulator:
    def __init__(self, path, package, device):
        text(device, '端末ID')
        data={k:v for k,v in package.items() if k!='distribution_id'}
        if package.get('schema')!=1 or digest(data)!=package.get('distribution_id'):
            raise ValueError('配布データが壊れています')
        self.package=package;self.device=device
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY, body TEXT NOT NULL, received INTEGER NOT NULL DEFAULT 0)')
        self.db.execute('CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, body TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0)')
        identity=digest(dict(distribution=package['distribution_id'],device=device))
        row=self.db.execute("SELECT value FROM config WHERE key='identity'").fetchone()
        if row and row[0]!=identity:
            self.db.close();raise ValueError('別端末・別棚卸の保存先です。既存データを回収してください')
        with self.db:self.db.execute("INSERT OR IGNORE INTO config VALUES ('identity',?)",(identity,))

    def close(self):self.db.close()

    def scan(self, barcode):
        text(barcode,'バーコード')
        item=next((x for x in self.package['items'] if x['code']==barcode),None)
        if item is None:raise ValueError('未登録バーコードです。自動で商品へ割り当てません')
        return item

    def count(self, barcode, value, location, operator):
        self.scan(barcode);quantity(value);text(operator,'担当者')
        if location not in self.package['locations']:raise ValueError('区画がありません')
        # IDs survive restart; a correction explicitly references prior local records.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            same=self.inspect(barcode,location)['history']
            removed={x for r in same for x in r['supersedes']}
            record=dict(id=str(uuid.uuid4()),device=self.device,code=barcode,quantity=value,
                        location=location,operator=operator,supersedes=[r['id'] for r in same if r['id'] not in removed])
            self.db.execute('INSERT INTO queue(id,body) VALUES (?,?)',(record['id'],json.dumps(record,ensure_ascii=False)))
        return record

    def inspect(self, barcode, location):
        """Read-only product view: None means uncounted, '0' is an explicit count."""
        item=self.scan(barcode)
        if location not in self.package['locations']:raise ValueError('区画がありません')
        history=[json.loads(r[0]) for r in self.db.execute('SELECT body FROM queue ORDER BY rowid')]
        history=[r for r in history if r['code']==barcode and r['location']==location]
        removed={x for r in history for x in r['supersedes']}
        active=[r for r in history if r['id'] not in removed]
        if len(active)>1:raise ValueError('端末内の訂正履歴が競合しています')
        return dict(item=item,location=location,quantity=active[0]['quantity'] if active else None,history=history)

    def batch(self):
        # Freeze before transport. New counts must not change a batch whose receipt was lost.
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            pending=self.db.execute('SELECT body FROM batches WHERE acknowledged=0 ORDER BY rowid LIMIT 1').fetchone()
            if pending:return json.loads(pending[0])
            records=[json.loads(r[0]) for r in self.db.execute('SELECT body FROM queue WHERE received=0 ORDER BY rowid LIMIT ?', (MAX_BATCH,))]
            if not records:raise ValueError('未送信記録はありません')
            data=dict(schema=1,session_id=self.package['session_id'],distribution_id=self.package['distribution_id'],records=records)
            batch=dict(data,batch_id=digest(data))
            self.db.execute('INSERT INTO batches(id,body) VALUES (?,?)',(batch['batch_id'],json.dumps(batch,ensure_ascii=False)))
            return batch

    def acknowledge(self, batch, receipt):
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            saved=self.db.execute('SELECT body FROM batches WHERE id=?',(batch.get('batch_id'),)).fetchone()
            if saved is None or json.loads(saved[0])!=batch:raise ValueError('保存済み送信内容と一致しません')
            expected=dict(batch_id=batch['batch_id'],distribution_id=batch['distribution_id'],record_ids=[r['id'] for r in batch['records']])
            if receipt!=expected:raise ValueError('受領確認が送信内容と一致しません')
            for record in batch['records']:
                row=self.db.execute('SELECT body FROM queue WHERE id=?',(record['id'],)).fetchone()
                if row is None or json.loads(row[0])!=record:raise ValueError('端末記録が一致しません')
                self.db.execute('UPDATE queue SET received=1 WHERE id=?',(record['id'],))
            self.db.execute('UPDATE batches SET acknowledged=1 WHERE id=?',(batch['batch_id'],))


def receive_batch(store, batch, actor):
    if not isinstance(batch,dict) or set(batch)!={'schema','session_id','distribution_id','records','batch_id'}:
        raise ValueError('バッチの項目が不正です')
    if type(batch['schema']) is not int or batch['schema']!=1 or digest({k:v for k,v in batch.items() if k!='batch_id'})!=batch['batch_id']:
        raise ValueError('バッチが破損または未対応の版です')
    text(batch['session_id'], '棚卸ID')
    text(batch['distribution_id'], '配布版')
    text(batch['batch_id'], 'バッチID')
    text(actor, '回収担当者')
    request=dict(request_id='terminal-'+batch['batch_id'],batch=batch,actor=actor)
    def operation():
        s=store.load(batch['session_id'])
        if distribution(s)['distribution_id']!=batch['distribution_id']:
            raise ValueError('配布版が古いか別棚卸です')
        store.change(s['id'],s['revision'],'receive',actor,batch['records'])
        return dict(batch_id=batch['batch_id'],distribution_id=batch['distribution_id'],record_ids=[r['id'] for r in batch['records']])
    return store.execute_once(request,operation)

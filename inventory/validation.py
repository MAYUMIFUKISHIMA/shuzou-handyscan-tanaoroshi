"""Shared, bounded input contract for the local prototype."""
MAX_CSV = 1_000_000
MAX_ITEMS = 5000
MAX_RECORDS = 20000
MAX_BATCH = 1000
MAX_LOCATIONS = 20


def text(value, label, maximum=128, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f'{label}: 文字列の長さが不正です（最大{maximum}文字）')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{label}: 制御文字は使用できません')
    return value


def headers(raw, encoding):
    import csv
    import io
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CSV:
        raise ValueError('CSVは空でない1MB以内のファイルにしてください')
    if encoding not in ('utf-8-sig', 'cp932'):
        raise ValueError('未対応の文字コードです')
    decoded = raw.decode(encoding)
    if '\x00' in decoded:
        raise ValueError('CSVにNUL文字があります')
    fields = next(csv.reader(io.StringIO(decoded, newline=''), strict=True), [])
    if not fields or len(fields) > 100 or len(set(fields)) != len(fields):
        raise ValueError('ヘッダーが空・重複、または100列を超えています')
    for field in fields:
        text(field, '列名')
    return fields


def request(body):
    if not isinstance(body, dict):
        raise ValueError('JSONオブジェクトが必要です')
    action = body.get('action')
    if not isinstance(action, str) or action not in {'inspect','preview','create','receive','complete','finalize','export','reopen','hold','resolve','dismiss','export_import','resolve_conflict'}:
        raise ValueError('未対応の操作です')
    if action in ('inspect','preview','create'):
        allowed = {'action','csv','encoding','columns','source_name'}
        if action == 'preview':
            allowed |= {'locations','correction_reserve'}
        if action == 'create':
            allowed |= {'actor','locations','request_id','correction_reserve'}
        if not isinstance(body.get('csv'), str) or not body['csv'].isascii():
            raise ValueError('CSVはBase64文字列が必要です')
    else:
        allowed = {'action','actor','id','revision','payload','request_id'}
        text(body.get('id'), '棚卸ID')
        if type(body.get('revision')) is not int or body['revision'] < 0:
            raise ValueError('revisionは非負の整数が必要です')
    if action in ('finalize', 'export') and body.get('payload') is not None:
        raise ValueError('この操作にpayloadは指定できません')
    if set(body) - allowed:
        raise ValueError('未対応の項目があります')
    if action not in ('inspect','preview'):
        text(body.get('actor'), '担当者')
        text(body.get('request_id'), '再送識別ID')
    return body

"""Local-only prototype UI. Not a production or handheld server."""
import argparse
import base64
import csv
import json
import io
import hashlib
import secrets
import sqlite3
import socket
from .validation import headers, request as validate_request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import Store, read_csv


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, mime='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def failure(self, exc):
        if isinstance(exc, sqlite3.Error):
            message = 'DBの保存・読込に失敗しました。容量・権限・ロックを確認し、復旧後に同じ操作を再送してください。破損の場合はバックアップから復旧してください。'
            status = 503
        elif isinstance(exc, OSError):
            message = 'ファイルまたは通信に失敗しました。保存結果を確認し、同じ操作を再送してください。'
            status = 503
        else:
            message = str(exc)
            status = 400
        try:
            self.reply(status, {'error': message})
        except OSError:
            pass

    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'error': '接続先ホストが不正です'})
        try:
            self.get()
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.failure(exc)

    def get(self):
        path = urlparse(self.path).path
        if path in ('/', '/app.js', '/style.css'):
            file = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
            mime = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[path]
            return self.reply(200, Path(__file__).with_name(file).read_bytes(), mime+'; charset=utf-8')
        if path == '/api':
            with_store = Store(self.server.db_path)
            try:
                sessions = with_store.list()
                for s in sessions:
                    s['summary'] = with_store.summary(s)
                return self.reply(200, dict(sessions=sessions, token=self.server.token))
            finally:
                with_store.close()
        self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        expected = f'http://127.0.0.1:{self.server.server_port}'
        if not self.valid_host() or self.headers.get('X-Token') != self.server.token or (origin and origin != expected):
            return self.reply(403, {'error': 'ページを再読込してください'})
        if self.path != '/api' or self.headers.get('Content-Type') != 'application/json':
            return self.reply(400, {'error': 'Invalid request'})
        store = None
        try:
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                raise ValueError('Content-Lengthを一つ指定してください')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2_000_000:
                raise ValueError('リクエストは2MB以内です')
            raw_body = self.rfile.read(size)
            if len(raw_body) != size:
                raise ValueError('受信が途中で終了しました')
            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('JSONの項目が重複しています')
                    result[key] = value
                return result
            def invalid_constant(value):
                raise ValueError('非有限JSON数値は使用できません')
            request = validate_request(json.loads(raw_body, object_pairs_hook=unique_pairs, parse_constant=invalid_constant))
            store = Store(self.server.db_path)
            if request['action'] in ('inspect', 'preview', 'create'):
                raw = base64.b64decode(request['csv'], validate=True)
                encoding = request.get('encoding', 'utf-8-sig')
                fields = headers(raw, encoding)
                if request['action'] == 'inspect':
                    return self.reply(200, {'headers': fields})
                columns = request.get('columns')
                if request['action'] == 'preview':
                    items = read_csv(raw, encoding, columns)
                    digest = hashlib.sha256(raw).hexdigest()
                    duplicates = [x['id'] for x in store.list() if x['source_hash'] == digest]
                    return self.reply(200, {'items': items[:100], 'count': len(items), 'duplicates': duplicates})
                def operation():
                    s = store.create(raw, request.get('locations'), request['actor'], encoding, columns, request.get('source_name', ''))
                    return {'id': s['id']}
            else:
                def operation():
                    s = store.change(request['id'], request['revision'], request['action'], request['actor'], request.get('payload'))
                    return {'id': s['id']}
            self.reply(200, store.execute_once(request, operation))
        except (ValueError, KeyError, TypeError, UnicodeError, csv.Error, sqlite3.Error, OSError, RecursionError) as exc:
            self.failure(exc)
        finally:
            if store is not None:
                store.close()


def serve(path, port):
    server = HTTPServer(('127.0.0.1', port), Handler)
    server.db_path = str(path)
    server.token = secrets.token_urlsafe(32)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/prototype.sqlite3')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    server = serve(args.db, args.port)
    print(f'Local prototype: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

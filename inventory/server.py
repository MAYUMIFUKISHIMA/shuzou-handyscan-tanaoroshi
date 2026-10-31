"""Local-only prototype UI. Not a production or handheld server."""
import argparse
import base64
import csv
import json
import io
import hashlib
import secrets
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

    def do_GET(self):
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
        if self.headers.get('X-Token') != self.server.token or (origin and origin != expected):
            return self.reply(403, {'error': 'ページを再読込してください'})
        if self.path != '/api' or self.headers.get('Content-Type') != 'application/json':
            return self.reply(400, {'error': 'Invalid request'})
        store = Store(self.server.db_path)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2_000_000:
                raise ValueError('リクエストは2MB以内です')
            request = json.loads(self.rfile.read(size))
            if request['action'] in ('inspect', 'preview', 'create'):
                raw = base64.b64decode(request['csv'], validate=True)
                encoding = request.get('encoding', 'utf-8-sig')
                if encoding not in ('utf-8-sig', 'cp932'):
                    raise ValueError('未対応の文字コードです')
                if request['action'] == 'inspect':
                    headers = next(csv.reader(io.StringIO(raw.decode(encoding)), strict=True), [])
                    if not headers or len(set(headers)) != len(headers) or any(not x for x in headers):
                        raise ValueError('ヘッダーが空または重複しています')
                    return self.reply(200, {'headers': headers})
                columns = request.get('columns')
                if request['action'] == 'preview':
                    items = read_csv(raw, encoding, columns)
                    digest = hashlib.sha256(raw).hexdigest()
                    duplicates = [x['id'] for x in store.list() if x['source_hash'] == digest]
                    return self.reply(200, {'items': items[:100], 'count': len(items), 'duplicates': duplicates})
                s = store.create(raw, request['locations'], request['actor'], encoding, columns, request.get('source_name', ''))
            else:
                s = store.change(request['id'], request['revision'], request['action'], request['actor'], request.get('payload'))
            self.reply(200, {'id': s['id']})
        except (ValueError, KeyError, TypeError, UnicodeError, csv.Error) as exc:
            self.reply(400, {'error': str(exc)})
        finally:
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

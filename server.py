import http.server
import socketserver
import json
import urllib.parse
import os
import mimetypes
import sys

# Database selection based on DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    def get_db_connection():
        return psycopg2.connect(DATABASE_URL)
    def init_db():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS Users (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, name_changed INTEGER DEFAULT 0);")
        c.execute("CREATE TABLE IF NOT EXISTS Persons (id SERIAL PRIMARY KEY, name TEXT);")
        c.execute("CREATE TABLE IF NOT EXISTS Ratings (id SERIAL PRIMARY KEY, person_id INTEGER, rating REAL, image_data TEXT);")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);")
        c.execute("INSERT INTO settings (key, value) VALUES ('background_url', '') ON CONFLICT (key) DO NOTHING;")
        c.execute("SELECT * FROM Users WHERE username = 'shafin'")
        if not c.fetchone():
            c.execute("INSERT INTO Users (username, password, role) VALUES ('shafin', '29743115', 'admin')")
        conn.commit()
        c.close()
        conn.close()
else:
    import sqlite3
    def get_db_connection():
        return sqlite3.connect('facerater.db')
    def init_db():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, name_changed INTEGER DEFAULT 0);")
        c.execute("CREATE TABLE IF NOT EXISTS Persons (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);")
        c.execute("CREATE TABLE IF NOT EXISTS Ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER, rating REAL, image_data TEXT);")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('background_url', '');")
        c.execute("SELECT * FROM Users WHERE username = 'shafin'")
        if not c.fetchone():
            c.execute("INSERT INTO Users (username, password, role) VALUES ('shafin', '29743115', 'admin')")
        conn.commit()
        c.close()
        conn.close()

PORT = int(os.environ.get("PORT", 8000))

class FaceRaterAPI(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="public", **kwargs)

    def send_json(self, data, status=200):
        try:
            json_data = json.dumps(data, default=lambda x: float(x) if hasattr(x, '__float__') else str(x))
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json_data.encode('utf-8'))
        except Exception as e:
            print(f"JSON error: {e}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # --- Root redirect ---
        if path == '/':
            self.send_response(302)
            self.send_header('Location', '/login.html')
            self.end_headers()
            return

        # --- API endpoints ---
        if path == '/api/data':
            conn = get_db_connection()
            if DATABASE_URL:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                query = "SELECT p.id as id, p.name as name, ROUND(CAST(AVG(r.rating) AS numeric), 2) as rating FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name ORDER BY p.id DESC"
                c.execute(query)
                data = c.fetchall()
            else:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                query = "SELECT p.id as id, p.name as name, ROUND(AVG(r.rating), 2) as rating FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name ORDER BY p.id DESC"
                c.execute(query)
                rows = c.fetchall()
                data = [dict(row) for row in rows]
            conn.close()
            self.send_json(data)

        elif path == '/api/users':
            conn = get_db_connection()
            if DATABASE_URL:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("SELECT id, username, role, name_changed FROM Users")
                users = c.fetchall()
            else:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT id, username, role, name_changed FROM Users")
                rows = c.fetchall()
                users = [dict(row) for row in rows]
            conn.close()
            self.send_json(users)

        elif path == '/api/settings/background':
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='background_url'")
            res = c.fetchone()
            conn.close()
            self.send_json({"url": res[0] if res else ""})

        elif path == '/api/export/ratings':
            conn = get_db_connection()
            c = conn.cursor()
            if DATABASE_URL:
                c.execute("SELECT p.id, p.name, ROUND(CAST(AVG(r.rating) AS numeric), 2) FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name")
            else:
                c.execute("SELECT p.id, p.name, ROUND(AVG(r.rating), 2) FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name")
            rows = c.fetchall()
            conn.close()
            csv_data = "ID,Name,Mean Rating\n" + "\n".join([f"{r[0]},{r[1]},{r[2]}" for r in rows])
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.send_header('Content-Disposition', 'attachment; filename="ratings.csv"')
            self.end_headers()
            self.wfile.write(csv_data.encode('utf-8'))

        # --- Static files (from 'public' folder) ---
        else:
            # Security: prevent directory traversal
            if '..' in path:
                self.send_error(403)
                return
            file_path = os.path.join('public', path.lstrip('/'))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(file_path)
                if content_type:
                    self.send_header('Content-Type', content_type)
                else:
                    self.send_header('Content-Type', 'application/octet-stream')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}
        conn = get_db_connection()
        c = conn.cursor()

        try:
            if parsed.path == '/api/login':
                if DATABASE_URL:
                    c.execute("SELECT role FROM Users WHERE username=%s AND password=%s", (body.get('username'), body.get('password')))
                else:
                    c.execute("SELECT role FROM Users WHERE username=? AND password=?", (body.get('username'), body.get('password')))
                user = c.fetchone()
                if user:
                    self.send_json({"status": "success", "role": user[0]})
                else:
                    self.send_json({"error": "Invalid"}, 401)

            elif parsed.path == '/api/rate':
                if DATABASE_URL:
                    c.execute("SELECT id FROM Persons WHERE name=%s", (body['name'],))
                else:
                    c.execute("SELECT id FROM Persons WHERE name=?", (body['name'],))
                row = c.fetchone()
                if row:
                    p_id = row[0]
                else:
                    if DATABASE_URL:
                        c.execute("INSERT INTO Persons (name) VALUES (%s) RETURNING id", (body['name'],))
                        p_id = c.fetchone()[0]
                    else:
                        c.execute("INSERT INTO Persons (name) VALUES (?)", (body['name'],))
                        p_id = c.lastrowid
                if DATABASE_URL:
                    c.execute("INSERT INTO Ratings (person_id, rating, image_data) VALUES (%s, %s, %s)", (p_id, body['rating'], body['image']))
                else:
                    c.execute("INSERT INTO Ratings (person_id, rating, image_data) VALUES (?, ?, ?)", (p_id, body['rating'], body['image']))
                self.send_json({"status": "success"})

            elif parsed.path == '/api/data/remove':
                if DATABASE_URL:
                    c.execute("DELETE FROM Ratings WHERE person_id=%s", (body['id'],))
                    c.execute("DELETE FROM Persons WHERE id=%s", (body['id'],))
                else:
                    c.execute("DELETE FROM Ratings WHERE person_id=?", (body['id'],))
                    c.execute("DELETE FROM Persons WHERE id=?", (body['id'],))
                self.send_json({"status": "success"})

            elif parsed.path == '/api/users/add':
                if DATABASE_URL:
                    c.execute("INSERT INTO Users (username, password, role) VALUES (%s, %s, %s)", (body['username'], body['password'], body['role']))
                else:
                    c.execute("INSERT INTO Users (username, password, role) VALUES (?, ?, ?)", (body['username'], body['password'], body['role']))
                self.send_json({"status": "success"})

            elif parsed.path == '/api/users/remove':
                if DATABASE_URL:
                    c.execute("DELETE FROM Users WHERE id=%s", (body['id'],))
                else:
                    c.execute("DELETE FROM Users WHERE id=?", (body['id'],))
                self.send_json({"status": "success"})

            elif parsed.path == '/api/settings/background':
                if DATABASE_URL:
                    c.execute("UPDATE settings SET value=%s WHERE key='background_url'", (body.get('image'),))
                else:
                    c.execute("UPDATE settings SET value=? WHERE key='background_url'", (body.get('image'),))
                self.send_json({"status": "success"})

            elif parsed.path == '/api/logout':
                self.send_json({"status": "success"})

            conn.commit()
        except Exception as e:
            conn.rollback()
            self.send_json({"error": str(e)}, 500)
        finally:
            c.close()
            conn.close()

if __name__ == "__main__":
    init_db()
    with socketserver.TCPServer(("", PORT), FaceRaterAPI) as httpd:
        print(f"🚀 Server running on http://localhost:{PORT}")
        httpd.serve_forever()
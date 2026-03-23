import os
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
# This single line handles ALL the CORS headaches from GitHub Pages!
CORS(app)

PORT = int(os.environ.get("PORT", 8000))
# On Render, you will set this DATABASE_URL in the environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_ZRI8SXwxWGd5@ep-dawn-scene-a1vipx7c-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require")

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

# --- GET ROUTES ---

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "Face Analyzer Flask API is running!"})

@app.route('/api/data', methods=['GET'])
def get_data():
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = "SELECT p.id as id, p.name as name, ROUND(CAST(AVG(r.rating) AS numeric), 2) as rating FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name ORDER BY p.id DESC"
    c.execute(query)
    # Convert decimals to floats for JSON serialization
    data = [{k: float(v) if hasattr(v, '__float__') else v for k, v in row.items()} for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("SELECT id, username, role, name_changed FROM Users")
    users = c.fetchall()
    conn.close()
    return jsonify(users)

@app.route('/api/settings/background', methods=['GET'])
def get_background():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='background_url'")
    res = c.fetchone()
    conn.close()
    return jsonify({"url": res[0] if res else ""})

@app.route('/api/export/ratings', methods=['GET'])
def export_ratings():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT p.id, p.name, ROUND(CAST(AVG(r.rating) AS numeric), 2) FROM Ratings r JOIN Persons p ON r.person_id = p.id GROUP BY p.id, p.name")
    rows = c.fetchall()
    conn.close()
    
    csv_data = "ID,Name,Mean Rating\n" + "\n".join([f"{r[0]},{r[1]},{r[2]}" for r in rows])
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ratings.csv"}
    )

# --- POST ROUTES ---

@app.route('/api/login', methods=['POST'])
def login():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT role FROM Users WHERE username=%s AND password=%s", (body.get('username'), body.get('password')))
        user = c.fetchone()
        if user:
            return jsonify({"status": "success", "role": user[0]})
        return jsonify({"error": "Invalid credentials"}), 401
    finally:
        c.close()
        conn.close()

@app.route('/api/rate', methods=['POST'])
def rate_person():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM Persons WHERE name = %s", (body.get('name'),))
        row = c.fetchone()
        p_id = row[0] if row else None
        if not p_id:
            c.execute("INSERT INTO Persons (name) VALUES (%s) RETURNING id", (body.get('name'),))
            p_id = c.fetchone()[0]
            
        c.execute("INSERT INTO Ratings (person_id, rating, image_data) VALUES (%s, %s, %s)", 
                  (p_id, body.get('rating'), body.get('image')))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        c.close()
        conn.close()

@app.route('/api/data/remove', methods=['POST'])
def remove_data():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM Ratings WHERE person_id = %s", (body.get('id'),))
        c.execute("DELETE FROM Persons WHERE id = %s", (body.get('id'),))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        c.close()
        conn.close()

@app.route('/api/users/add', methods=['POST'])
def add_user():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Users (username, password, role) VALUES (%s, %s, %s)", 
                  (body.get('username'), body.get('password'), body.get('role')))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        c.close()
        conn.close()

@app.route('/api/users/remove', methods=['POST'])
def remove_user():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM Users WHERE id = %s", (body.get('id'),))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        c.close()
        conn.close()

@app.route('/api/settings/background', methods=['POST'])
def update_background():
    body = request.json or {}
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("UPDATE settings SET value=%s WHERE key='background_url'", (body.get('image'),))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        c.close()
        conn.close()

@app.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({"status": "success"})

if __name__ == "__main__":
    init_db()
    print(f"🚀 Flask Server Online on Port {PORT}")
    # '0.0.0.0' is required for Render to expose the port externally
    app.run(host='0.0.0.0', port=PORT)
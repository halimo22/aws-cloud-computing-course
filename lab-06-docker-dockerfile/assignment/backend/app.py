"""Notes API for the Lab 6 assignment.

The app has exactly one setting: DATABASE_URL, a PostgreSQL connection string,
for example postgresql://notes:secret@db:5432/notes
It never reads a host, user or password from anywhere else.
"""

import os
import socket
from urllib.parse import urlsplit

import psycopg2
from flask import Flask, jsonify, request

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def query(sql, params=()):
    if not DATABASE_URL:
        raise psycopg2.OperationalError("DATABASE_URL is not set")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    try:
        with conn, conn.cursor() as cur:  # commits on success, rolls back on error
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    finally:
        conn.close()


def ensure_table():
    # ponytail: created on demand, no migrations tool; fine for one table.
    query("""CREATE TABLE IF NOT EXISTS messages (
               id SERIAL PRIMARY KEY,
               text VARCHAR(500) NOT NULL,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


@app.errorhandler(psycopg2.Error)
def database_error(error):
    return jsonify(error=str(error).strip()), 503


@app.get("/api/health")
def health():  # used by HEALTHCHECK: answers even when the database is down
    return jsonify(status="ok")


@app.get("/api/info")
def info():
    url = urlsplit(DATABASE_URL)
    data = {
        "backend_hostname": socket.gethostname(),  # the container ID
        "db_host": url.hostname,  # the parts of the connection string,
        "db_port": url.port,  # never the password
        "db_name": url.path.lstrip("/") or None,
        "db_user": url.username,
    }
    try:
        data["db_version"] = query("SELECT version()")[0][0]
    except psycopg2.Error as error:
        data["db_error"] = str(error).strip()
    return jsonify(data)


@app.get("/api/messages")
def list_messages():
    ensure_table()
    rows = query("SELECT id, text, created_at FROM messages ORDER BY id DESC LIMIT 50")
    return jsonify([{"id": i, "text": t, "created_at": c.isoformat()} for i, t, c in rows])


@app.post("/api/messages")
def add_message():
    text = str((request.get_json(silent=True) or {}).get("text", "")).strip()
    if not 1 <= len(text) <= 500:
        return jsonify(error="text must be 1 to 500 characters"), 400
    ensure_table()
    (row,) = query("INSERT INTO messages (text) VALUES (%s) RETURNING id, created_at", (text,))
    return jsonify(id=row[0], text=text, created_at=row[1].isoformat()), 201

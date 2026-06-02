import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'glamour.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fabrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            fabric_type TEXT,
            color       TEXT,
            pattern     TEXT,
            yardage     REAL,
            location    TEXT,
            supplier    TEXT,
            notes       TEXT,
            photo_path  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS email_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id    TEXT UNIQUE,
            sender_name   TEXT,
            sender_email  TEXT,
            subject       TEXT,
            body          TEXT,
            received_at   TEXT,
            status        TEXT DEFAULT 'new',
            estimate_id   TEXT,
            logged_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            firm            TEXT,
            email           TEXT,
            phone           TEXT,
            location        TEXT,
            notes           TEXT,
            status          TEXT DEFAULT 'new',
            emailed_at      TIMESTAMP,
            followup1_at    TIMESTAMP,
            followup2_at    TIMESTAMP,
            responded_at    TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# ── Fabric helpers ──────────────────────────────────────────────────────────

def add_fabric(client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path):
    conn = get_db()
    conn.execute(
        """INSERT INTO fabrics
           (client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path)
    )
    conn.commit()
    conn.close()


def get_fabrics(search='', client=''):
    conn = get_db()
    query = "SELECT * FROM fabrics WHERE 1=1"
    params = []
    if client:
        query += " AND LOWER(client_name) = LOWER(?)"
        params.append(client)
    if search:
        query += " AND (LOWER(client_name) LIKE ? OR LOWER(fabric_type) LIKE ? OR LOWER(color) LIKE ? OR LOWER(notes) LIKE ?)"
        term = f'%{search.lower()}%'
        params.extend([term, term, term, term])
    query += " ORDER BY client_name, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_fabric(fabric_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM fabrics WHERE id=?", (fabric_id,)).fetchone()
    conn.close()
    return row


def update_fabric(fabric_id, client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path=None):
    conn = get_db()
    if photo_path:
        conn.execute(
            """UPDATE fabrics SET client_name=?, fabric_type=?, color=?, pattern=?, yardage=?,
               location=?, supplier=?, notes=?, photo_path=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path, fabric_id)
        )
    else:
        conn.execute(
            """UPDATE fabrics SET client_name=?, fabric_type=?, color=?, pattern=?, yardage=?,
               location=?, supplier=?, notes=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (client_name, fabric_type, color, pattern, yardage, location, supplier, notes, fabric_id)
        )
    conn.commit()
    conn.close()


def delete_fabric(fabric_id):
    conn = get_db()
    conn.execute("DELETE FROM fabrics WHERE id=?", (fabric_id,))
    conn.commit()
    conn.close()


def get_clients():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT client_name FROM fabrics ORDER BY client_name").fetchall()
    conn.close()
    return [r['client_name'] for r in rows]


def get_fabric_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM fabrics").fetchone()[0]
    clients = conn.execute("SELECT COUNT(DISTINCT client_name) FROM fabrics").fetchone()[0]
    conn.close()
    return {'total': total, 'clients': clients}


# ── Email log helpers ────────────────────────────────────────────────────────

def log_email(message_id, sender_name, sender_email, subject, body, received_at):
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO email_log
               (message_id, sender_name, sender_email, subject, body, received_at)
               VALUES (?,?,?,?,?,?)""",
            (message_id, sender_name, sender_email, subject, body, received_at)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def mark_email_used(message_id, estimate_id=''):
    conn = get_db()
    conn.execute(
        "UPDATE email_log SET status='estimate_created', estimate_id=? WHERE message_id=?",
        (estimate_id, message_id)
    )
    conn.commit()
    conn.close()


def get_email_log():
    conn = get_db()
    rows = conn.execute("SELECT * FROM email_log ORDER BY logged_at DESC LIMIT 50").fetchall()
    conn.close()
    return rows


# ── Lead helpers ─────────────────────────────────────────────────────────────

def add_lead(name, firm, email, phone, location, notes=''):
    conn = get_db()
    conn.execute(
        "INSERT INTO leads (name, firm, email, phone, location, notes) VALUES (?,?,?,?,?,?)",
        (name, firm, email, phone, location, notes)
    )
    conn.commit()
    conn.close()


def get_leads(status=''):
    conn = get_db()
    if status:
        rows = conn.execute("SELECT * FROM leads WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def get_lead(lead_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    conn.close()
    return row


def update_lead_status(lead_id, status, timestamp_field=None):
    conn = get_db()
    if timestamp_field:
        conn.execute(f"UPDATE leads SET status=?, {timestamp_field}=CURRENT_TIMESTAMP WHERE id=?", (status, lead_id))
    else:
        conn.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
    conn.commit()
    conn.close()


def update_lead(lead_id, name, firm, email, phone, location, notes):
    conn = get_db()
    conn.execute(
        "UPDATE leads SET name=?, firm=?, email=?, phone=?, location=?, notes=? WHERE id=?",
        (name, firm, email, phone, location, notes, lead_id)
    )
    conn.commit()
    conn.close()


def delete_lead(lead_id):
    conn = get_db()
    conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()


def get_lead_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    emailed = conn.execute("SELECT COUNT(*) FROM leads WHERE status != 'new'").fetchone()[0]
    responded = conn.execute("SELECT COUNT(*) FROM leads WHERE status='responded'").fetchone()[0]
    converted = conn.execute("SELECT COUNT(*) FROM leads WHERE status='converted'").fetchone()[0]
    conn.close()
    return {'total': total, 'emailed': emailed, 'responded': responded, 'converted': converted}

import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

_raw = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(os.path.dirname(__file__), 'glamour.db')}")
DATABASE_URL = _raw.replace('postgres://', 'postgresql://', 1)

_is_sqlite = DATABASE_URL.startswith('sqlite')

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=StaticPool if _is_sqlite else None,
)


def _conn():
    return engine.connect()


def init_db():
    with _conn() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fabrics (
                id          SERIAL PRIMARY KEY,
                client_name TEXT NOT NULL,
                fabric_type TEXT,
                color       TEXT,
                pattern     TEXT,
                yardage     FLOAT,
                location    TEXT,
                supplier    TEXT,
                notes       TEXT,
                photo_path  TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if not _is_sqlite else text("""
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
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS email_log (
                id            SERIAL PRIMARY KEY,
                message_id    TEXT UNIQUE,
                sender_name   TEXT,
                sender_email  TEXT,
                subject       TEXT,
                body          TEXT,
                received_at   TEXT,
                status        TEXT DEFAULT 'new',
                estimate_id   TEXT,
                logged_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """) if not _is_sqlite else text("""
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
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS leads (
                id              SERIAL PRIMARY KEY,
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
            )
        """) if not _is_sqlite else text("""
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
            )
        """))
        conn.commit()


def _rows(result):
    return [dict(row._mapping) for row in result]


def _row(result):
    row = result.fetchone()
    return dict(row._mapping) if row else None


# ── Fabric helpers ─────────────────────────────────────────────────────────

def add_fabric(client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path):
    with _conn() as conn:
        conn.execute(text(
            "INSERT INTO fabrics (client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path) "
            "VALUES (:cn,:ft,:co,:pa,:ya,:lo,:su,:no,:ph)"
        ), dict(cn=client_name, ft=fabric_type, co=color, pa=pattern, ya=yardage,
                lo=location, su=supplier, no=notes, ph=photo_path))
        conn.commit()


def get_fabrics(search='', client=''):
    q = "SELECT * FROM fabrics WHERE 1=1"
    params = {}
    if client:
        q += " AND LOWER(client_name) = LOWER(:client)"
        params['client'] = client
    if search:
        q += " AND (LOWER(client_name) LIKE :s OR LOWER(fabric_type) LIKE :s OR LOWER(color) LIKE :s OR LOWER(notes) LIKE :s)"
        params['s'] = f'%{search.lower()}%'
    q += " ORDER BY client_name, created_at DESC"
    with _conn() as conn:
        return _rows(conn.execute(text(q), params))


def get_fabric(fabric_id):
    with _conn() as conn:
        return _row(conn.execute(text("SELECT * FROM fabrics WHERE id=:id"), {'id': fabric_id}))


def update_fabric(fabric_id, client_name, fabric_type, color, pattern, yardage, location, supplier, notes, photo_path=None):
    with _conn() as conn:
        if photo_path:
            conn.execute(text(
                "UPDATE fabrics SET client_name=:cn, fabric_type=:ft, color=:co, pattern=:pa, yardage=:ya, "
                "location=:lo, supplier=:su, notes=:no, photo_path=:ph, updated_at=CURRENT_TIMESTAMP WHERE id=:id"
            ), dict(cn=client_name, ft=fabric_type, co=color, pa=pattern, ya=yardage,
                    lo=location, su=supplier, no=notes, ph=photo_path, id=fabric_id))
        else:
            conn.execute(text(
                "UPDATE fabrics SET client_name=:cn, fabric_type=:ft, color=:co, pattern=:pa, yardage=:ya, "
                "location=:lo, supplier=:su, notes=:no, updated_at=CURRENT_TIMESTAMP WHERE id=:id"
            ), dict(cn=client_name, ft=fabric_type, co=color, pa=pattern, ya=yardage,
                    lo=location, su=supplier, no=notes, id=fabric_id))
        conn.commit()


def delete_fabric(fabric_id):
    with _conn() as conn:
        conn.execute(text("DELETE FROM fabrics WHERE id=:id"), {'id': fabric_id})
        conn.commit()


def get_clients():
    with _conn() as conn:
        rows = _rows(conn.execute(text("SELECT DISTINCT client_name FROM fabrics ORDER BY client_name")))
        return [r['client_name'] for r in rows]


def get_fabric_stats():
    with _conn() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM fabrics")).scalar()
        clients = conn.execute(text("SELECT COUNT(DISTINCT client_name) FROM fabrics")).scalar()
        return {'total': total or 0, 'clients': clients or 0}


# ── Email log helpers ──────────────────────────────────────────────────────

def log_email(message_id, sender_name, sender_email, subject, body, received_at):
    try:
        with _conn() as conn:
            conn.execute(text(
                "INSERT INTO email_log (message_id, sender_name, sender_email, subject, body, received_at) "
                "VALUES (:mid,:sn,:se,:su,:bo,:ra) ON CONFLICT (message_id) DO NOTHING"
                if not _is_sqlite else
                "INSERT OR IGNORE INTO email_log (message_id, sender_name, sender_email, subject, body, received_at) "
                "VALUES (:mid,:sn,:se,:su,:bo,:ra)"
            ), dict(mid=message_id, sn=sender_name, se=sender_email, su=subject, bo=body, ra=received_at))
            conn.commit()
    except Exception:
        pass


def mark_email_used(message_id, estimate_id=''):
    with _conn() as conn:
        conn.execute(text(
            "UPDATE email_log SET status='estimate_created', estimate_id=:eid WHERE message_id=:mid"
        ), {'eid': estimate_id, 'mid': message_id})
        conn.commit()


# ── Lead helpers ───────────────────────────────────────────────────────────

def add_lead(name, firm, email, phone, location, notes=''):
    with _conn() as conn:
        conn.execute(text(
            "INSERT INTO leads (name, firm, email, phone, location, notes) VALUES (:na,:fi,:em,:ph,:lo,:no)"
        ), dict(na=name, fi=firm, em=email, ph=phone, lo=location, no=notes))
        conn.commit()


def get_leads(status=''):
    with _conn() as conn:
        if status:
            return _rows(conn.execute(text("SELECT * FROM leads WHERE status=:s ORDER BY created_at DESC"), {'s': status}))
        return _rows(conn.execute(text("SELECT * FROM leads ORDER BY created_at DESC")))


def get_lead(lead_id):
    with _conn() as conn:
        return _row(conn.execute(text("SELECT * FROM leads WHERE id=:id"), {'id': lead_id}))


def update_lead_status(lead_id, status, timestamp_field=None):
    with _conn() as conn:
        if timestamp_field:
            conn.execute(text(f"UPDATE leads SET status=:s, {timestamp_field}=CURRENT_TIMESTAMP WHERE id=:id"),
                         {'s': status, 'id': lead_id})
        else:
            conn.execute(text("UPDATE leads SET status=:s WHERE id=:id"), {'s': status, 'id': lead_id})
        conn.commit()


def update_lead(lead_id, name, firm, email, phone, location, notes):
    with _conn() as conn:
        conn.execute(text(
            "UPDATE leads SET name=:na, firm=:fi, email=:em, phone=:ph, location=:lo, notes=:no WHERE id=:id"
        ), dict(na=name, fi=firm, em=email, ph=phone, lo=location, no=notes, id=lead_id))
        conn.commit()


def delete_lead(lead_id):
    with _conn() as conn:
        conn.execute(text("DELETE FROM leads WHERE id=:id"), {'id': lead_id})
        conn.commit()


def get_lead_stats():
    with _conn() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM leads")).scalar() or 0
        emailed = conn.execute(text("SELECT COUNT(*) FROM leads WHERE status != 'new'")).scalar() or 0
        responded = conn.execute(text("SELECT COUNT(*) FROM leads WHERE status='responded'")).scalar() or 0
        converted = conn.execute(text("SELECT COUNT(*) FROM leads WHERE status='converted'")).scalar() or 0
        return {'total': total, 'emailed': emailed, 'responded': responded, 'converted': converted}

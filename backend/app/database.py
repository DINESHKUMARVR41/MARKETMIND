import sqlite3, json, os
from pathlib import Path
from datetime import datetime, timezone

_configured_db_path = Path(os.getenv("DATABASE_PATH", "marketmind.db"))
DB_PATH = str(_configured_db_path if _configured_db_path.is_absolute() else Path(__file__).resolve().parents[1] / _configured_db_path)

def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, symbol TEXT NOT NULL, company TEXT NOT NULL, decision TEXT NOT NULL, confidence REAL NOT NULL, amount REAL NOT NULL, report TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, created_at TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL, price REAL NOT NULL, amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'PAPER');
        ''')
        # One paper execution per analysis, including concurrent requests.
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_run_id_unique ON trades(run_id)')

def save_run(report):
    with connect() as db:
        cur = db.execute("INSERT INTO runs(created_at,symbol,company,decision,confidence,amount,report) VALUES(?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), report['symbol'], report['company'], report['decision'], 0.0, report['investment_amount'], json.dumps(report)))
        return cur.lastrowid

def update_run_report(run_id, report):
    with connect() as db:
        db.execute('UPDATE runs SET report=? WHERE id=?', (json.dumps(report), run_id))

def save_trade(run_id, symbol, side, qty, price, amount):
    try:
        with connect() as db:
            cur = db.execute("INSERT INTO trades(run_id,created_at,symbol,side,quantity,price,amount) VALUES(?,?,?,?,?,?,?)", (run_id, datetime.now(timezone.utc).isoformat(), symbol, side, qty, price, amount))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None

def trade_exists_for_run(run_id):
    with connect() as db:
        row=db.execute("SELECT id FROM trades WHERE run_id=? LIMIT 1",(run_id,)).fetchone()
        return bool(row)

def list_runs(limit=30):
    with connect() as db:
        rows = db.execute("SELECT id,created_at,symbol,company,decision,confidence,amount FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), 'confidence': (r['confidence'] if r['confidence'] and r['confidence'] > 0 else None)} for r in rows]

def get_run(run_id):
    with connect() as db:
        row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row: return None
        data = dict(row); data['report'] = json.loads(data['report']); return data

def list_trades():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100").fetchall()]


def save_adal_event(event_id, payload):
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS adal_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            received_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )''')
        cur = db.execute('INSERT OR IGNORE INTO adal_events(event_id,received_at,payload) VALUES(?,?,?)',
                         (event_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)))
        return cur.rowcount == 1


def list_adal_events(limit=30):
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS adal_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            received_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )''')
        rows = db.execute('SELECT id,event_id,received_at,payload FROM adal_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows]

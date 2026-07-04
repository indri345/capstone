import sqlite3, json
from datetime import datetime

DB = 'db.sqlite3'
EVENT_ID = 25

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

# Fetch event
cur.execute('SELECT event_id, event_name, status, registration_deadline, capacity FROM events WHERE event_id = ?', (EVENT_ID,))
e = cur.fetchone()

# Fetch registrations
cur.execute('SELECT registration_id, full_name, email, registered_at FROM event_registrations WHERE event_id = ?', (EVENT_ID,))
regs = [dict(r) for r in cur.fetchall()]

out = {'event': None, 'registrations': regs}
if e:
    ev = dict(e)
    rd = ev.get('registration_deadline')
    out['event'] = ev

print(json.dumps(out, indent=2, default=str))
con.close()

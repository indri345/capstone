import sqlite3, json
DB = 'db.sqlite3'
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cur.fetchall()]
print(json.dumps(tables, indent=2))
con.close()

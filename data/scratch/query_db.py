import sqlite3
import os

db_path = r'c:\Users\pushp\Music\AI_Agent_Naukri_refactored\refactored\data\naukri_agent.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
tables = [t[0] for t in c.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
print('Tables:', tables)
for t in tables:
    print(f'\n=== Schema of {t} ===')
    schema = c.execute(f"PRAGMA table_info({t})").fetchall()
    for col in schema:
        print(f"  {col[1]} ({col[2]})")
    cnt = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f"  Total rows: {cnt}")
    if cnt > 0:
        print("  Sample rows:")
        rows = c.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 3").fetchall()
        for r in rows:
            print("    ", r)
conn.close()

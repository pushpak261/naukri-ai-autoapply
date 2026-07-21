import sqlite3
import glob
import os

db_files = glob.glob(r'c:\Users\pushp\Music\AI_Agent_Naukri_refactored\refactored\data\*.db')
for db_path in db_files:
    print(f"\n--- Checking DB: {os.path.basename(db_path)} ---")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        tables = [t[0] for t in c.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()]
        for t in tables:
            cnt = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'  {t}: {cnt} rows')
            if cnt > 0 and t == 'applications':
                print("  Sample applications:")
                rows = c.execute("SELECT id, status, error_message, applied_at FROM applications ORDER BY rowid DESC LIMIT 3").fetchall()
                for r in rows:
                    print("    ", r)
        conn.close()
    except Exception as e:
        print("  Error:", e)

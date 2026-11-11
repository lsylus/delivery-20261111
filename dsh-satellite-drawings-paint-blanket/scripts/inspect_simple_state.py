from pathlib import Path
import json
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
for name in ('simple-v1-trial','simple-v1-large'):
    db=ROOT/'work'/name/'data/engineering.sqlite3'
    with sqlite3.connect(db) as connection:
        print(name)
        for row in connection.execute('select body from runs order by rowid desc limit 4'):
            run=json.loads(row[0]);print({k:run.get(k) for k in ('id','operation','state','error','checks','started_at','finished_at')})

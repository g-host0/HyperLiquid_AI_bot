# view_positions.py
import sqlite3
import pandas as pd

conn = sqlite3.connect('positions.db')
df = pd.read_sql_query("SELECT * FROM positions ORDER BY opened_at DESC", conn)
conn.close()

if len(df) == 0:
    print("Позиций пока нет")
else:
    print("\n" + "="*120)
    print("ОТКРЫТЫЕ ПОЗИЦИИ:")
    print("="*120)
    open_df = df[df['status']=='open']
    if len(open_df) > 0:
        print(open_df[['id', 'symbol', 'side', 'quantity', 'entry_price', 'atr', 'stop_loss', 'take_profit_hit', 'opened_at']].to_string(index=False))
    else:
        print("Нет открытых позиций")
    
    print("\n" + "="*120)
    print("ЗАКРЫТЫЕ ПОЗИЦИИ:")
    print("="*120)
    closed_df = df[df['status']=='closed']
    if len(closed_df) > 0:
        print(closed_df[['id', 'symbol', 'side', 'quantity', 'entry_price', 'profit', 'opened_at']].to_string(index=False))
    else:
        print("Нет закрытых позиций")

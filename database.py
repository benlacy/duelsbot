import sqlite3

# Connect to or create the database
conn = sqlite3.connect('mmr.db')
cursor = conn.cursor()

# Create the players table if it doesn't exist
cursor.execute('''
CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player1_id TEXT,
    player2_id TEXT,
    status TEXT, -- PENDING, CONFIRMED, REPORTED, COMPLETE
    winner_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
''')

conn.commit()
conn.close()
import sqlite3

DB_PATH = "bot_data.db"


def get_connection():
    """Opens a connection to the SQLite database file (creates it if missing)."""
    return sqlite3.connect(DB_PATH)


def init_db():
    """Creates the tables if they don't already exist. Safe to call every startup."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            chat_id INTEGER PRIMARY KEY
        )
    """)

    conn.commit()
    conn.close()


def add_subscriber(chat_id: int):
    """Records a chat_id as having used the bot. Does nothing if already present."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()


def get_all_subscribers() -> set:
    """Returns every known chat_id as a set of ints."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM subscribers")
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}
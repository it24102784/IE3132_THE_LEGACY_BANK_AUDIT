import sqlite3


def init_db():
    conn = sqlite3.connect('legacy_portal.db')
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # Seed legacy admin user
    cursor.execute("DELETE FROM users")
    cursor.execute('''
        INSERT INTO users (username, password, employee_id, role)
        VALUES ('admin_legacy', 'SuperSecretHash2026!', 'EMP-9901', 'Administrator')
    ''')

    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()

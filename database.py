import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        email TEXT,
        password_hash TEXT,
        joined_date DATE NOT NULL,
        left_date DATE
    );
    """)
    
    # 2. Create Groups Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT
    );
    """)
    
    # 3. Create Group Memberships Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_memberships (
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at DATE NOT NULL,
        left_at DATE,
        PRIMARY KEY (group_id, user_id),
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # 4. Create Expenses Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        exchange_rate REAL NOT NULL,
        amount_inr REAL NOT NULL,
        paid_by_user_id INTEGER NOT NULL,
        split_type TEXT NOT NULL, -- 'equal', 'unequal', 'percentage', 'share'
        date DATE NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (paid_by_user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # 5. Create Expense Splits Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expense_splits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        share_ratio REAL, -- percentage, share multiplier or split coefficient
        share_amount REAL NOT NULL, -- final portion in INR
        FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # 6. Create Payments (Settlements) Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        currency TEXT NOT NULL,
        exchange_rate REAL NOT NULL,
        amount_inr REAL NOT NULL,
        date DATE NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    
    # 7. Create Imports Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 8. Create Import Anomalies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_anomalies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id INTEGER NOT NULL,
        row_index INTEGER NOT NULL,
        anomaly_type TEXT NOT NULL,
        original_data TEXT NOT NULL,
        detected_issue TEXT NOT NULL,
        action_taken TEXT NOT NULL,
        FOREIGN KEY (import_id) REFERENCES imports(id) ON DELETE CASCADE
    );
    """)
    
    # Seed default users
    # Inconsistent names or casings in CSV are mapped to these canonical names
    default_users = [
        ("Aisha", "aisha@example.com", "2026-02-01", None),
        ("Rohan", "rohan@example.com", "2026-02-01", None),
        ("Priya", "priya@example.com", "2026-02-01", None),
        ("Meera", "meera@example.com", "2026-02-01", "2026-03-31"),
        ("Dev", "dev@example.com", "2026-02-08", "2026-03-14"),
        ("Sam", "sam@example.com", "2026-04-10", None),
        ("Kabir", "kabir@example.com", "2026-03-11", "2026-03-11")
    ]
    
    for name, email, joined, left in default_users:
        cursor.execute("""
        INSERT OR IGNORE INTO users (name, email, password_hash, joined_date, left_date)
        VALUES (?, ?, 'scrypt:32768:8:1$default_password_hash', ?, ?);
        """, (name, email, joined, left))
        
    # Seed a default group for flat expenses
    cursor.execute("SELECT id FROM groups WHERE name = 'Flat Expenses' LIMIT 1;")
    group_row = cursor.fetchone()
    if not group_row:
        cursor.execute("INSERT INTO groups (name, description) VALUES ('Flat Expenses', 'Shared expenses of the apartment flatmates');")
        group_id = cursor.lastrowid
    else:
        group_id = group_row[0]
        
    # Associate default memberships
    cursor.execute("SELECT id, name FROM users;")
    all_users = cursor.fetchall()
    for user_row in all_users:
        uid = user_row['id']
        uname = user_row['name']
        
        # joined/left dates for group membership
        joined_date = "2026-02-01"
        left_date = None
        if uname == "Dev":
            joined_date = "2026-02-08"
            left_date = "2026-03-14"
        elif uname == "Sam":
            joined_date = "2026-04-10"
        elif uname == "Meera":
            left_date = "2026-03-31"
        elif uname == "Kabir":
            joined_date = "2026-03-11"
            left_date = "2026-03-11"
            
        cursor.execute("""
        INSERT OR REPLACE INTO group_memberships (group_id, user_id, joined_at, left_at)
        VALUES (?, ?, ?, ?);
        """, (group_id, uid, joined_date, left_date))
        
    conn.commit()
    conn.close()
    print("Database schema initialized and seeded successfully.")

if __name__ == "__main__":
    init_db()

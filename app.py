from flask import Flask, request, jsonify, session, send_from_directory, render_template
import sqlite3
import os
import json
from database import get_db_connection, init_db
import importer
import balances

app = Flask(__name__)
app.secret_key = 'antigravity_secret_key_12345_spreetail'

# Ensure the database is initialized
if not os.path.exists(os.path.join(os.path.dirname(__file__), "expenses.db")):
    init_db()

@app.route('/')
def index_view():
    return render_template('index.html')

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# --- Authentication APIs ---

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    user_name = data.get('username')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute("SELECT id, name FROM users WHERE id = ?;", (user_id,))
    elif user_name:
        cursor.execute("SELECT id, name FROM users WHERE LOWER(name) = LOWER(?);", (user_name.strip(),))
    else:
        conn.close()
        return jsonify({"error": "Missing user_id or username"}), 400
        
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "User not found"}), 404
        
    session['user_id'] = user['id']
    session['user_name'] = user['name']
    
    return jsonify({
        "message": f"Logged in successfully as {user['name']}",
        "user": {"id": user['id'], "name": user['name']}
    })

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    if 'user_id' not in session:
        # Fallback to auto-login Aisha for convenience if no session
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM users WHERE name = 'Aisha' LIMIT 1;")
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['name']
        else:
            return jsonify({"error": "Unauthorized"}), 401
            
    return jsonify({
        "user": {"id": session['user_id'], "name": session['user_name']}
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    return jsonify({"message": "Logged out successfully"})

# --- User & Group Info APIs ---

@app.route('/api/users', methods=['GET'])
def list_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, joined_date, left_date FROM users;")
    rows = cursor.fetchall()
    conn.close()
    
    users = []
    for r in rows:
        users.append({
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "joined_date": r["joined_date"],
            "left_date": r["left_date"]
        })
    return jsonify(users)

@app.route('/api/groups', methods=['GET'])
def list_groups():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description FROM groups;")
    groups = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(groups)

# --- CSV Import Flow APIs ---

@app.route('/api/import/analyze', methods=['POST'])
def import_analyze():
    """
    Receives CSV file upload, runs the importer analysis, and returns details.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    csv_file = request.files['file']
    if csv_file.filename == '':
        return jsonify({"error": "Empty filename"}), 400
        
    try:
        content_str = csv_file.read().decode('utf-8')
    except Exception as e:
        return jsonify({"error": f"Failed to read file encoding: {e}"}), 400
        
    analysis = importer.analyze_csv(content_str)
    
    # Store raw CSV content or analysis in session briefly (optional)
    session['last_import_filename'] = csv_file.filename
    
    return jsonify({
        "filename": csv_file.filename,
        "rows": analysis
    })

@app.route('/api/import/confirm', methods=['POST'])
def import_confirm():
    """
    Accepts the user-validated CSV row changes and applies them transactionally.
    Outputs the Import Report details.
    """
    data = request.get_json() or {}
    filename = data.get('filename', 'expenses_export.csv')
    rows = data.get('rows', [])
    default_exchange_rate = float(data.get('exchange_rate', 83.50))
    
    if not rows:
        return jsonify({"error": "No rows to import"}), 400
        
    conn = get_db_connection()
    conn.isolation_level = None  # manual transaction control
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN TRANSACTION;")
        
        # 1. Create Import Log
        cursor.execute("INSERT INTO imports (file_name) VALUES (?);", (filename,))
        import_id = cursor.lastrowid
        
        # Fetch user mappings for quick lookup
        cursor.execute("SELECT id, name FROM users;")
        user_map = {row['name']: row['id'] for row in cursor.fetchall()}
        
        stats = {
            "total_records": len(rows),
            "imported_expenses": 0,
            "imported_payments": 0,
            "skipped_duplicates": 0,
            "anomalies_logged": 0
        }
        
        for idx, row in enumerate(rows):
            row_idx = row.get('row_index', idx + 2)
            action = row.get('action', 'import') # 'import' or 'skip' (for duplicates)
            
            anomalies = row.get('anomalies', [])
            
            # Log all anomalies detected in the raw import record
            for anom in anomalies:
                cursor.execute("""
                    INSERT INTO import_anomalies (import_id, row_index, anomaly_type, original_data, detected_issue, action_taken)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    import_id,
                    row_idx,
                    anom.get('type', 'warning'),
                    str(row.get('original_row', '')),
                    anom.get('message', ''),
                    row.get('resolution_summary', 'Applied suggested correction')
                ))
                stats["anomalies_logged"] += 1
                
            if action == 'skip':
                stats["skipped_duplicates"] += 1
                continue
                
            is_settlement = row.get('is_settlement', False)
            parsed = row.get('parsed', {})
            
            # Extract fields
            date = parsed.get('date')
            desc = parsed.get('description')
            paid_by = parsed.get('paid_by')
            amount = float(parsed.get('amount', 0.0))
            currency = parsed.get('currency', 'INR').upper()
            split_type = parsed.get('split_type', 'equal')
            split_with = parsed.get('split_with', [])
            split_details = parsed.get('split_details', {})
            notes = parsed.get('notes', '')
            
            # Retrieve payer user_id
            paid_by_id = user_map.get(paid_by)
            if not paid_by_id:
                # Fallback to create user if not exists or select standard
                cursor.execute("INSERT OR IGNORE INTO users (name, joined_date) VALUES (?, ?);", (paid_by, date))
                cursor.execute("SELECT id FROM users WHERE name = ?;", (paid_by,))
                paid_by_id = cursor.fetchone()['id']
                user_map[paid_by] = paid_by_id
                
            # Exchange Rate resolution
            exchange_rate = 1.0
            if currency == 'USD':
                exchange_rate = float(parsed.get('exchange_rate', default_exchange_rate))
            amount_inr = round(amount * exchange_rate, 2)
            
            if is_settlement:
                # Import as payment/settlement record
                # The CSV payment has single recipient in split_with
                if not split_with:
                    raise ValueError(f"Row {row_idx} Settlement: Split with recipient user is missing")
                recipient_name = split_with[0]
                recipient_id = user_map.get(recipient_name)
                if not recipient_id:
                    cursor.execute("INSERT OR IGNORE INTO users (name, joined_date) VALUES (?, ?);", (recipient_name, date))
                    cursor.execute("SELECT id FROM users WHERE name = ?;", (recipient_name,))
                    recipient_id = cursor.fetchone()['id']
                    user_map[recipient_name] = recipient_id
                    
                cursor.execute("""
                    INSERT INTO payments (group_id, sender_id, receiver_id, amount, currency, exchange_rate, amount_inr, date, notes)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (paid_by_id, recipient_id, amount, currency, exchange_rate, amount_inr, date, desc or notes))
                
                stats["imported_payments"] += 1
            else:
                # Import as regular group expense
                cursor.execute("""
                    INSERT INTO expenses (group_id, description, amount, currency, exchange_rate, amount_inr, paid_by_user_id, split_type, date, notes)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (desc, amount, currency, exchange_rate, amount_inr, paid_by_id, split_type, date, notes))
                
                expense_id = cursor.lastrowid
                
                # Insert Splits
                # 1. equal split division
                if split_type == 'equal':
                    share_amount = round(amount_inr / len(split_with), 2)
                    # Rounding error adjustments: distribute residual paise to first member
                    tot_rounded = share_amount * len(split_with)
                    diff = round(amount_inr - tot_rounded, 2)
                    
                    for i, m in enumerate(split_with):
                        m_id = user_map.get(m)
                        m_share = share_amount
                        if i == 0:
                            m_share = round(share_amount + diff, 2)
                        cursor.execute("""
                            INSERT INTO expense_splits (expense_id, user_id, share_amount)
                            VALUES (?, ?, ?);
                        """, (expense_id, m_id, m_share))
                
                # 2. percentage split division
                elif split_type == 'percentage':
                    for m in split_with:
                        m_id = user_map.get(m)
                        pct = float(split_details.get(m, 0.0))
                        m_share = round(amount_inr * (pct / 100.0), 2)
                        cursor.execute("""
                            INSERT INTO expense_splits (expense_id, user_id, share_ratio, share_amount)
                            VALUES (?, ?, ?, ?);
                        """, (expense_id, m_id, pct, m_share))
                        
                # 3. share split division (ratio)
                elif split_type == 'share':
                    total_ratio_shares = sum(float(split_details.get(m, 0.0)) for m in split_with)
                    for m in split_with:
                        m_id = user_map.get(m)
                        m_shares = float(split_details.get(m, 0.0))
                        m_share = round(amount_inr * (m_shares / total_ratio_shares), 2) if total_ratio_shares > 0 else 0.0
                        cursor.execute("""
                            INSERT INTO expense_splits (expense_id, user_id, share_ratio, share_amount)
                            VALUES (?, ?, ?, ?);
                        """, (expense_id, m_id, m_shares, m_share))
                        
                # 4. unequal split division (direct numbers)
                elif split_type == 'unequal':
                    for m in split_with:
                        m_id = user_map.get(m)
                        custom_amt = float(split_details.get(m, 0.0))
                        cursor.execute("""
                            INSERT INTO expense_splits (expense_id, user_id, share_amount)
                            VALUES (?, ?, ?);
                        """, (expense_id, m_id, custom_amt))
                        
                stats["imported_expenses"] += 1
                
        cursor.execute("COMMIT;")
        conn.close()
        
        return jsonify({
            "message": "CSV data imported successfully",
            "import_id": import_id,
            "stats": stats
        })
        
    except Exception as e:
        conn.execute("ROLLBACK;")
        conn.close()
        return jsonify({"error": f"Database import transaction failed: {str(e)}"}), 500

# --- Dashboard & Balance APIs ---

@app.route('/api/groups/<int:group_id>/balances', methods=['GET'])
def get_balances(group_id):
    try:
        users_balances = balances.get_group_balances(group_id)
        simplified_debts = balances.minimize_debts(users_balances)
        return jsonify({
            "balances": users_balances,
            "simplified_debts": simplified_debts
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<int:user_id>/audit', methods=['GET'])
def get_audit(user_id):
    try:
        audit = balances.get_detailed_audit_trail(user_id, 1)
        return jsonify(audit)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Add Manual Expenses / Payments APIs ---

@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT e.id, e.description, e.amount, e.currency, e.exchange_rate, e.amount_inr, 
               e.paid_by_user_id, u.name as payer_name, e.split_type, e.date, e.notes
        FROM expenses e
        JOIN users u ON e.paid_by_user_id = u.id
        ORDER BY e.date DESC, e.id DESC;
    """)
    expenses = [dict(row) for row in cursor.fetchall()]
    
    # Enrich with split details
    for exp in expenses:
        cursor.execute("""
            SELECT es.user_id, u.name as user_name, es.share_ratio, es.share_amount
            FROM expense_splits es
            JOIN users u ON es.user_id = u.id
            WHERE es.expense_id = ?;
        """, (exp['id'],))
        exp['splits'] = [dict(row) for row in cursor.fetchall()]
        
    conn.close()
    return jsonify(expenses)

@app.route('/api/expenses', methods=['POST'])
def add_expense():
    data = request.get_json() or {}
    description = data.get('description')
    amount = float(data.get('amount', 0.0))
    currency = data.get('currency', 'INR').upper()
    exchange_rate = float(data.get('exchange_rate', 1.0))
    paid_by_user_id = data.get('paid_by_user_id')
    split_type = data.get('split_type', 'equal')
    split_with_ids = data.get('split_with', []) # list of user IDs
    split_details = data.get('split_details', {}) # user_id -> value
    date = data.get('date')
    notes = data.get('notes', '')
    
    if not description or amount <= 0 or not paid_by_user_id or not split_with_ids or not date:
        return jsonify({"error": "Missing required fields"}), 400
        
    amount_inr = round(amount * exchange_rate, 2)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO expenses (group_id, description, amount, currency, exchange_rate, amount_inr, paid_by_user_id, split_type, date, notes)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (description, amount, currency, exchange_rate, amount_inr, paid_by_user_id, split_type, date, notes))
        expense_id = cursor.lastrowid
        
        # Calculate splits
        if split_type == 'equal':
            share_amount = round(amount_inr / len(split_with_ids), 2)
            diff = round(amount_inr - (share_amount * len(split_with_ids)), 2)
            for i, uid in enumerate(split_with_ids):
                m_share = round(share_amount + diff, 2) if i == 0 else share_amount
                cursor.execute("""
                    INSERT INTO expense_splits (expense_id, user_id, share_amount)
                    VALUES (?, ?, ?);
                """, (expense_id, uid, m_share))
        elif split_type == 'percentage':
            for uid in split_with_ids:
                pct = float(split_details.get(str(uid), 0.0))
                m_share = round(amount_inr * (pct / 100.0), 2)
                cursor.execute("""
                    INSERT INTO expense_splits (expense_id, user_id, share_ratio, share_amount)
                    VALUES (?, ?, ?, ?);
                """, (expense_id, uid, pct, m_share))
        elif split_type == 'share':
            total_ratio_shares = sum(float(split_details.get(str(uid), 0.0)) for uid in split_with_ids)
            for uid in split_with_ids:
                m_shares = float(split_details.get(str(uid), 0.0))
                m_share = round(amount_inr * (m_shares / total_ratio_shares), 2) if total_ratio_shares > 0 else 0.0
                cursor.execute("""
                    INSERT INTO expense_splits (expense_id, user_id, share_ratio, share_amount)
                    VALUES (?, ?, ?, ?);
                """, (expense_id, uid, m_shares, m_share))
        elif split_type == 'unequal':
            for uid in split_with_ids:
                custom_amt = float(split_details.get(str(uid), 0.0))
                cursor.execute("""
                    INSERT INTO expense_splits (expense_id, user_id, share_amount)
                    VALUES (?, ?, ?);
                """, (expense_id, uid, custom_amt))
                
        conn.commit()
        conn.close()
        return jsonify({"message": "Expense added successfully", "expense_id": expense_id})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500

@app.route('/api/payments', methods=['GET'])
def get_payments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.sender_id, u1.name as sender_name, p.receiver_id, u2.name as receiver_name,
               p.amount, p.currency, p.exchange_rate, p.amount_inr, p.date, p.notes
        FROM payments p
        JOIN users u1 ON p.sender_id = u1.id
        JOIN users u2 ON p.receiver_id = u2.id
        ORDER BY p.date DESC, p.id DESC;
    """)
    payments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(payments)

@app.route('/api/payments', methods=['POST'])
def add_payment():
    data = request.get_json() or {}
    sender_id = data.get('sender_id')
    receiver_id = data.get('receiver_id')
    amount = float(data.get('amount', 0.0))
    currency = data.get('currency', 'INR').upper()
    exchange_rate = float(data.get('exchange_rate', 1.0))
    date = data.get('date')
    notes = data.get('notes', 'Direct Settlement')
    
    if not sender_id or not receiver_id or amount <= 0 or not date:
        return jsonify({"error": "Missing required fields"}), 400
        
    amount_inr = round(amount * exchange_rate, 2)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO payments (group_id, sender_id, receiver_id, amount, currency, exchange_rate, amount_inr, date, notes)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (sender_id, receiver_id, amount, currency, exchange_rate, amount_inr, date, notes))
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({"message": "Payment recorded successfully", "payment_id": payment_id})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500

# --- Import History & Report APIs ---

@app.route('/api/imports', methods=['GET'])
def list_imports():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_name, imported_at FROM imports ORDER BY id DESC;")
    imports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(imports)

@app.route('/api/imports/<int:import_id>/report', methods=['GET'])
def get_import_report(import_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, file_name, imported_at FROM imports WHERE id = ?;", (import_id,))
    imp_row = cursor.fetchone()
    if not imp_row:
        conn.close()
        return jsonify({"error": "Import not found"}), 404
        
    cursor.execute("""
        SELECT row_index, anomaly_type, original_data, detected_issue, action_taken
        FROM import_anomalies
        WHERE import_id = ?
        ORDER BY row_index ASC, id ASC;
    """, (import_id,))
    anomalies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        "import_id": imp_row["id"],
        "file_name": imp_row["file_name"],
        "imported_at": imp_row["imported_at"],
        "anomalies": anomalies
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

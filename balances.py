from database import get_db_connection

def get_group_balances(group_id=1):
    """
    Calculates the net balance for each user in the group, taking into account
    all expenses, splits, and direct payments (settlements).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all users and their details
    cursor.execute("SELECT id, name, joined_date, left_date FROM users;")
    users = {row['id']: {"name": row['name'], "paid": 0.0, "owed": 0.0, "net": 0.0} for row in cursor.fetchall()}
    
    # 1. Sum up what each user PAID for expenses
    cursor.execute("""
        SELECT paid_by_user_id, SUM(amount_inr) as total_paid
        FROM expenses
        WHERE group_id = ?
        GROUP BY paid_by_user_id;
    """, (group_id,))
    for row in cursor.fetchall():
        uid = row['paid_by_user_id']
        if uid in users:
            users[uid]["paid"] += row['total_paid']
            
    # 2. Sum up what each user OWES from expense splits
    cursor.execute("""
        SELECT es.user_id, SUM(es.share_amount) as total_owed
        FROM expense_splits es
        JOIN expenses e ON es.expense_id = e.id
        WHERE e.group_id = ?
        GROUP BY es.user_id;
    """, (group_id,))
    for row in cursor.fetchall():
        uid = row['user_id']
        if uid in users:
            users[uid]["owed"] += row['total_owed']
            
    # 3. Apply payments/settlements
    # Sender pays Receiver: Sender's net balance increases (they paid out), Receiver's net balance decreases (they received money)
    cursor.execute("""
        SELECT sender_id, receiver_id, SUM(amount_inr) as total_settled
        FROM payments
        WHERE group_id = ?
        GROUP BY sender_id, receiver_id;
    """, (group_id,))
    for row in cursor.fetchall():
        sender = row['sender_id']
        receiver = row['receiver_id']
        amount = row['total_settled']
        if sender in users:
            users[sender]["paid"] += amount # Sender paid out, counts as credit
        if receiver in users:
            users[receiver]["owed"] += amount # Receiver got paid, counts as debit / debt reduction
            
    # Calculate Net Balances
    for uid in users:
        users[uid]["net"] = round(users[uid]["paid"] - users[uid]["owed"], 2)
        users[uid]["paid"] = round(users[uid]["paid"], 2)
        users[uid]["owed"] = round(users[uid]["owed"], 2)
        
    conn.close()
    return users

def get_detailed_audit_trail(user_id, group_id=1):
    """
    Returns every expense and payment that affects a specific user's balance.
    This fulfills Rohan's request ("No magic numbers").
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    audit_trail = []
    
    # Fetch user's name
    cursor.execute("SELECT name FROM users WHERE id = ?;", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        return []
    user_name = user_row['name']
    
    # 1. Fetch all expenses where the user was either the payer OR involved in the split
    cursor.execute("""
        SELECT DISTINCT e.id, e.description, e.amount, e.currency, e.exchange_rate, e.amount_inr, 
                        e.date, e.paid_by_user_id, u.name as payer_name, e.split_type
        FROM expenses e
        JOIN users u ON e.paid_by_user_id = u.id
        LEFT JOIN expense_splits es ON e.id = es.expense_id
        WHERE e.group_id = ? AND (e.paid_by_user_id = ? OR es.user_id = ?)
        ORDER BY e.date ASC, e.id ASC;
    """, (group_id, user_id, user_id))
    
    expenses = cursor.fetchall()
    
    for exp in expenses:
        exp_id = exp['id']
        # Fetch the user's specific split share
        cursor.execute("""
            SELECT share_amount, share_ratio
            FROM expense_splits
            WHERE expense_id = ? AND user_id = ?;
        """, (exp_id, user_id))
        split_row = cursor.fetchone()
        
        user_owed = split_row['share_amount'] if split_row else 0.0
        user_paid = exp['amount_inr'] if exp['paid_by_user_id'] == user_id else 0.0
        net_impact = user_paid - user_owed
        
        # Detail description
        split_desc = ""
        if exp['split_type'] == 'equal':
            split_desc = "Split equally"
        elif exp['split_type'] == 'percentage':
            split_desc = f"Split by percentage ({split_row['share_ratio']}% if active)" if split_row else ""
        elif exp['split_type'] == 'share':
            split_desc = f"Split by shares/ratio ({split_row['share_ratio']} shares)" if split_row else ""
        elif exp['split_type'] == 'unequal':
            split_desc = "Split unequally (custom amount)"
            
        audit_trail.append({
            "type": "expense",
            "id": exp_id,
            "date": exp['date'],
            "description": exp['description'],
            "original_amount": exp['amount'],
            "currency": exp['currency'],
            "exchange_rate": exp['exchange_rate'],
            "amount_inr": exp['amount_inr'],
            "payer_name": exp['payer_name'],
            "user_paid": round(user_paid, 2),
            "user_owed": round(user_owed, 2),
            "net_impact": round(net_impact, 2),
            "split_type": exp['split_type'],
            "split_desc": split_desc
        })
        
    # 2. Fetch all settlements/payments where the user was the sender or receiver
    cursor.execute("""
        SELECT p.id, p.sender_id, u1.name as sender_name, p.receiver_id, u2.name as receiver_name,
               p.amount, p.currency, p.exchange_rate, p.amount_inr, p.date, p.notes
        FROM payments p
        JOIN users u1 ON p.sender_id = u1.id
        JOIN users u2 ON p.receiver_id = u2.id
        WHERE p.group_id = ? AND (p.sender_id = ? OR p.receiver_id = ?)
        ORDER BY p.date ASC, p.id ASC;
    """, (group_id, user_id, user_id))
    
    payments = cursor.fetchall()
    
    for pay in payments:
        if pay['sender_id'] == user_id:
            # User paid out money as settlement -> net impact is positive (reduces their debts)
            user_paid = pay['amount_inr']
            user_owed = 0.0
            net_impact = user_paid
            desc = f"Settled debt to {pay['receiver_name']}"
        else:
            # User received money as settlement -> net impact is negative (reduces what others owe them)
            user_paid = 0.0
            user_owed = pay['amount_inr']
            net_impact = -user_owed
            desc = f"Received payment from {pay['sender_name']}"
            
        audit_trail.append({
            "type": "payment",
            "id": pay['id'],
            "date": pay['date'],
            "description": f"Settlement: {desc}",
            "original_amount": pay['amount'],
            "currency": pay['currency'],
            "exchange_rate": pay['exchange_rate'],
            "amount_inr": pay['amount_inr'],
            "payer_name": pay['sender_name'],
            "user_paid": round(user_paid, 2),
            "user_owed": round(user_owed, 2),
            "net_impact": round(net_impact, 2),
            "notes": pay['notes']
        })
        
    # Sort audit trail chronologically
    audit_trail.sort(key=lambda x: (x['date'], x['type'], x['id']))
    conn.close()
    return audit_trail

def minimize_debts(users_dict):
    """
    Computes simplified debt payments (Who pays whom, how much).
    Aisha's request: "I just want one number per person. Who pays whom, how much, done."
    """
    # Create lists of debtors and creditors
    debtors = [] # (user_id, name, amount_owed_positive)
    creditors = [] # (user_id, name, amount_to_receive_positive)
    
    for uid, udata in users_dict.items():
        net = udata["net"]
        if net < -0.01:
            debtors.append((uid, udata["name"], -net))
        elif net > 0.01:
            creditors.append((uid, udata["name"], net))
            
    # Debt simplification greedy matching
    transactions = []
    
    # Sort descending
    debtors.sort(key=lambda x: x[2], reverse=True)
    creditors.sort(key=lambda x: x[2], reverse=True)
    
    d_idx = 0
    c_idx = 0
    
    # Make copies to manipulate
    d_list = [list(d) for d in debtors]
    c_list = [list(c) for c in creditors]
    
    while d_idx < len(d_list) and c_idx < len(c_list):
        debtor_id, d_name, d_amt = d_list[d_idx]
        creditor_id, c_name, c_amt = c_list[c_idx]
        
        if d_amt < 0.01:
            d_idx += 1
            continue
        if c_amt < 0.01:
            c_idx += 1
            continue
            
        settle_amt = min(d_amt, c_amt)
        transactions.append({
            "from_user_id": debtor_id,
            "from_user_name": d_name,
            "to_user_id": creditor_id,
            "to_user_name": c_name,
            "amount": round(settle_amt, 2)
        })
        
        d_list[d_idx][2] -= settle_amt
        c_list[c_idx][2] -= settle_amt
        
        if d_list[d_idx][2] < 0.01:
            d_idx += 1
        if c_list[c_idx][2] < 0.01:
            c_idx += 1
            
    return transactions

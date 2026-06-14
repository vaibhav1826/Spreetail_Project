import csv
import re
from datetime import datetime

VALID_USERS = ["Aisha", "Rohan", "Priya", "Meera", "Dev", "Sam", "Kabir"]

# Canonical membership windows for validation
MEMBERSHIP_DATES = {
    "Aisha": ("2026-02-01", "9999-12-31"),
    "Rohan": ("2026-02-01", "9999-12-31"),
    "Priya": ("2026-02-01", "9999-12-31"),
    "Meera": ("2026-02-01", "2026-03-31"),
    "Dev": ("2026-02-08", "2026-03-14"),
    "Sam": ("2026-04-10", "9999-12-31"),
    "Kabir": ("2026-03-11", "2026-03-11")
}

def clean_name(name):
    if not name:
        return ""
    name_clean = name.strip()
    if not name_clean:
        return ""
    
    name_lower = name_clean.lower()
    
    # Check exact match first
    for valid in VALID_USERS:
        if valid.lower() == name_lower:
            return valid
            
    # Direct mappings for CSV anomalies
    if name_lower == 'priya' or name_lower == 'priya s':
        return 'Priya'
    if name_lower == 'rohan':
        return 'Rohan'
    if name_lower == 'aisha':
        return 'Aisha'
    if name_lower == 'meera':
        return 'Meera'
    if name_lower == 'dev':
        return 'Dev'
    if name_lower == 'sam':
        return 'Sam'
    if name_lower == 'kabir':
        return 'Kabir'
        
    # Substring matching priority
    if 'kabir' in name_lower:
        return 'Kabir'
    if 'dev' in name_lower:
        return 'Dev'
    if 'priya' in name_lower:
        return 'Priya'
    if 'rohan' in name_lower:
        return 'Rohan'
    if 'aisha' in name_lower:
        return 'Aisha'
    if 'meera' in name_lower:
        return 'Meera'
    if 'sam' in name_lower:
        return 'Sam'
            
    return name_clean # Return trimmed name if no match

def parse_date(date_str):
    """
    Parses various date formats seen in the CSV:
    - YYYY-MM-DD
    - DD/MM/YYYY
    - MMM DD (e.g. 'Mar 14' -> infer year 2026)
    """
    if not date_str:
        return None, "empty_date", True
        
    d_str = date_str.strip()
    
    # Try YYYY-MM-DD
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d"), None, False
    except ValueError:
        pass
        
    # Try DD/MM/YYYY
    try:
        dt = datetime.strptime(d_str, "%d/%m/%Y")
        # Check if ambiguous (e.g. 04/05/2026 could be April 5th or May 4th)
        # We flag any date where both day and month are <= 12 as potentially ambiguous
        is_ambiguous = dt.day <= 12 and dt.month <= 12
        return dt.strftime("%Y-%m-%d"), "ambiguous_date" if is_ambiguous else None, is_ambiguous
    except ValueError:
        pass
        
    # Try MMM DD (e.g., 'Mar 14')
    try:
        # Match 'Mar 14' or 'March 14'
        dt = datetime.strptime(f"{d_str} 2026", "%b %d %Y")
        return dt.strftime("%Y-%m-%d"), "inferred_year", False
    except ValueError:
        pass
        
    try:
        dt = datetime.strptime(f"{d_str} 2026", "%B %d %Y")
        return dt.strftime("%Y-%m-%d"), "inferred_year", False
    except ValueError:
        pass
        
    return None, "invalid_format", False

def parse_amount(amount_str):
    """
    Cleans and parses numeric amounts (e.g., "1,200", " 1450 ")
    """
    if not amount_str:
        return 0.0, None
        
    cleaned = amount_str.strip().replace('"', '').replace(',', '')
    try:
        val = float(cleaned)
        # Check decimal precision
        parts = cleaned.split('.')
        has_precision_issue = len(parts) > 1 and len(parts[1]) > 2
        return val, "precision_issue" if has_precision_issue else None
    except ValueError:
        return 0.0, "invalid_number"

def analyze_csv(file_content_str):
    """
    Parses CSV file contents and outputs raw data plus detected anomalies.
    """
    lines = file_content_str.splitlines()
    reader = csv.reader(lines)
    header = next(reader, None)
    
    parsed_rows = []
    
    # Track rows to detect exact duplicates and conflicts
    # Key: (date, paid_by_clean, amount_val, split_with_sorted_tuple)
    seen_exact_expenses = {}
    # Key: (date, split_with_sorted_tuple) -> list of row indices
    seen_similar_expenses = {}
    
    for idx, row in enumerate(reader):
        row_num = idx + 2 # 1-indexed header is row 1, first data row is row 2
        if not row:
            continue
            
        # Ensure row has enough columns
        while len(row) < 9:
            row.append("")
            
        raw_date, raw_desc, raw_paid_by, raw_amount, raw_currency, raw_split_type, raw_split_with, raw_split_details, raw_notes = [col.strip() for col in row[:9]]
        
        anomalies = []
        
        # 1. Parse Date
        parsed_date, date_warning, is_ambiguous = parse_date(raw_date)
        if not parsed_date:
            anomalies.append({
                "type": "invalid_date",
                "severity": "error",
                "message": f"Could not parse date '{raw_date}'",
                "suggested_fix": {"date": "2026-02-01"}
            })
            parsed_date = "2026-02-01" # fallback
        elif date_warning == "inferred_year":
            anomalies.append({
                "type": "inferred_year",
                "severity": "warning",
                "message": f"Inferred year 2026 for date '{raw_date}'",
                "suggested_fix": {"date": parsed_date}
            })
        elif date_warning == "ambiguous_date":
            anomalies.append({
                "type": "ambiguous_date",
                "severity": "warning",
                "message": f"Ambiguous date format '{raw_date}'. Ingesting as YYYY-MM-DD ({parsed_date})",
                "suggested_fix": {"date": parsed_date} # default to parsed_date, frontend can let them swap day/month
            })
            
        # 2. Parse Amount
        amount_val, amount_warning = parse_amount(raw_amount)
        if amount_warning == "invalid_number":
            anomalies.append({
                "type": "invalid_amount",
                "severity": "error",
                "message": f"Invalid amount format '{raw_amount}'",
                "suggested_fix": {"amount": 0.0}
            })
        elif amount_warning == "precision_issue":
            rounded = round(amount_val, 2)
            anomalies.append({
                "type": "decimal_precision",
                "severity": "warning",
                "message": f"Amount '{raw_amount}' has >2 decimal places. Suggest rounding to {rounded}",
                "suggested_fix": {"amount": rounded}
            })
        elif "," in raw_amount or raw_amount.startswith(" ") or raw_amount.endswith(" "):
            anomalies.append({
                "type": "number_format_whitespace",
                "severity": "warning",
                "message": f"Cleaned formatting/whitespace in amount '{raw_amount}'",
                "suggested_fix": {"amount": amount_val}
            })
            
        # 3. Clean Paid By
        paid_by_clean = clean_name(raw_paid_by)
        if not raw_paid_by:
            # Suggest Aisha or first member in split list
            first_split_member = ""
            if raw_split_with:
                first_split_member = clean_name(raw_split_with.split(";")[0])
            suggested_payer = first_split_member if first_split_member in VALID_USERS else "Aisha"
            anomalies.append({
                "type": "missing_payer",
                "severity": "error",
                "message": "Missing 'paid_by' value",
                "suggested_fix": {"paid_by": suggested_payer}
            })
            paid_by_clean = ""
        elif paid_by_clean not in VALID_USERS:
            anomalies.append({
                "type": "unregistered_payer",
                "severity": "warning",
                "message": f"Payer '{raw_paid_by}' is not in flatmates list. Will create user or map if mapping exists.",
                "suggested_fix": {"paid_by": paid_by_clean}
            })
        elif paid_by_clean != raw_paid_by:
            anomalies.append({
                "type": "payer_name_typo",
                "severity": "warning",
                "message": f"Mapped '{raw_paid_by}' to canonical name '{paid_by_clean}'",
                "suggested_fix": {"paid_by": paid_by_clean}
            })
            
        # 4. Currency
        curr_clean = raw_currency.upper().strip()
        if not raw_currency:
            anomalies.append({
                "type": "currency_missing",
                "severity": "warning",
                "message": "Currency field is blank. Assuming base currency INR",
                "suggested_fix": {"currency": "INR"}
            })
            curr_clean = "INR"
        elif curr_clean == "USD":
            anomalies.append({
                "type": "usd_currency",
                "severity": "warning",
                "message": f"USD expense of {amount_val} USD requires conversion",
                "suggested_fix": {"currency": "USD", "exchange_rate": 83.50}
            })
            
        # 5. Split Type & Split With
        split_with_clean = []
        if raw_split_with:
            split_members = [m.strip() for m in raw_split_with.split(";")]
            for m in split_members:
                mc = clean_name(m)
                if mc:
                    split_with_clean.append(mc)
                    if mc not in VALID_USERS:
                        anomalies.append({
                            "type": "unregistered_split_user",
                            "severity": "warning",
                            "message": f"Unregistered split member '{m}'",
                            "suggested_fix": {"split_member": mc}
                        })
                    if mc != m:
                        anomalies.append({
                            "type": "split_member_typo",
                            "severity": "warning",
                            "message": f"Mapped split member '{m}' to '{mc}'",
                            "suggested_fix": {"split_member": mc}
                        })
        else:
            anomalies.append({
                "type": "missing_split_with",
                "severity": "error",
                "message": "Empty 'split_with' list. Defaulting split to all active members.",
                "suggested_fix": {"split_with": "Aisha;Rohan;Priya;Meera"}
            })
            
        # 6. Membership checks for active date boundaries
        for u in split_with_clean:
            if u in MEMBERSHIP_DATES:
                join_date_str, leave_date_str = MEMBERSHIP_DATES[u]
                if parsed_date < join_date_str:
                    anomalies.append({
                        "type": "inactive_member_split",
                        "severity": "warning",
                        "message": f"Member '{u}' was not active on {parsed_date} (joined on {join_date_str})",
                        "suggested_fix": {"remove_member": u}
                    })
                elif leave_date_str and parsed_date > leave_date_str:
                    anomalies.append({
                        "type": "inactive_member_split",
                        "severity": "warning",
                        "message": f"Member '{u}' had already left on {parsed_date} (left on {leave_date_str})",
                        "suggested_fix": {"remove_member": u}
                    })
                    
        # 7. Split Details Parsing & Validation
        split_type_clean = raw_split_type.lower().strip()
        details_parsed = {}
        if split_type_clean == 'percentage':
            # Parse percentage e.g. "Aisha 30%; Rohan 30%; Priya 30%; Meera 20%"
            parts = [p.strip() for p in raw_split_details.split(";") if p.strip()]
            pct_sum = 0
            for part in parts:
                match = re.match(r"^(.+?)\s+([0-9\.]+)\s*%$", part)
                if match:
                    u_name = clean_name(match.group(1))
                    u_val = float(match.group(2))
                    details_parsed[u_name] = u_val
                    pct_sum += u_val
                else:
                    anomalies.append({
                        "type": "invalid_split_details_format",
                        "severity": "error",
                        "message": f"Could not parse percentage split detail '{part}'",
                        "suggested_fix": {}
                    })
            if pct_sum != 100.0:
                # Suggest normalized percentages
                normalized = {}
                if pct_sum > 0:
                    normalized = {u: round((v / pct_sum) * 100, 2) for u, v in details_parsed.items()}
                anomalies.append({
                    "type": "percentage_sum_mismatch",
                    "severity": "warning",
                    "message": f"Percentage splits sum to {pct_sum}%, not 100%",
                    "suggested_fix": {"normalized_percentages": normalized}
                })
        elif split_type_clean == 'unequal':
            # Parse unequal e.g. "Rohan 700; Priya 400; Meera 400"
            parts = [p.strip() for p in raw_split_details.split(";") if p.strip()]
            sum_unequal = 0
            for part in parts:
                match = re.match(r"^(.+?)\s+([0-9\.]+)$", part)
                if match:
                    u_name = clean_name(match.group(1))
                    u_val = float(match.group(2))
                    details_parsed[u_name] = u_val
                    sum_unequal += u_val
                else:
                    anomalies.append({
                        "type": "invalid_split_details_format",
                        "severity": "error",
                        "message": f"Could not parse unequal split detail '{part}'",
                        "suggested_fix": {}
                    })
            if abs(sum_unequal - amount_val) > 0.01:
                anomalies.append({
                    "type": "unequal_sum_mismatch",
                    "severity": "warning",
                    "message": f"Unequal split details sum to {sum_unequal}, but expense amount is {amount_val}",
                    "suggested_fix": {}
                })
        elif split_type_clean == 'share':
            # Parse ratio/shares e.g. "Aisha 1; Rohan 2; Priya 1; Dev 2"
            parts = [p.strip() for p in raw_split_details.split(";") if p.strip()]
            for part in parts:
                match = re.match(r"^(.+?)\s+([0-9\.]+)$", part)
                if match:
                    u_name = clean_name(match.group(1))
                    u_val = float(match.group(2))
                    details_parsed[u_name] = u_val
                else:
                    anomalies.append({
                        "type": "invalid_split_details_format",
                        "severity": "error",
                        "message": f"Could not parse share split detail '{part}'",
                        "suggested_fix": {}
                    })
        elif split_type_clean == 'equal' and raw_split_details:
            # Redundant details warning
            anomalies.append({
                "type": "redundant_split_details",
                "severity": "warning",
                "message": "Split details provided for equal split type. Details will be ignored in favor of equal division.",
                "suggested_fix": {"clear_details": True}
            })
            
        # 8. Settlements logged as expenses
        is_settlement = False
        desc_lower = raw_desc.lower()
        if not raw_split_type and (len(split_with_clean) == 1 or "paid" in desc_lower or "deposit" in desc_lower or "back" in desc_lower):
            is_settlement = True
            anomalies.append({
                "type": "settlement_logged_as_expense",
                "severity": "warning",
                "message": f"Description '{raw_desc}' and empty split type suggest this is a settlement/payment, not an expense",
                "suggested_fix": {"convert_to_payment": True}
            })
        elif "deposit" in desc_lower and len(split_with_clean) == 1:
            is_settlement = True
            anomalies.append({
                "type": "settlement_logged_as_expense",
                "severity": "warning",
                "message": f"Description '{raw_desc}' suggests this is a security deposit transfer, not a group expense",
                "suggested_fix": {"convert_to_payment": True}
            })
            
        # 9. Duplicates and conflict detection
        split_with_sorted_tuple = tuple(sorted(split_with_clean))
        exact_key = (parsed_date, paid_by_clean, amount_val, curr_clean, split_with_sorted_tuple)
        similar_key = (parsed_date, split_with_sorted_tuple)
        
        # Check exact duplicate
        action_default = "import"
        if exact_key in seen_exact_expenses:
            action_default = "skip"
            first_idx = seen_exact_expenses[exact_key]
            anomalies.append({
                "type": "exact_duplicate",
                "severity": "warning",
                "message": f"Exact duplicate of row {first_idx}",
                "suggested_fix": {"action": "delete", "duplicate_of": first_idx}
            })
        else:
            seen_exact_expenses[exact_key] = row_num
            
        # Check conflict duplicate (e.g. Thalassa dinner logged by Aisha and Rohan with diff amounts)
        # We define similar key as same date and same split-with participants
        if similar_key in seen_similar_expenses:
            for matching_row_num in seen_similar_expenses[similar_key]:
                # Avoid triggering duplicate warning if it's already an exact duplicate
                if exact_key not in seen_exact_expenses or seen_exact_expenses[exact_key] == row_num:
                    anomalies.append({
                        "type": "conflict_duplicate",
                        "severity": "warning",
                        "message": f"Conflict duplicate. Row {matching_row_num} is also logged on {parsed_date} for same group.",
                        "suggested_fix": {"action": "resolve_conflict", "conflict_with": matching_row_num}
                    })
            seen_similar_expenses[similar_key].append(row_num)
        else:
            seen_similar_expenses[similar_key] = [row_num]
            
        parsed_rows.append({
            "row_index": row_num,
            "original_row": row,
            "is_settlement": is_settlement,
            "action": action_default,
            "parsed": {
                "date": parsed_date,
                "description": raw_desc,
                "paid_by": paid_by_clean,
                "amount": amount_val,
                "currency": curr_clean,
                "split_type": split_type_clean if raw_split_type else "equal",
                "split_with": split_with_clean,
                "split_details": details_parsed,
                "notes": raw_notes
            },
            "anomalies": anomalies
        })
        
    return parsed_rows

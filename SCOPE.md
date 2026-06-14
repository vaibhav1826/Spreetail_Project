# SCOPE.md — Anomaly Log & Database Schema

This document details every data quality issue identified in `expenses_export.csv`, our resolution policies, and the relational database schema of the app.

---

## 1. Relational Database Schema

We use **SQLite** as our relational database. Below is the database schema design:

```mermaid
erDiagram
    users {
        int id PK
        string name UNIQUE
        string email
        string password_hash
        date joined_date
        date left_date
    }
    groups {
        int id PK
        string name
        string description
    }
    group_memberships {
        int group_id FK
        int user_id FK
        date joined_at
        date left_at
    }
    expenses {
        int id PK
        int group_id FK
        string description
        real amount
        string currency
        real exchange_rate
        real amount_inr
        int paid_by_user_id FK
        string split_type
        date date
        string notes
        timestamp created_at
    }
    expense_splits {
        int id PK
        int expense_id FK
        int user_id FK
        real share_ratio
        real share_amount
    }
    payments {
        int id PK
        int group_id FK
        int sender_id FK
        int receiver_id FK
        real amount
        string currency
        real exchange_rate
        real amount_inr
        date date
        string notes
        timestamp created_at
    }
    imports {
        int id PK
        string file_name
        timestamp imported_at
    }
    import_anomalies {
        int id PK
        int import_id FK
        int row_index
        string anomaly_type
        string original_data
        string detected_issue
        string action_taken
    }

    users ||--o{ group_memberships : has
    groups ||--o{ group_memberships : contains
    groups ||--o{ expenses : records
    users ||--o{ expenses : pays
    expenses ||--o{ expense_splits : has
    users ||--o{ expense_splits : owes
    groups ||--o{ payments : tracks
    users ||--o{ payments : sends
    users ||--o{ payments : receives
    imports ||--o{ import_anomalies : logs
```

### Table Definitions
1. **`users`**: Stores user profiles. Note the `joined_date` and `left_date` which determine their membership activity period.
2. **`groups`**: Supports multiple flat/trip groups (our app operates on `group_id = 1` default).
3. **`group_memberships`**: Connects users to groups, restricting transaction splits to their active duration (`joined_at` to `left_at`).
4. **`expenses`**: Holds the main expense header records. Amount in original currency and final converted `amount_inr` are stored.
5. **`expense_splits`**: Stores individual debt allocations. `share_ratio` stores percentage value or share weight. `share_amount` is the final value in base currency (INR).
6. **`payments`**: Records cash transfers (settlements), which reduce mutual debts.
7. **`imports`**: Logs CSV upload history.
8. **`import_anomalies`**: Logs each anomaly found during an import, detailing the row index, category, raw data, and resolution action applied.

---

## 2. Anomaly Log (CSV Data Problems)

We identified **14 distinct categories of anomalies** across the 42 rows of the spreadsheet export:

| Anomaly Type | Occurrences / Rows | Example Row | Description | Resolution Policy |
| :--- | :--- | :--- | :--- | :--- |
| **Exact Duplicate** | Row 6 | `2026-02-08,dinner - marina bites,Dev,3200,INR...` | Row 6 matches Row 5 exactly on Date, Payer, Amount, and Split. | Auto-suggest delete/skip Row 6. User can toggle action in the UI. |
| **Conflict Duplicate** | Rows 24 & 25 | `Thalassa dinner` (Rohan ₹2450) vs `Dinner at Thalassa` (Aisha ₹2400) | Two people logged the same group dinner on March 11. | Flagged as conflict duplicate. In the Import Wizard, user selects which row wins (e.g. keep Rohan's, delete Aisha's, or keep both). |
| **Payer Name Typo** | Rows 9, 11, 27 | `priya`, `Priya S`, `rohan ` | Typo, casing error, or trailing spaces in the payer name. | Normalizes to canonical names (`Priya`, `Rohan`). Flagged for user approval. |
| **Missing Payer** | Row 13 | `2026-02-22,House cleaning supplies,,780...` | The payer field is blank. Note says "can't remember who paid". | Flags error. User must select the payer from a dropdown in the UI. |
| **Number Whitespace / Comma** | Row 7, 29 | `"1,200"`, ` 1450 ` | Amounts formatted with commas as thousand separators, or wrapped in spaces. | Parses string, removes formatting characters and whitespace, casting to float. |
| **Decimal Precision** | Row 10 | `Cylinder refill,Rohan,899.995` | Amount has 3 decimal places. | Suggests rounding to 2 decimal places (`900.00`) and logs correction. |
| **Blank Split Type (Settlement)** | Row 14, 38 | `Rohan paid Aisha back`, `Sam deposit share` | Settlement transactions logged as standard expenses. | Auto-suggests converting the record to a direct `Payment` (Settlement) rather than a group expense. |
| **Percentage split sum != 100%** | Rows 15, 32 | `Pizza Friday` (110% total) | Percentage share details sum to 110% instead of 100%. | Normalizes values proportionally to sum to 100% (e.g. `val / 1.1`) and logs action. |
| **Date Format Inconsistencies** | Rows 16-26 | `01/03/2026` vs `2026-02-01` | Mixed ISO `YYYY-MM-DD` and European `DD/MM/YYYY` formats. | Attempts multiple date string formats to standardise. |
| **Inferred Year / Missing Year** | Row 27 | `Mar 14` | Date has no year. | Infers year `2026` based on surrounding chronological context. |
| **Ambiguous Date Format** | Row 34 | `04/05/2026` | Could be April 5th or May 4th. Note says "format is a mess". | Flags warning. Suggests standard parsing and allows user to swap DD/MM if needed. |
| **Missing Currency** | Row 28 | `Groceries DMart` (currency column blank) | Notes say "forgot to set currency". | Defaults currency to base `INR` and flags warning. |
| **Multi-Currency USD** | Rows 20, 21, 23, 26 | `540 USD` (Goa trip) | Part of the trip logged in USD. Priya notes "sheet pretends a dollar is a rupee". | Ingests as USD, prompts user to configure the USD->INR exchange rate (default 83.50), and calculates split shares in INR. |
| **Inactive Member Split** | Row 36 | `Groceries BigBasket` on April 2 splitting with Meera. | Meera moved out on March 31, but was included in an April split. | Flags warning. Redistributes Meera's share to active members, or logs Meera's liability if user approves. |

---

## 3. Verifying the 12+ Deliberate Data Problems

The application guarantees that no messy data enters the relational database silently. By showing the interactive review screen, **Aisha, Rohan, Priya, Sam, and Meera** get exactly what they need:

1. **Aisha** gets an clean ledger with duplicates resolved, ensuring she has single-value balances with simplified settlements.
2. **Rohan** can audit all parsed transactions in his list because the import wizard logs the original row values and the exact action taken.
3. **Priya's** USD transactions are converted using the designated exchange rate, keeping the base currency intact.
4. **Sam** is not assigned shares for March expenses because of active date boundaries (`inactive_member_split` warnings).
5. **Meera** reviews every single deletion (e.g. duplicate rows) and mapping before she clicks "Confirm Import".

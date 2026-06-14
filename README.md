# FairShare — Shared Expenses App

FairShare is a premium, glassmorphic single-page web application designed for flatmates to track shared expenses, resolve messy CSV spreadsheet imports, and settle debts.

Built as a candidate submission for the Spreetail Software Engineering Internship project.

---

## 1. Features

1. **Dashboard View**: Real-time net balances for each flatmate with highlight support for the logged-in user.
2. **Simplified Settlement**: Aisha's request: a debt-minimization algorithm that computes the absolute minimum number of payments required to settle all debts.
3. **Detailed Transaction Audit**: Rohan's request: a step-by-step breakdown of every single transaction that contributes to a user's balance.
4. **USD Conversion**: Priya's request: USD transactions are converted to INR using user-configurable exchange rates.
5. **Membership active boundaries**: Sam's request: memberships have date ranges (e.g. Sam joined April 10, Meera left March 31). Sam is not charged for March bills, and Meera is flagged if included in April splits.
6. **Interactive CSV Import Wizard**: Meera's request: the app analyzes `expenses_export.csv` and highlights 24+ anomalies. The user reviews and corrects duplicates, typos, ambiguous dates, and percentages before database ingestion.

---

## 2. Tech Stack

- **Backend**: Python Flask 3.1.3 (WSGI Server)
- **Database**: SQLite 3 (relational database file: `expenses.db`)
- **Frontend**: Single-Page App (SPA) built with Vanilla HTML5, CSS3 (Glassmorphism design system), and JavaScript.
- **AI Collaborator**: Gemini 3.5 Flash

---

## 3. Setup and Run Instructions

### Prerequisites
- Python 3.10+
- Flask is required. It is pre-installed on this workspace. If running in a clean environment, install via:
  ```bash
  pip install Flask
  ```

### Step 1: Initialize and Seed the Database
From the project root directory, execute the database seeding script. This will create the relational tables in `expenses.db` and populate the default users (Aisha, Rohan, Priya, Meera, Sam, Dev, Kabir) with their active membership dates.
```bash
python database.py
```

### Step 2: Start the Web Server
Launch the Flask development server:
```bash
python app.py
```
By default, the application will start on: **`http://127.0.0.1:5000`**

Open this link in your web browser to access the app.

---

## 4. How to Use the Import Wizard

1. Go to the **CSV Import Wizard** tab in the app.
2. Drag and drop `expenses_export.csv` (located in your scratch or project folder) or click to choose the file.
3. The app will run `analyze` and render the **Interactive CSV Resolution Wizard** listing all rows.
4. Expand any cards with **warnings (orange)** or **errors (red)**:
   - For Row 6 (duplicate rent) or Row 25 (Thalassa dinner conflict), select "Delete/Skip Row" or edit the parameters.
   - For Row 13 (missing payer), choose who paid from the dropdown.
   - Review dates, currencies, and percentages.
5. Click **"Approve & Ingest Data"** at the top.
6. Review the generated **Log & Verification Report** confirming the exact number of expenses imported and the anomaly resolutions logged, then click "Done" to see updated balances.

---

## 5. Running Automated Tests

A unit test suite verifying date parsing, numerical formats, split allocations, and the debt-minimization algorithm is provided.
To execute the tests:
```bash
python -m unittest test_app.py
```
All tests should pass successfully.

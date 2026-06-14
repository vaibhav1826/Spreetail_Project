# DECISIONS.md — Decision Log

This document records the architectural and product decisions made during the development of the Shared Expenses App, outlining the options considered and the rationale behind each choice.

---

## 1. Core Tech Stack
* **Decision**: Python Flask backend + SQLite relational database + Vanilla HTML/CSS/JavaScript frontend SPA.
* **Options Considered**:
  1. *Next.js (React) + PostgreSQL*: Modern, but has substantial setup/dependency installation size and requires a separate running PostgreSQL database server. Too heavy for a simple local workspace submission.
  2. *Vite (React) + Node Express + SQLite*: Good, but Express requires setting up CORS, and npm packages can break during deployment or build processes.
  3. *Python Flask + SQLite + Vanilla JS*: Selected. Flask has zero build compilation overhead, starts instantly, has direct access to Python's robust CSV and regex packages, and includes a built-in relational connector (`sqlite3`). Vanilla JS allows us to build a responsive SPA with premium CSS without build step dependencies.

---

## 2. CSV Anomaly Handling Strategy
* **Decision**: Built-in **Interactive CSV Import Wizard** rather than silent background cleanup or throwing script exceptions.
* **Options Considered**:
  1. *Silent Guessing*: Clean up names and round numbers automatically. Bad, because it violates Meera's request ("approve anything deleted or changed") and risks incorrect date parsings (ambiguity).
  2. *Crashed Import / Strict Rejection*: Crash the import if any format is off. Bad, because the file has 24+ deliberate anomalies, and the user would never be able to load the data.
  3. *Interactive Resolution Wizard*: Selected. The importer runs analysis, returns a detailed list of flagged issues, and lets the user preview, override, or approve corrections directly in the UI.

---

## 3. Database Schema for Dynamic Membership
* **Decision**: Separated `users`, `groups`, and `group_memberships`. Memberships track `joined_at` and `left_at` date ranges.
* **Options Considered**:
  1. *Static Group List*: A simple text column in `groups` listing members (e.g. "Aisha, Rohan, Priya, Meera"). Bad, because it fails to capture membership changes over time, splitting April rent with Meera even though she left in March.
  2. *Date-bounded Memberships*: Selected. Each user has active date ranges in the group. Expenses are checked against the expense date. Users are only split with if they were active members on that date, solving Sam's request.

---

## 4. Multi-Currency Split Strategy
* **Decision**: All transactions are converted to base currency (`INR`) at the point of ingestion (using historical USD exchange rate or custom user rate) and recorded as `amount_inr` inside the relational database.
* **Options Considered**:
  1. *Multi-currency balances*: Maintain separate USD and INR balances. Bad, because flatmates would have to pay each other in multiple currencies, complicating the final settlements (Aisha's request).
  2. *Single Base Currency Conversion*: Selected. Convert foreign items to INR using a configured rate. Keeps balances unified and clean, solving Priya's issue.

---

## 5. Rounding and Precision Rules
* **Decision**: Rounded all final share amounts to 2 decimal places (`REAL` in SQLite). Residual fractions of a rupee (paise) are applied to the first split participant in each expense to ensure the sum of splits equals the exact transaction total.
* **Options Considered**:
  1. *Float values without rounding*: Leave infinite decimals (e.g., `899.995 / 4 = 224.99875`). Bad, because database tallies will drift due to floating-point representation limits.
  2. *Banker's Rounding + Residual Distribution*: Selected. Guarantees that the sum of splits matches `amount_inr` exactly.

---

## 6. Debt Simplification Algorithm
* **Decision**: Greedy matching of sorted net outstanding balances (creditors vs debtors).
* **Options Considered**:
  1. *Raw Payer-to-Ower matching*: Create a transaction for every split. Bad, because flatmates would have to make dozens of tiny transactions (Aisha's request).
  2. *Greedy Net Settlement*: Selected. Sort net debtors (most negative first) and net creditors (most positive first), matching them iteratively. Reduces the number of payments to at most $N-1$ transactions.

# AI_USAGE.md — AI Tool Usage Log

This document lists the AI tools used, key prompts, and concrete cases where AI-generated output had issues that were caught and corrected.

---

## 1. AI Tools and Prompts
* **AI Tool Used**: Gemini 3.5 Flash (Medium)
* **Key Prompts**:
  * "Write a Python script using urllib to download file streams directly from Google Drive share links."
  * "Create a database schema in SQLite to track expense splits, user membership windows (joined/left dates), and CSV import anomalies."
  * "Write a simplified debt settlement algorithm in Python that matches debtors with creditors to minimize transactions."
  * "Design a responsive glassmorphic HTML/CSS template using HSL colors and Outfit/Inter fonts for a web dashboard."

---

## 2. Concrete Cases of AI Corrections

### Case 1: Name Mapping Prioritization Bug
* **AI Output**: A substring loop checking:
  ```python
  for valid in VALID_USERS:
      if valid.lower() in name_lower:
          return valid
  ```
* **Issue**: Because the loop checked `"Dev"` before `"Kabir"`, the name `"Dev's friend Kabir"` matched `"dev"` first and was incorrectly mapped to `"Dev"`.
* **How Caught**: Executed the test parser script `test_parser.py` on `expenses_export.csv` and saw row 23 outputting `"Mapped split member Dev's friend Kabir to Dev"`.
* **Correction**: Refactored `clean_name` in `importer.py` to prioritize exact equality matches first, followed by substring checking for `'kabir'` before checking for `'dev'`.

### Case 2: Silent Date Ingestion (Ambiguity Resolution)
* **AI Output**: The code parsed `04/05/2026` strictly as May 4th (`%d/%m/%Y`) without warnings.
* **Issue**: This was a silent guess. The date `04/05/2026` is ambiguous (could be April 5th or May 4th), and the row notes state "is this April 5 or May 4? format is a mess". A silent guess is a failing answer.
* **How Caught**: Cross-referenced the parsed date with the row notes in `expenses.csv`.
* **Correction**: Added an ambiguity check in `parse_date`: if both day and month are `<= 12` in a `DD/MM/YYYY` format, we flag it with an `ambiguous_date` warning. The UI then highlights this row and lets the user choose which month/day mapping is correct.

### Case 3: Floating-Point Paise Drift in Split Database Inserts
* **AI Output**: Splitting an expense was modeled as a simple float division (e.g. `amount_inr / len(split_with)`).
* **Issue**: For some splits (e.g. splitting ₹1,199.00 among 4 users), the rounded shares (₹299.75 * 4 = ₹1,199.00) work out, but for prime fractions or custom percentage calculations (e.g. Pizza Friday 1440 INR), float summation could result in small residual values (e.g. sum of splits = 1439.99 or 1440.01).
* **How Caught**: Verified splits logic mathematically by checking whether sum of splits equals `amount_inr` exactly.
* **Correction**: Added a residual adjustment routine in `app.py` confirm API. The code rounds all splits to 2 decimal places, calculates the difference `diff = amount_inr - sum(splits)`, and adds this difference (usually +/- 1 or 2 paise) to the first split participant.

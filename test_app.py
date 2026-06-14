import unittest
import sys
import os

sys.path.append(os.path.dirname(__file__))
import importer
import balances

class TestFairShareApp(unittest.TestCase):

    def test_clean_name(self):
        # Exact names
        self.assertEqual(importer.clean_name("Aisha"), "Aisha")
        self.assertEqual(importer.clean_name("Rohan"), "Rohan")
        
        # Typos and casing
        self.assertEqual(importer.clean_name("priya"), "Priya")
        self.assertEqual(importer.clean_name("Priya S"), "Priya")
        self.assertEqual(importer.clean_name("rohan "), "Rohan")
        
        # Compound names (Kabir)
        self.assertEqual(importer.clean_name("Dev's friend Kabir"), "Kabir")
        
        # Untrimmed spaces
        self.assertEqual(importer.clean_name("  Sam  "), "Sam")

    def test_parse_date(self):
        # ISO format
        date_str, warning, is_ambig = importer.parse_date("2026-02-05")
        self.assertEqual(date_str, "2026-02-05")
        self.assertNilOrFalse(is_ambig)
        
        # Inferred year
        date_str, warning, is_ambig = importer.parse_date("Mar 14")
        self.assertEqual(date_str, "2026-03-14")
        self.assertEqual(warning, "inferred_year")
        
        # European format (not ambiguous)
        date_str, warning, is_ambig = importer.parse_date("28/03/2026")
        self.assertEqual(date_str, "2026-03-28")
        self.assertNilOrFalse(is_ambig)
        
        # Ambiguous format (day and month <= 12)
        date_str, warning, is_ambig = importer.parse_date("04/05/2026")
        self.assertEqual(date_str, "2026-05-04")
        self.assertEqual(warning, "ambiguous_date")
        self.assertTrue(is_ambig)

    def test_parse_amount(self):
        # Valid numbers
        val, warning = importer.parse_amount("1500")
        self.assertEqual(val, 1500.0)
        self.assertIsNone(warning)
        
        # Whitespace and commas
        val, warning = importer.parse_amount(" 1,200 ")
        self.assertEqual(val, 1200.0)
        self.assertIsNone(warning) # or number_format warning caught separately
        
        # Decimal precision
        val, warning = importer.parse_amount("899.995")
        self.assertEqual(val, 899.995)
        self.assertEqual(warning, "precision_issue")

    def test_debt_minimization(self):
        # Sample balances:
        # User 1: net = -100 (Debtor)
        # User 2: net = -50  (Debtor)
        # User 3: net = +150 (Creditor)
        balances_dict = {
            1: {"name": "Alice", "net": -100.0},
            2: {"name": "Bob", "net": -50.0},
            3: {"name": "Charlie", "net": 150.0}
        }
        
        transactions = balances.minimize_debts(balances_dict)
        
        self.assertEqual(len(transactions), 2)
        
        # Largest debtor (Alice) pays largest creditor (Charlie)
        self.assertEqual(transactions[0]["from_user_name"], "Alice")
        self.assertEqual(transactions[0]["to_user_name"], "Charlie")
        self.assertEqual(transactions[0]["amount"], 100.0)
        
        # Bob pays Charlie the remaining
        self.assertEqual(transactions[1]["from_user_name"], "Bob")
        self.assertEqual(transactions[1]["to_user_name"], "Charlie")
        self.assertEqual(transactions[1]["amount"], 50.0)

    def assertNilOrFalse(self, val):
        self.assertTrue(val is None or val is False)

if __name__ == '__main__':
    unittest.main()

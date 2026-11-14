import os
import unittest
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from calc_overlay import (
    PHP_TO_USDT,
    eval_math,
    convert_single_token,
    process_query,
    extract_numbers_from_clipboard,
)


class TestCalcConverter(unittest.TestCase):
    def test_eval_math_basic(self):
        self.assertEqual(eval_math("10+5"), 15.0)
        self.assertEqual(eval_math("50*2"), 100.0)
        self.assertEqual(eval_math("100/4"), 25.0)
        self.assertEqual(eval_math("(10+2)*3"), 36.0)

    def test_eval_math_invalid(self):
        self.assertIsNone(eval_math("invalid_code()"))
        self.assertIsNone(eval_math("__import__('os')"))
        self.assertIsNone(eval_math(""))

    def test_convert_php_to_usdt(self):
        res = convert_single_token("100")
        self.assertIsNotNone(res)
        expected_usdt = 100 * PHP_TO_USDT
        self.assertAlmostEqual(res["usdt_num"], expected_usdt, places=4)
        self.assertEqual(res["input"], "100.00 PHP")

    def test_convert_php_with_suffix(self):
        res = convert_single_token("250php")
        self.assertIsNotNone(res)
        expected_usdt = 250 * PHP_TO_USDT
        self.assertAlmostEqual(res["usdt_num"], expected_usdt, places=4)

    def test_convert_usdt_to_php(self):
        res = convert_single_token("10usdt")
        self.assertIsNotNone(res)
        expected_php = 10.0 / PHP_TO_USDT
        self.assertAlmostEqual(res["php_num"], expected_php, places=2)
        self.assertEqual(res["input"], "10 USDT")

    def test_convert_usd_dollar_sign(self):
        res_prefix = convert_single_token("$15")
        self.assertIsNotNone(res_prefix)
        expected_php = 15.0 / PHP_TO_USDT
        self.assertAlmostEqual(res_prefix["php_num"], expected_php, places=2)

        res_suffix = convert_single_token("25$")
        self.assertIsNotNone(res_suffix)
        expected_php_25 = 25.0 / PHP_TO_USDT
        self.assertAlmostEqual(res_suffix["php_num"], expected_php_25, places=2)

    def test_math_expression_conversion(self):
        res = convert_single_token("50*2")
        self.assertIsNotNone(res)
        expected_usdt = 100.0 * PHP_TO_USDT
        self.assertAlmostEqual(res["usdt_num"], expected_usdt, places=4)

    def test_process_query_multiple_tokens(self):
        results = process_query("100, 200, 10usdt")
        self.assertEqual(len(results), 3)
        self.assertAlmostEqual(results[0]["php_num"], 100.0)
        self.assertAlmostEqual(results[1]["php_num"], 200.0)
        self.assertAlmostEqual(results[2]["usdt_num"], 10.0)

    def test_extract_numbers_from_clipboard(self):
        # Plain number
        self.assertEqual(extract_numbers_from_clipboard("500"), "500")

        # Mixed text with currency
        self.assertEqual(extract_numbers_from_clipboard("Total cost is 1500 PHP for order"), "1500")

        # Multiple amounts
        extracted = extract_numbers_from_clipboard("Item 1: 100, Item 2: 250")
        self.assertIn("100", extracted)
        self.assertIn("250", extracted)

        # Empty or non-numeric
        self.assertEqual(extract_numbers_from_clipboard(""), "")
        self.assertEqual(extract_numbers_from_clipboard("no numbers here"), "")

    def test_get_process_ram_mb(self):
        from calc_overlay import FloatingCalcOverlay
        ram = FloatingCalcOverlay._get_process_ram_mb(None)
        if ram is not None:
            self.assertGreater(ram, 0.0)
            self.assertLess(ram, 1000.0)  # Should reasonably be well under 1GB


if __name__ == "__main__":
    unittest.main()

"""Tests for the invented-name A/B that make no API calls.

    python -m unittest evals.hallucination.test_run_ab
    python evals/hallucination/test_run_ab.py

They pin the metric (invented() flags a bogus name and passes a real snippet), assert every
question's category is a real catalogue group, and assert every documented trap is genuinely
absent from the catalogue -- so a name Polars later ships stops being a trap loudly.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_ab  # noqa: E402


class Metric(unittest.TestCase):
    def test_valid_snippet_has_no_inventions(self):
        text = ("```python\n"
                "df.group_by(\"region\").agg(pl.col(\"sales\").sum())\n"
                "```")
        self.assertEqual(run_ab.invented(text), [])

    def test_bogus_names_are_flagged(self):
        text = ("```python\n"
                "df.groupby(\"region\").agg(pl.col(\"sales\").made_up_method())\n"
                "```")
        bad = run_ab.invented(text)
        self.assertTrue(any("groupby" in e for e in bad), bad)
        self.assertTrue(any("made_up_method" in e for e in bad), bad)

    def test_bogus_pl_function_in_code_flagged(self):
        self.assertTrue(run_ab.invented("```python\npl.load_csv(\"f.csv\")\n```"))

    def test_prose_mention_not_counted(self):
        # Naming a dead/wrong API in prose to contrast it is not a hallucination.
        self.assertEqual(run_ab.invented("Avoid `pl.load_csv`; use `pl.read_csv`."), [])

    def test_builder_methods_allowlisted(self):
        # pl.when().then().otherwise() is valid; the checker misses When/Then, so these are
        # allowlisted and must not count.
        text = ("```python\n"
                "df.with_columns(pl.when(pl.col(\"p\") > 100).then(pl.lit(\"hi\"))"
                ".otherwise(pl.lit(\"lo\")))\n```")
        self.assertEqual(run_ab.invented(text), [])

    def test_allowlist_is_exact_not_substring(self):
        # A real invention whose name starts with an allowlisted word must still be flagged.
        self.assertTrue(run_ab.invented("```python\npl.col(\"x\").then_fill(0)\n```"))

    def test_parse_and_param_errors_not_counted(self):
        # A keyword-argument mismatch is a real checker finding but NOT a name invention.
        param = run_ab.invented("```python\npl.col(\"x\").sum(not_a_real_kwarg=1)\n```")
        self.assertEqual(param, [])


class Bank(unittest.TestCase):
    def setUp(self):
        self.questions = run_ab.load_questions()
        self.rows = run_ab.catalog_rows()

    def test_categories_are_real_groups(self):
        for q in self.questions:
            self.assertIn(q["category"], self.rows, f"{q['id']}: bad category")

    def test_regimes_known(self):
        for q in self.questions:
            self.assertIn(q["regime"], ("core", "deep"), q["id"])

    def test_traps_are_absent_from_catalog(self):
        # Every trap, written in CODE, must be flagged as invented; if Polars ships one, loudly.
        for q in self.questions:
            for trap in q.get("traps", []):
                self.assertTrue(run_ab.invented(f"```python\n{trap}\n```"),
                                f"{q['id']}: trap {trap} is NOT invented (shipped by Polars?)")


if __name__ == "__main__":
    unittest.main()

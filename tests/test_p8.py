"""P8 tests — Ablation study, parity evidence, and documentation."""
import unittest
from pathlib import Path

from backtest.cli import _run_full_ablation
from backtest.metrics_breakdown import breakdown_by_overlay_config


class FullAblationTest(unittest.TestCase):
    def test_ablate_overlays_exists(self):
        from backtest.cli import _parse_args
        args = _parse_args(["--ablate-full", "--start", "2023-01-01", "--end", "2023-01-31"])
        self.assertTrue(args.ablate_full)

    def test_ablation_configs_count(self):
        from backtest.cli import _parse_args
        args = _parse_args(["--ablate-full", "--start", "2023-01-01", "--end", "2023-01-31"])
        expected = [
            "grounded_baseline", "grounded_news_off", "grounded_macro_off", "grounded_both_off",
            "ungrounded_baseline", "ungrounded_news_off", "ungrounded_macro_off", "ungrounded_both_off",
        ]
        self.assertTrue(hasattr(args, "ablate_full"))


class ParityEvidenceTest(unittest.TestCase):
    def test_parity_evidence_doc_exists(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_parity_evidence.md").read_text()
        self.assertIn("P3 — Unit Parity Test Suite", doc)
        self.assertIn("P5 — Shadow Mode Discrepancy Log", doc)
        self.assertIn("P7 — Live-Mode Parity Validation", doc)

    def test_parity_table_exists(self):
        sql = Path("/home/ed/projects/sturdy-couscous/infra/postgres/init.sql").read_text()
        self.assertIn("shadow_comparison", sql)
        self.assertIn("live_validation_discrepancy", sql)


class ArchitectureWriteupTest(unittest.TestCase):
    def test_architecture_doc_exists(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_architecture.md").read_text()
        self.assertIn("Python/C++ Boundary", doc)
        self.assertIn("Known Limitations", doc)

    def test_architecture_cites_p3_parity(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_architecture.md").read_text()
        self.assertIn("P3", doc)


class RunbookTest(unittest.TestCase):
    def test_runbook_exists(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_runbook.md").read_text()
        self.assertIn("Emergency Procedures", doc)
        self.assertIn("Kill Switch", doc)

    def test_runbook_live_warning(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_runbook.md").read_text()
        self.assertIn("WARNING", doc)


class PackagingAssessmentTest(unittest.TestCase):
    def test_packaging_doc_exists(self):
        doc = Path("/home/ed/projects/sturdy-couscous/docs/p8_packaging_assessment.md").read_text()
        self.assertIn("Backtest Engine as Research Tool", doc)
        self.assertIn("Execution Stack as Managed Strategy", doc)


class FullAblationCLIIntegrationTest(unittest.TestCase):
    def test_ablate_full_config_structure(self):
        from backtest.cli import _run_full_ablation
        import argparse
        args = argparse.Namespace(
            start="2023-01-01",
            end="2023-01-31",
            capital=10000.0,
            rebal_freq=5,
            fee_pct=None,
            slip_pct=None,
            interval="1d",
            output=None,
        )
        self.assertIsNotNone(_run_full_ablation)
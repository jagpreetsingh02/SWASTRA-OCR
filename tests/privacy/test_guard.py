"""Privacy-only tests: no models, medical samples or holdout reads."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "check_privacy.py"
spec = importlib.util.spec_from_file_location("privacy_guard", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PrivacyGuardTests(unittest.TestCase):
    def test_private_paths(self):
        for path in ("eval/real_world/rw_001.truth.json", "eval/real_world_dev/nested/a.txt",
                     "eval/real_world_holdout/a.png", "eval/reports/real_world_ocr.json",
                     "eval/reports/model_selection_real_world/paddleocr-vl.INCOMPLETE.json",
                     "eval/reports/SUMMARY.md", "prescription-data/a.png", "uploads/a.pdf",
                     ".env", "local/.env.secret", "hf_cache/a.json", "a.safetensors",
                     "data/Dataset.zip", "unreviewed/patient.jpeg", "recovery.bundle"):
            with self.subTest(path=path):
                self.assertIsNotNone(guard.path_problem(path))

    def test_safe_paths(self):
        for path in (".env.example", "eval/aggregates/real_world_baseline.json", "eval/real_world/README.md", "eval/real_world/manifest.json",
                     "eval/real_world/truth_template.json", "eval/dev/synthetic.png",
                     "eval/model_selection/real_handwriting.py", guard.AGGREGATE):
            self.assertIsNone(guard.path_problem(path), path)

    def test_aggregate_rejects_raw_text_and_free_strings(self):
        for obj in ({"text": 1}, {"metrics": {"note": "patient detail"}}, {"values": [1, 2]}):
            self.assertIsNotNone(guard.content_problem(guard.AGGREGATE, json.dumps(obj).encode()))
        self.assertIsNone(guard.content_problem(guard.AGGREGATE, b'{"engines":{"test":{"accuracy":0.5}}}'))

    def test_secrets_are_rejected_without_disclosure(self):
        self.assertIsNotNone(guard.content_problem("x.py", b"hf_" + b"x" * 30))
        self.assertIsNotNone(guard.content_problem(".env.example", b"HF_TOKEN=not-empty"))
        self.assertIsNone(guard.content_problem(".env.example", b"HF_TOKEN=\n"))

    def test_staged_content_and_force_added_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args):
                return subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True)
            git("init", "-q")
            p = Path(tmp)
            (p / "safe.txt").write_text("hf_" + "x" * 30)
            git("add", "safe.txt")
            (p / "safe.txt").write_text("clean working tree but unsafe index")
            out = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertNotIn("hf_" + "x" * 30, out.stdout)
            git("add", "safe.txt")
            (p / ".gitignore").write_text(".env\n")
            (p / ".env").write_text("HF_TOKEN=\n")
            git("add", "-f", ".env")
            out = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn("local environment file", out.stdout)

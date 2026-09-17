#!/usr/bin/env python3
"""Reject private artifact paths in the Git index; never display file contents."""
from __future__ import annotations
import argparse
import json
from pathlib import PurePosixPath
import re
import subprocess

REAL_METADATA = {"README.md", "DATASET.md", "manifest.json", "truth_template.json"}
AGGREGATE = "eval/reports/model_selection_real_world/summary.json"
PRIVATE_PARTS = {"prescription-data", "external-data", "datasets", "uploads", "tmp",
                 "hf_cache", "huggingface", "models", ".cache", ".venv", "privacy-recovery"}
MEDIA = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif",
         ".heic", ".heif", ".pdf"}
WEIGHTS_ARCHIVES = {".safetensors", ".gguf", ".pt", ".pth", ".bin", ".ckpt",
                    ".zip", ".tar", ".gz", ".7z", ".bundle"}
SECRET = re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
                    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
RAW_KEYS = {"raw_text", "text", "transcription", "model_wrote", "source_line",
            "patient_name", "doctor_name", "documents_detail"}


def path_problem(path: str) -> str | None:
    p = PurePosixPath(path)
    parts = p.parts
    if any(part in PRIVATE_PARTS for part in parts):
        return "private data/cache directory"
    if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
        return "local environment file"
    if p.suffix.lower() in WEIGHTS_ARCHIVES:
        return "weights, archive or recovery bundle"
    if path == "eval/aggregates/real_world_baseline.json":
        return None  # content_problem enforces numeric-only aggregates
    for i, part in enumerate(parts):
        if part.startswith("real_world"):
            if len(parts) == i + 2 and p.name in REAL_METADATA:
                break
            return "real-world source, transcription or annotation"
    if path.startswith("eval/reports/model_selection_real_world/") and path != AGGREGATE:
        return "real-world per-document model report"
    if path == "eval/reports/SUMMARY.md":
        return "combined report may contain real-world source text"
    if p.suffix.lower() in MEDIA and not any(path.startswith(s) for s in
            ("eval/dev/", "eval/heldout/", "eval/controls/")):
        return "document/media outside synthetic fixture directories"
    return None


def numeric_aggregate(value: object) -> bool:
    # Keys are metric/engine/category labels; values must never carry free text.
    if isinstance(value, dict):
        return all(k not in RAW_KEYS and numeric_aggregate(v) for k, v in value.items())
    return value is None or isinstance(value, (int, float, bool))


def content_problem(path: str, data: bytes) -> str | None:
    if SECRET.search(data):
        return "credential/private-key pattern"
    if path in {AGGREGATE, "eval/aggregates/real_world_baseline.json"}:
        try:
            value = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return "invalid aggregate JSON"
        if not isinstance(value, dict) or not numeric_aggregate(value):
            return "aggregate must contain numeric metrics only, with no source text"
    if PurePosixPath(path).name == ".env.example":
        for line in data.decode("utf-8", errors="replace").splitlines():
            if re.match(r"\s*(?:export\s+)?HF_TOKEN\s*=\s*\S", line):
                return "HF_TOKEN example must be empty"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="check every tracked index entry (CI)")
    args = parser.parse_args()
    cmd = ["git", "ls-files", "-z"] if args.all else [
        "git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    paths = subprocess.check_output(cmd).decode().split("\0")
    failures = []
    for path in filter(None, paths):
        reason = path_problem(path)
        if reason is None:
            data = subprocess.check_output(["git", "show", ":" + path])
            reason = content_problem(path, data)
        if reason:
            failures.append((path, reason))
    for path, reason in failures:
        print(f"Privacy check blocked {path!r}: {reason}")
    if failures:
        print("Keep raw medical artifacts local. See PRIVACY.md. No file contents were printed.")
    else:
        print("Privacy path and credential checks passed (not proof of de-identification).")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())

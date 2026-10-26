"""Benchmark the pipeline on labelled samples and write a Markdown + JSON report.

Usage:
    python scripts/generate_samples.py --out samples --count 12
    python scripts/evaluate.py --samples samples --report reports/evaluation.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from invoice_ocr.evaluation import field_accuracy, line_cer, line_wer  # noqa: E402
from invoice_ocr.pipeline import InvoicePipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", default="samples")
    parser.add_argument("--report", default="reports/evaluation.md")
    args = parser.parse_args()

    samples_dir = Path(args.samples)
    manifest = json.loads((samples_dir / "ground_truth.json").read_text(encoding="utf-8"))
    pipeline = InvoicePipeline()

    rows = []
    for item in manifest:
        result = pipeline.run_path(str(samples_dir / item["file"]))
        predicted = result.fields.to_dict()
        acc = field_accuracy(item["expected"], predicted)
        rows.append({
            "file": item["file"],
            "difficulty": item["difficulty"],
            "cer": round(line_cer(item["reference_lines"], result.text), 4),
            "wer": round(line_wer(item["reference_lines"], result.text), 4),
            "field_accuracy": acc["accuracy"],
            "failed_fields": [k for k, ok in acc["per_field"].items() if not ok],
            "confidence": result.mean_confidence,
            "latency_ms": result.timings_ms["total"],
            "arithmetic_ok": predicted["arithmetic_ok"],
        })

    def summarise(subset: list[dict]) -> dict:
        return {
            "n": len(subset),
            "avg_cer": round(statistics.mean(r["cer"] for r in subset), 4),
            "avg_wer": round(statistics.mean(r["wer"] for r in subset), 4),
            "avg_field_accuracy": round(statistics.mean(r["field_accuracy"] for r in subset), 4),
            "avg_confidence": round(statistics.mean(r["confidence"] for r in subset), 1),
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in subset), 1),
            "p95_latency_ms": round(sorted(r["latency_ms"] for r in subset)[max(int(len(subset) * 0.95) - 1, 0)], 1),
        }

    by_level = defaultdict(list)
    for r in rows:
        by_level[r["difficulty"]].append(r)
    summary = {"overall": summarise(rows), **{k: summarise(v) for k, v in by_level.items()}}

    lines = [
        "# Evaluation Report", "",
        f"Samples: {len(rows)} synthetic invoices (clean / medium / hard degradation).", "",
        "| Slice | N | CER | WER | Field acc. | Avg conf. | Avg latency (ms) | p95 (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summary.items():
        lines.append(
            f"| {name} | {s['n']} | {s['avg_cer']:.2%} | {s['avg_wer']:.2%} | {s['avg_field_accuracy']:.2%} "
            f"| {s['avg_confidence']} | {s['avg_latency_ms']} | {s['p95_latency_ms']} |"
        )
    lines += ["", "## Per-file results", "",
              "| File | Difficulty | CER | WER | Field acc. | Failed fields |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['file']} | {r['difficulty']} | {r['cer']:.2%} | {r['wer']:.2%} | "
                     f"{r['field_accuracy']:.0%} | {', '.join(r['failed_fields']) or '-'} |")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\nFull report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

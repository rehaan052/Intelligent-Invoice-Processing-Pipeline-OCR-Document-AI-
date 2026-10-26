# Evaluation Report

Samples: 30 synthetic invoices (clean / medium / hard degradation).

| Slice | N | CER | WER | Field acc. | Avg conf. | Avg latency (ms) | p95 (ms) |
|---|---|---|---|---|---|---|---|
| overall | 30 | 1.09% | 5.63% | 100.00% | 91.9 | 276.2 | 298.6 |
| clean | 10 | 1.62% | 9.25% | 100.00% | 89.5 | 272.6 | 293.8 |
| medium | 10 | 0.71% | 3.83% | 100.00% | 93.3 | 285.0 | 298.6 |
| hard | 10 | 0.94% | 3.82% | 100.00% | 92.8 | 271.1 | 287.4 |

## Per-file results

| File | Difficulty | CER | WER | Field acc. | Failed fields |
|---|---|---|---|---|---|
| invoice_001_clean.png | clean | 1.22% | 7.69% | 100% | - |
| invoice_002_medium.png | medium | 0.93% | 3.92% | 100% | - |
| invoice_003_hard.png | hard | 1.75% | 9.62% | 100% | - |
| invoice_004_clean.png | clean | 1.19% | 7.69% | 100% | - |
| invoice_005_medium.png | medium | 1.08% | 5.26% | 100% | - |
| invoice_006_hard.png | hard | 0.76% | 1.67% | 100% | - |
| invoice_007_clean.png | clean | 1.50% | 9.62% | 100% | - |
| invoice_008_medium.png | medium | 0.26% | 1.61% | 100% | - |
| invoice_009_hard.png | hard | 1.33% | 5.26% | 100% | - |
| invoice_010_clean.png | clean | 1.21% | 7.84% | 100% | - |
| invoice_011_medium.png | medium | 1.34% | 6.90% | 100% | - |
| invoice_012_hard.png | hard | 0.28% | 1.75% | 100% | - |
| invoice_013_clean.png | clean | 2.14% | 10.00% | 100% | - |
| invoice_014_medium.png | medium | 0.53% | 1.64% | 100% | - |
| invoice_015_hard.png | hard | 1.59% | 5.26% | 100% | - |
| invoice_016_clean.png | clean | 1.55% | 9.80% | 100% | - |
| invoice_017_medium.png | medium | 0.30% | 1.96% | 100% | - |
| invoice_018_hard.png | hard | 1.37% | 5.36% | 100% | - |
| invoice_019_clean.png | clean | 1.37% | 8.77% | 100% | - |
| invoice_020_medium.png | medium | 0.50% | 3.23% | 100% | - |
| invoice_021_hard.png | hard | 0.28% | 1.79% | 100% | - |
| invoice_022_clean.png | clean | 2.39% | 11.54% | 100% | - |
| invoice_023_medium.png | medium | 0.77% | 4.84% | 100% | - |
| invoice_024_hard.png | hard | 0.93% | 1.96% | 100% | - |
| invoice_025_clean.png | clean | 1.29% | 8.06% | 100% | - |
| invoice_026_medium.png | medium | 0.84% | 5.36% | 100% | - |
| invoice_027_hard.png | hard | 0.85% | 3.51% | 100% | - |
| invoice_028_clean.png | clean | 2.29% | 11.54% | 100% | - |
| invoice_029_medium.png | medium | 0.55% | 3.57% | 100% | - |
| invoice_030_hard.png | hard | 0.29% | 2.00% | 100% | - |

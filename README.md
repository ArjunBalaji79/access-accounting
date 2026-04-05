# Access Accounting

**A Framework for Measuring and Reporting AI Compute Availability for Governance**

SIPA AI Club Research Team | Columbia University  
Submitted to TAIGR @ ICML 2026 (Seoul, South Korea)

---

## Overview

Policymakers use compute as a governance lever — through export controls, public compute programs, and international frameworks — but no standardized methodology exists for measuring **who can actually access what compute**. This project provides:

1. **Access Availability Record (AAR)** — a structured reporting schema for compute access across physical, economic, and legal dimensions
2. **Effective Compute Access (ECA)** — a composite metric revealing how access gaps compound across layers
3. **A reference implementation** computing AAR and ECA from public data

## Quick Start

```bash
pip install -r requirements.txt

# Step 1: Build AAR records from config
python -m src.aar --config data/ --output outputs/tables/aar_records.csv

# Step 2: Compute ECA
python -m src.eca --aar outputs/tables/aar_records.csv --budget 10000 --hours 720

# Step 3: Run sensitivity analysis
python -m src.sensitivity --aar outputs/tables/aar_records.csv

# Step 4: Generate figures
python -m src.visualize --results outputs/tables/ --output outputs/figures/

# Run tests
pytest tests/ -v
```

## Data Sources

All inputs are publicly verifiable. See `data/README.md` for exact sourcing instructions.

| Data | Source |
|------|--------|
| GPU pricing | AWS/GCP/Azure public pricing pages |
| PPP factors | World Bank ICP 2024 |
| GPU specs | NVIDIA official datasheets |
| BIS export tiers | Federal Register 90 FR 4544 |

## Citation

```bibtex
@inproceedings{accessaccounting2026,
  title={Access Accounting: A Framework for Measuring and Reporting AI Compute Availability for Governance},
  author={SIPA AI Club Research Team},
  booktitle={TAIGR Workshop @ ICML 2026},
  year={2026}
}
```

## License

MIT

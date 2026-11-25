# Data for the platform comparison

`wisconsin.csv`: the Wisconsin Diagnostic Breast Cancer data (569 rows: 357 `B`, 212 `M`; 30 numeric
features, target `diagnosis`), the tabular use case of decision 0008. Source: UCI Machine Learning
Repository, "Breast Cancer Wisconsin (Diagnostic)" (Wolberg, Mangasarian, Street, Street, 1993),
CC BY 4.0, exported from the copy bundled with scikit-learn 1.7.2 (`load_breast_cancer`) with the
feature names' spaces replaced by `_`, and `target` mapped to `diagnosis` (0 → `M`, 1 → `B`).

Used by `python -m distributed.platform_compare --csv distributed/data/wisconsin.csv ...` (from `training/`).

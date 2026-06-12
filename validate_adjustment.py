#!/usr/bin/env python3
"""
validate_adjustment.py
-----------------------
Pre-flight validation for an APSONA bulk-adjustment upload.

Before pushing a bulk update back into Salesforce, this script checks the
adjustment file against the original batch export so that a single upload
cannot silently corrupt records. It answers four questions a careful operator
should always ask before a bulk write:

  1. Does every record I'm about to change actually exist in the source batch?
     (No orphan IDs writing to the wrong records.)
  2. Am I changing exactly the records I expect, and no more?
     (Row count and uniqueness.)
  3. Of the records in the file, how many genuinely change vs. are no-ops?
     (A no-op write is harmless but inflates the change log; worth knowing.)
  4. Are all keys well-formed, non-blank, non-duplicated?

It prints a human-readable report and writes a clean, deduped, upload-ready
file. If any blocking issue is found it exits non-zero so the upload step can
be gated in a script or pipeline.

Usage:
    python scripts/validate_adjustment.py \
        --original data/batch_export_original.csv \
        --adjustment data/adjustment_upload.csv \
        --field "GAU Allocation" \
        --out data/adjustment_validated.csv

No live Salesforce credentials are used or required. Inputs are flat CSVs
exported from / staged for APSONA.
"""

import argparse
import sys
import pandas as pd

ID_COL = "Opportunity ID"


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df


def looks_like_sf_id(value: str) -> bool:
    """Salesforce IDs are 15 or 18 alphanumeric characters."""
    v = value.strip()
    return len(v) in (15, 18) and v.isalnum()


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate an APSONA bulk-adjustment upload.")
    ap.add_argument("--original", required=True, help="Original batch export CSV.")
    ap.add_argument("--adjustment", required=True, help="Adjustment upload CSV (Id + changed field).")
    ap.add_argument("--field", required=True, help="Name of the field being adjusted.")
    ap.add_argument("--out", default="adjustment_validated.csv", help="Path for the cleaned upload-ready file.")
    args = ap.parse_args()

    original = load(args.original)
    adjustment = load(args.adjustment)

    issues = []   # blocking problems
    notes = []    # informational

    # --- structural checks -------------------------------------------------
    for col, df, label in ((ID_COL, original, "original"), (ID_COL, adjustment, "adjustment")):
        if col not in df.columns:
            issues.append(f"Missing key column '{col}' in {label} file.")
    if args.field not in adjustment.columns:
        issues.append(f"Adjustment file has no '{args.field}' column to write.")
    if issues:
        report(issues, notes, blocking=True)
        return 1

    # --- key quality on the adjustment file --------------------------------
    blanks = adjustment[adjustment[ID_COL].str.strip() == ""]
    if len(blanks):
        issues.append(f"{len(blanks)} adjustment row(s) have a blank {ID_COL}.")

    malformed = adjustment[~adjustment[ID_COL].apply(looks_like_sf_id)]
    malformed = malformed[malformed[ID_COL].str.strip() != ""]
    if len(malformed):
        issues.append(f"{len(malformed)} adjustment row(s) have a malformed {ID_COL} "
                      f"(not 15/18 alphanumeric): {malformed[ID_COL].tolist()[:5]}...")

    dupes = adjustment[adjustment.duplicated(subset=[ID_COL], keep=False)]
    if len(dupes):
        issues.append(f"{dupes[ID_COL].nunique()} {ID_COL}(s) appear more than once in the adjustment file "
                      f"({len(dupes)} rows total). Duplicate keys can produce conflicting writes.")

    # --- referential check: every adjustment Id must exist in the batch ----
    orig_ids = set(original[ID_COL].str.strip())
    adj_ids = set(adjustment[ID_COL].str.strip()) - {""}
    orphans = adj_ids - orig_ids
    if orphans:
        issues.append(f"{len(orphans)} adjustment Id(s) are NOT in the original batch "
                      f"(would write to records outside this batch): {list(orphans)[:5]}...")

    # --- scope check: counts ----------------------------------------------
    notes.append(f"Original batch records:      {len(original)}")
    notes.append(f"Adjustment rows submitted:   {len(adjustment)}")
    notes.append(f"Unique records targeted:     {len(adj_ids)}")
    missing_from_adj = orig_ids - adj_ids
    if missing_from_adj:
        notes.append(f"Records in batch NOT being adjusted: {len(missing_from_adj)} "
                     f"(expected if the change applies to a subset).")

    # --- effect check: real changes vs. no-ops -----------------------------
    if args.field in original.columns:
        merged = adjustment.merge(
            original[[ID_COL, args.field]].rename(columns={args.field: "_old"}),
            on=ID_COL, how="left",
        )
        merged["_new"] = merged[args.field].str.strip()
        merged["_old"] = merged["_old"].fillna("").str.strip()
        changed = merged[(merged[ID_COL].isin(orig_ids)) & (merged["_new"] != merged["_old"])]
        noops = merged[(merged[ID_COL].isin(orig_ids)) & (merged["_new"] == merged["_old"])]
        notes.append(f"Records that will actually change '{args.field}': {len(changed)}")
        if len(noops):
            notes.append(f"No-op rows (value already correct): {len(noops)}")
        if len(changed):
            sample = changed.iloc[0]
            notes.append(f"Example change: '{sample['_old']}' -> '{sample['_new']}'")
    else:
        notes.append(f"Field '{args.field}' not present in original export; "
                     f"skipping before/after comparison.")

    # --- write cleaned, deduped, in-scope output ---------------------------
    clean = adjustment.copy()
    clean[ID_COL] = clean[ID_COL].str.strip()
    clean = clean[clean[ID_COL] != ""]
    clean = clean[clean[ID_COL].apply(looks_like_sf_id)]
    clean = clean[clean[ID_COL].isin(orig_ids)]
    clean = clean.drop_duplicates(subset=[ID_COL], keep="first")
    clean.to_csv(args.out, index=False)
    notes.append(f"Wrote upload-ready file: {args.out} ({len(clean)} rows).")

    report(issues, notes, blocking=bool(issues))
    return 1 if issues else 0


def report(issues, notes, blocking):
    print("=" * 60)
    print("APSONA BULK-ADJUSTMENT VALIDATION REPORT")
    print("=" * 60)
    for n in notes:
        print(f"  {n}")
    print("-" * 60)
    if issues:
        print(f"BLOCKING ISSUES ({len(issues)}):")
        for i in issues:
            print(f"  [X] {i}")
        print("\nResult: NOT SAFE TO UPLOAD. Resolve the issues above first.")
    else:
        print("Result: PASSED. Validated file is safe to upload via APSONA.")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())

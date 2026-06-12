# APSONA Bulk-Adjustment Workflow (Salesforce NPSP)

A repeatable, validated process for correcting a batch of Salesforce
Opportunities in a single bulk operation instead of editing each record by
hand — with a pre-flight data check so one upload can't silently corrupt
records.

> **Note on data:** Every record in this repository is **synthetic**. No real
> donor, organization, financial, or constituent data is included. The IDs,
> names, amounts, and accounting codes are fabricated to demonstrate the
> *method*. The technique is exactly what I run in production; the data is not.

---

## The problem

A batch import created **39 Opportunities** in Salesforce (NPSP). After the
fact, all 39 were found to be coded to the wrong General Accounting Unit (GAU)
designation. They needed to be recoded to the correct fund.

The default path — opening each Opportunity and editing it in the Salesforce
UI — means **39 separate manual edits**. That is slow, easy to get wrong on
record 31 of 39, and leaves 39 separate change events to reconcile if
something looks off later.

## The approach

Rather than touch records one at a time, I built a **single APSONA adjustment
upload**:

1. **Export** the batch from Salesforce via APSONA, keyed on Opportunity ID.
2. **Stage** an adjustment file containing only the record key and the one
   field being corrected (`GAU Allocation`).
3. **Validate before writing.** Run a pre-flight check (`scripts/validate_adjustment.py`)
   that confirms every record I'm about to change actually belongs to the
   batch, that keys are well-formed and unique, and that the change is real
   rather than a no-op.
4. **Upload once.** Push the validated file through APSONA as a single update
   matched on record ID.

The validation step is the part that matters most. A bulk write is only as
safe as your confidence that you're writing to the right records — the script
turns that confidence into something checked rather than assumed.

## The result

| | Record-by-record | This workflow |
|---|---|---|
| Manual edits | 39 | 1 upload |
| Risk of inconsistent values | High (per-record drift) | None (one source value) |
| Auditability | 39 scattered changes | 1 logged change set |
| Pre-write safety check | None | Referential + key validation |
| Repeatability | Re-do by hand each time | Re-run the same process |

The same workflow scales to any batch size and any single-field correction —
GAU recodes, stage corrections, campaign reassignments — without changing the
method.

---

## Repository contents

```
apsona-bulk-adjustment/
├── README.md
├── requirements.txt
├── data/
│   ├── batch_export_original.csv     # 39 synthetic Opportunities, mis-coded GAU
│   ├── adjustment_upload.csv         # the staged correction (Id + corrected field)
│   └── adjustment_validated.csv      # output of the validation step (upload-ready)
├── scripts/
│   └── validate_adjustment.py        # pre-flight validation (pandas)
└── docs/
    └── field_mapping.md              # field-by-field mapping + NPSP notes
```

## Running the validation

```bash
pip install -r requirements.txt

python scripts/validate_adjustment.py \
    --original data/batch_export_original.csv \
    --adjustment data/adjustment_upload.csv \
    --field "GAU Allocation" \
    --out data/adjustment_validated.csv
```

The script prints a report, writes a cleaned upload-ready file, and exits
non-zero if it finds a blocking issue — so it can gate an upload step in a
larger script or pipeline. It checks for: missing/blank/malformed Salesforce
IDs, duplicate keys, and "orphan" IDs that don't exist in the source batch
(records that would be written to in error). It also reports how many records
genuinely change versus how many are already correct.

---

## Why this is here

This is a sanitized version of a real process-improvement I delivered in a
nonprofit Salesforce operations role. I keep the production artifact private;
this exists to show the method, the documentation discipline behind it, and
the data-integrity thinking that goes into a bulk write before it ever
touches a live org. Happy to walk through the production specifics in an
interview or under NDA.
   

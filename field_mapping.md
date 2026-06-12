# Field Mapping & Notes

This documents the fields used in the adjustment and how they map between the
Salesforce export, the staged adjustment file, and the upload. All values are
synthetic.

## Adjustment file → Salesforce

The adjustment upload is deliberately **narrow**: it carries the match key and
only the field being changed. Nothing else is included, so there is no risk of
overwriting a field that wasn't meant to change.

| Column in upload | Maps to (Salesforce) | Role | Notes |
|---|---|---|---|
| `Opportunity ID` | `Opportunity.Id` | **Match key** | 18-char ID. APSONA matches the update on this; it is never edited. |
| `GAU Allocation` | (see note below) | **Field being corrected** | The single value being changed across all 39 records. |

## Original export columns (for reference / validation only)

These come from the batch export and are used by the validation script to
confirm scope and compute before/after. They are **not** part of the upload.

| Column | Maps to | Used for |
|---|---|---|
| `Opportunity Name` | `Opportunity.Name` | Human-readable identification |
| `Account Name` | `Opportunity.Account.Name` | Donor/org context |
| `Amount` | `Opportunity.Amount` | Reconciliation context |
| `Close Date` | `Opportunity.CloseDate` | Batch-period context |
| `Stage` | `Opportunity.StageName` | Confirming records are Closed Won |
| `GAU Allocation` | (see note) | Before/after comparison in validation |
| `Batch` | custom batch identifier | Confirming all records share one batch |

## NPSP note on GAU Allocations

In NPSP, a General Accounting Unit allocation is technically stored on the
**GAU Allocation object** (`npsp__Allocation__c`), related to the Opportunity,
rather than as a plain text field on the Opportunity itself. A real recode may
therefore target allocation records keyed to their own IDs and the parent
Opportunity ID, depending on how the org models single vs. multiple
allocations per gift.

For clarity, this demonstration represents the designation as a single field
so the *method* — export, stage a narrow correction, validate against the
source, upload once — reads cleanly. The validation logic (match on a stable
key, confirm referential integrity, reject orphans and duplicates, write only
in-scope rows) is identical regardless of which object the field lives on.

## Why "validate before write" is the point

A bulk update is fast, which is exactly why it deserves a check. The risk is
never the records you can see — it's the stray ID that doesn't belong, the
duplicate key that writes twice, or the malformed value that fails silently.
Catching those before the upload turns a bulk write from a leap of faith into
a controlled, auditable change.

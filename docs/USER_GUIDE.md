# Migration Bridge — User Guide

Migration Bridge validates data migration from **Salesforce (IQVIA OCE-P)** to **Veeva Vault CRM** and supports target data cleanup. It compares source and target records field-by-field and generates detailed validation reports.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Connections](#2-connections)
3. [Projects](#3-projects)
4. [Data Model Mappings](#4-data-model-mappings)
5. [Importing a Mapping Sheet](#5-importing-a-mapping-sheet)
6. [Running a Validation](#6-running-a-validation)
7. [Understanding Validation Results](#7-understanding-validation-results)
8. [Exporting Reports](#8-exporting-reports)
9. [Target Cleanup](#9-target-cleanup)
10. [Tips for Large Datasets](#10-tips-for-large-datasets)

---

## 1. Getting Started

### Register & Login

1. Open the application URL in your browser.
2. On the login page, switch to the **Register** tab to create an account.
3. After registration, sign in with your credentials.

The left sidebar provides navigation to **Connections** and **Projects**.

---

## 2. Connections

Connections define how Migration Bridge connects to your source and target systems.

### Creating a Connection

1. Navigate to **Connections** in the sidebar.
2. Click **New Connection**.
3. Fill in the details:

| Field | Description |
|---|---|
| **Name** | A descriptive name (e.g., "OCE-P UAT Sandbox") |
| **System Type** | Salesforce (IQVIA OCEP) or Veeva Vault CRM |
| **Environment** | Sandbox or Production |

**For Salesforce:**

| Field | Description |
|---|---|
| Instance URL | e.g., `https://myorg.my.salesforce.com` |
| Username | Salesforce username |
| Password | Salesforce password |
| Security Token | Salesforce security token |
| Consumer Key | (Optional) Connected App consumer key |
| Consumer Secret | (Optional) Connected App consumer secret |

**For Veeva Vault:**

| Field | Description |
|---|---|
| Vault DNS | e.g., `https://myvault.veevavault.com` |
| Username | Vault username |
| Password | Vault password |

### Testing a Connection

Click the **Test** button next to any connection to verify connectivity.

---

## 3. Projects

A project links a source connection (Salesforce) to a target connection (Veeva Vault) and contains all object mappings, validation runs, and cleanup jobs.

### Creating a Project

1. Navigate to **Projects** in the sidebar.
2. Click **New Project**.
3. Enter a name, optional description, and select the source and target connections.

### Opening a Project

Click **Open** on any project to access its detail page with three tabs:
- **Data Model Mappings** — object and field mapping configuration
- **Validation** — run and review validation results
- **Target Cleanup** — delete migrated data from Veeva Vault

---

## 4. Data Model Mappings

### Object Mappings

An object mapping defines a source-to-target object pair (e.g., `OCE__Call__c → call2__v`).

1. Click **Add Object Mapping**.
2. Select the source object (Salesforce) and target object (Veeva Vault).
3. Click **OK**.

### Field Mappings

1. Click **Fields** on an object mapping row.
2. Use **Auto-Map** to suggest mappings based on name similarity, or add them manually.

### Match Keys

Match keys define how records are correlated between systems (e.g., Salesforce `Id` → Veeva `legacy_crm_id__v`).

1. Click **Keys** on an object mapping row.
2. Add match key pairs.

Match keys are required for validation. Objects without match keys are skipped during validation.

---

## 5. Importing a Mapping Sheet

For large-scale migrations, import an Excel mapping sheet to define all mappings at once.

### How to Import

1. Click the **Import Mapping Sheet** icon on the project detail page.
2. Select your `.xlsx` file.
3. The system processes all sheets with "Mapping" in the name (except "Mapping Objects").

### Expected Sheet Format

Each sheet should have these columns (Row 2 as headers):

| Column | Purpose |
|---|---|
| `EntityApiName` | Source object API name |
| `QualifiedApiName` | Source field API name |
| `DataType` | Source field data type |
| `Object Name` | Target object API name |
| `Field Name` | Target field API name |
| `Field Type` | Target field data type |
| `Relevant for Migration` | (Optional) "Yes"/"No" — "No" rows are skipped |

If the sheet has duplicate column headers (e.g., reference columns on the right), the importer uses the first occurrence.

Re-importing replaces existing field mappings for each object.

---

## 6. Running a Validation

### Starting a Validation Run

1. Go to the **Validation** tab.
2. Click **New Validation Run**.
3. Configure:

| Option | Description |
|---|---|
| **Mode** | `auto` (recommended), `realtime`, or `batch` |
| **Objects** | Select specific objects, or leave empty for all |
| **Source WHERE Clause** | Custom SOQL filter for source records |
| **Date Range** | Only validate records from the last N months |
| **Record Limit** | Cap records per object for sampling |

4. Click **OK** to start.

### Source WHERE Clause

Enter any valid SOQL WHERE condition (without the `WHERE` keyword):

```
OCE__Account__c in ('0013X00003gWtRSQA0', '00169000034NS6eAAG')
```

```
CreatedDate >= 2025-01-01T00:00:00Z
```

For child objects (e.g., `OCE__CallEmployeeAttendee__c`), the engine automatically rewrites the WHERE clause to use the parent relationship path. For example, `OCE__Account__c in (...)` becomes `OCE__Call__r.OCE__Account__c in (...)`.

### Quick Buttons

- **Date Range:** 3M, 6M, 1Y, 2Y, 3Y, All
- **Record Limit:** 1K, 5K, 10K, 50K, All

### Monitoring Progress

Progress updates every 3 seconds:

| Phase | Display |
|---|---|
| Initializing | "Initializing validation run..." |
| Connecting | "Connecting to source & target systems..." |
| Fetching Source | "Fetching source records... 4,200 fetched" |
| Fetching Target | "Fetching target records... 3,100 fetched" |
| Comparing | "Comparing records... 78%" |
| Done | Green "Done" tag |

### Cancelling

Click the **Cancel** button next to a running validation.

---

## 7. Understanding Validation Results

### Summary View

Click **View Results** to see per-object summaries:

| Column | Description |
|---|---|
| **Source / Target** | Object names |
| **Source Count** | Records fetched from source |
| **Target Count** | Records fetched from target |
| **Matched** | Records found in target |
| **With Warnings** | Matched records that have field-level differences |
| **Missing in Target** | Source records not found in target |
| **Match %** | Percentage of source records found in target |

### Record Status

Records are classified as:

| Status | Meaning |
|---|---|
| **matched** | Record found in target. All fields match. |
| **matched ⚠️** | Record found in target. Some fields have warnings (see below). |
| **missing in target** | Record not found in target system. |

A record is always considered **matched** if it exists in the target. Field-level differences are shown as warnings, not failures.

### Field-Level Details

Expand any matched record to see all field comparisons, grouped into three sections:

**Issues (warnings)** — fields where values differ:

| Tag | Meaning |
|---|---|
| `Mismatch` | Source and target values are different |
| `Missing in Target` | Source has a value, target is null |
| `Extra in Target` | Source is null, target has a value |

**ID References** — fields that are expected to differ between systems (shown with blue `ID Reference` tag). These include lookup fields, reference fields, and system IDs. They are not counted as mismatches.

**Matching Attributes** — fields where source and target values match (shown in green).

### Smart Value Comparison

The validation engine handles cross-system differences automatically:

| Scenario | Example | Result |
|---|---|---|
| Date format differences | `2025-09-10T14:05:10.000+0000` vs `2025-09-10T14:05:10.000Z` | Match |
| DateTime vs Date | `2025-09-16T22:00:00.000+0000` vs `2025-09-16` | Match |
| Null vs zero | `null` vs `0` | Match |
| Numeric boolean | `0` vs `false`, `1` vs `true` | Match |
| Vault picklist arrays | `Submitted` vs `['submitted__v']` | Match |
| Vault API name suffixes | `Submitted` vs `submitted_v` | Match |
| ID/Reference fields | `0056900000CqrA7AAJ` vs `32284543` | ID Reference (not a mismatch) |

---

## 8. Exporting Reports

### Summary Export

Click the **Export** icon next to a validation run to download the summary as CSV.

### Detail Export

In the record details view, click the download icon next to a summary row to export field-level comparisons as CSV.

Filter by status before exporting — only filtered records are included.

---

## 9. Target Cleanup

The Target Cleanup tab allows you to delete migrated transactional data from Veeva Vault CRM.

### How It Works

1. Records are deleted in **reverse dependency order** — children first, then parents.
2. Master data (accounts, users, territories, products) is **never deleted**.
3. The deletion order follows the SOP migration steps hierarchy (Step 8 → Step 1).

### Starting a Cleanup Job

1. Go to the **Target Cleanup** tab.
2. Click **New Cleanup Job**.
3. Select a filter mode:

| Filter Mode | Description |
|---|---|
| **Legacy CRM ID** | Deletes records where `legacy_crm_id__v` is not empty. These are records that were migrated from Salesforce. |
| **Country** | Deletes transactional data related to accounts in a specific country. Enter the country code (e.g., CH, DE, US). The engine traverses parent relationships to find the account's `country_code__v`. |

4. Click **Start Cleanup**.

⚠️ **This permanently deletes records from Veeva Vault. This action cannot be undone.**

### Monitoring Progress

The cleanup job list shows:

| Column | Description |
|---|---|
| **Status** | running, completed, failed, cancelled |
| **Progress** | "Done — X deleted" or "Step Y/Z: object_name" |
| **Filter** | Which filter mode was used |

### Viewing Results

Click **Details** on a completed job to see per-object results:

| Column | Description |
|---|---|
| **Object** | Vault object name |
| **Step** | Deletion order step number |
| **Found** | Records matching the filter |
| **Deleted** | Records successfully deleted |
| **Failed** | Records that failed to delete |
| **Status** | Done, Partial, No records, or Error |

### Cancelling

Click **Cancel** on a running cleanup job to stop it. Records already deleted are not restored.

---

## 10. Tips for Large Datasets

### Use Filters

For objects with millions of records, always use filters:

1. **WHERE clause** — most precise. Filter by account, date range, or status.
2. **Date Range** — quick filter by `CreatedDate`.
3. **Record Limit** — cap records per object for sampling.

**Recommended for demos:** WHERE clause with specific account IDs + 5K record limit. Completes in 1-2 minutes.

### WHERE Clause for Child Objects

When validating "All" objects with a WHERE clause, the engine automatically rewrites the clause for child objects. For example:

- Parent object `OCE__Call__c`: `WHERE OCE__Account__c in ('...')`
- Child object `OCE__CallEmployeeAttendee__c`: automatically becomes `WHERE OCE__Call__r.OCE__Account__c in ('...')`

### Objects Without Match Keys

Objects without configured match keys are **skipped** (not failed). Configure match keys for all objects you want to validate.

### Validation Logic

- Validates **source → target only**: checks whether each source record exists in the target.
- Records in the target that don't exist in the source are not reported.
- Invalid fields (not in the source/target schema) are automatically skipped.
- ID and reference fields are shown but not counted as mismatches.

# Migration Bridge — User Guide

Migration Bridge is a web application for validating data migration from **Salesforce (IQVIA OCE-P)** to **Veeva Vault CRM**. It compares source and target records field-by-field, identifies mismatches, missing records, and missing attributes, and generates detailed validation reports.

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
9. [Tips for Large Datasets](#9-tips-for-large-datasets)

---

## 1. Getting Started

### Register & Login

1. Open the application URL in your browser.
2. On the login page, switch to the **Register** tab to create an account (username, email, password).
3. After registration, switch back to the **Login** tab and sign in.

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

**For Salesforce connections:**

| Field | Description |
|---|---|
| Instance URL | e.g., `https://myorg.my.salesforce.com` |
| Username | Salesforce username |
| Password | Salesforce password |
| Security Token | Salesforce security token |
| Consumer Key | (Optional) Connected App consumer key |
| Consumer Secret | (Optional) Connected App consumer secret |

**For Veeva Vault connections:**

| Field | Description |
|---|---|
| Vault DNS | e.g., `https://myvault.veevavault.com` |
| Username | Vault username |
| Password | Vault password |

### Testing a Connection

Click the **Test** button next to any connection to verify connectivity. A success or error message will appear.

---

## 3. Projects

A project links a source connection (Salesforce) to a target connection (Veeva Vault) and contains all object mappings and validation runs.

### Creating a Project

1. Navigate to **Projects** in the sidebar.
2. Click **New Project**.
3. Enter a name, optional description, and select the source and target connections.
4. Click **OK**.

### Opening a Project

Click **Open** on any project to access its detail page, which has two tabs:
- **Data Model Mappings** — define which source objects map to which target objects and how fields correspond
- **Validation** — run and review validation results

---

## 4. Data Model Mappings

### Object Mappings

An object mapping defines a source-to-target object pair (e.g., `OCE__Call__c → call2__v`).

**To add an object mapping manually:**
1. On the Data Model Mappings tab, click **Add Object Mapping**.
2. Select the source object (Salesforce) and target object (Veeva Vault) from the dropdowns.
3. Click **OK**.

### Field Mappings

Field mappings define which source fields correspond to which target fields within an object mapping.

**To view/manage field mappings:**
1. Click **Fields** on an object mapping row.
2. The field mappings modal shows all mapped fields.

**Auto-Map:** Click **Auto-Map** to let the system suggest field mappings based on name similarity. Review the suggestions and click **Apply** to accept them.

### Match Keys

Match keys define how records are matched between source and target (e.g., Salesforce `Id` matches Veeva `legacy_crm_id__v`).

**To manage match keys:**
1. Click **Keys** on an object mapping row.
2. Add match key pairs (source field → target field).

Match keys are required for validation — without them, the engine cannot correlate source and target records.

---

## 5. Importing a Mapping Sheet

For large-scale migrations, you can import an Excel mapping sheet that defines all object mappings, field mappings, and match keys at once.

### How to Import

1. On the project detail page, click **Import Mapping Sheet** (upload icon).
2. Select your `.xlsx` file.
3. The system processes all sheets with "Mapping" in the name (except "Mapping Objects").

### Expected Sheet Format

Each mapping sheet should have these columns (Row 2 as headers):

| Column | Purpose |
|---|---|
| `EntityApiName` | Source object API name |
| `QualifiedApiName` | Source field API name |
| `DataType` | Source field data type |
| `Object Name` | Target object API name |
| `Field Name` | Target field API name |
| `Field Type` | Target field data type |
| `Relevant for Migration` | (Optional) "Yes"/"No" — rows with "No" are skipped |

**Note:** If the sheet has duplicate column headers (e.g., a reference target field list on the right side), the importer uses the **first occurrence** of each column name.

### What Happens on Import

- If an object mapping already exists, its field mappings are **replaced** with the sheet data.
- If an object mapping doesn't exist, it is created.
- The import summary shows how many object mappings and field mappings were created from each sheet.

---

## 6. Running a Validation

### Starting a Validation Run

1. Go to the **Validation** tab on the project detail page.
2. Click **New Validation Run**.
3. Configure the run:

| Option | Description |
|---|---|
| **Mode** | `auto` (recommended), `realtime`, or `batch` |
| **Objects to Validate** | Select specific object mappings, or leave empty for all |
| **Source WHERE Clause** | Custom SOQL condition to filter source records (see below) |
| **Date Range** | Only validate records created within the last N months |
| **Record Limit** | Limit records per object for quick sampling |

4. Click **OK** to start the validation.

### Source WHERE Clause

Enter any valid SOQL WHERE condition (without the `WHERE` keyword). Examples:

```
CreatedDate >= 2025-01-01T00:00:00Z AND CreatedDate < 2025-07-01T00:00:00Z
```

```
OCE__Status__c = 'Submitted' AND CreatedDate >= 2025-06-01T00:00:00Z
```

```
Id IN ('001xx000003DGbYAAW', '001xx000003DGbZAAW')
```

The WHERE clause is applied to the **source (Salesforce) query only**. It can be combined with Date Range and Record Limit — all conditions are joined with AND.

### Date Range Quick Buttons

Click **3M**, **6M**, **1Y**, **2Y**, **3Y**, or **All** to quickly set the date range.

### Record Limit Quick Buttons

Click **1K**, **5K**, **10K**, **50K**, or **All** to quickly set the record limit.

### Monitoring Progress

While a validation is running, the progress column shows real-time updates:

| Phase | What You See |
|---|---|
| Initializing | "Initializing validation run..." |
| Connecting | "Connecting to source & target systems..." |
| Fetching Source | "Fetching source records... 4,200 / 5,000 fetched ~12s left" |
| Fetching Target | "Fetching target records... 3,100 fetched (source: 5,000)" |
| Comparing | "Comparing records... 78% 3,900 / 5,000" |
| Done | Green "Done" tag |

The progress updates every 3 seconds via polling.

### Cancelling a Run

Click the **Cancel** button next to a running validation to stop it.

---

## 7. Understanding Validation Results

### Summary View

After a validation completes, click **View Results** to see the summary:

| Column | Description |
|---|---|
| **Source** | Source object name |
| **Target** | Target object name |
| **Source Count** | Number of source records fetched |
| **Target Count** | Number of target records fetched |
| **Matched** | Records found in target with all fields matching |
| **Mismatched** | Records found in target but with field differences |
| **Missing in Target** | Source records not found in target |
| **Match %** | Percentage of source records that fully match |

### Record Details

Click **Details** on a summary row to see individual record results.

**Filter by status** using the dropdown: Matched, Mismatched, or Missing in Target.

Each record row shows:

| Column | Description |
|---|---|
| **Match Key** | The match key value used to correlate source and target records |
| **Status** | `matched`, `mismatched`, or `missing in target` |
| **Summary** | Tag counts: e.g., "12 matched", "3 mismatched", "1 missing" |

### Expanding a Record

Click the expand arrow (▶) on any matched or mismatched record to see all field-level details:

**Issues section** (shown first for mismatched records):

| Column | Description |
|---|---|
| Status | `Mismatch` (values differ), `Missing in Target` (source has value, target is null), or `Extra in Target` |
| Source Field | Source field API name |
| Source Value | Value in source system |
| Target Field | Target field API name |
| Target Value | Value in target system |

**Matching Attributes section:**

Shows all fields where source and target values match, displayed in green.

Records marked "missing in target" cannot be expanded (there is no target data to compare).

---

## 8. Exporting Reports

### Summary Report

Click the **Export** button (download icon) next to a validation run to download the summary as a CSV file.

### Detail Report

In the record details view, click the download icon next to a summary row to export the detailed field-level comparison as a CSV.

You can filter by status before exporting — only the filtered records will be included.

---

## 9. Tips for Large Datasets

### Use Filters for Faster Validation

For objects with millions of records (e.g., `OCE__Call__c` with 1.4M records), always use filters:

1. **WHERE clause** — most precise control. Example: validate only records from a specific date range or status.
2. **Date Range** — quick way to limit by `CreatedDate` (e.g., last 12 months).
3. **Record Limit** — caps the number of records fetched per object (e.g., 5K for a quick sample).

**Recommended for demos:** Use a WHERE clause with a tight date range + 5K record limit. This typically completes in 1-2 minutes.

### Validation Logic

- The engine validates **source → target only**: it checks whether each source record exists in the target and whether field values match.
- Records in the target that don't exist in the source are **not reported** (this is intentional — the focus is on verifying migrated data).
- Invalid fields in the mapping (fields that don't exist in the source/target schema) are **automatically skipped** with a warning, rather than failing the entire validation.

### Match Keys Are Required

Without match keys, the engine cannot correlate source and target records. Ensure every object mapping has at least one match key configured (e.g., `Id → legacy_crm_id__v`).

### Re-import Mapping Sheet After Changes

If you update your mapping sheet, re-import it — the import replaces existing field mappings for each object mapping, so you always get the latest version.

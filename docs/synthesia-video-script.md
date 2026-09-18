# Migration Bridge — Synthesia Video Script

**Total Duration:** ~4–5 minutes
**Synthesia Avatar:** Professional presenter (e.g., "Anna" or "James")
**Tone:** Confident, clear, corporate-friendly
**Audience:** Roche leadership, project stakeholders, CRM migration teams

---

## FRAME 1 — Opening / Hook
**Duration:** 15 seconds
**Avatar:** Visible, center frame
**Background Video/Image:** Login page of Migration Bridge (the illustration with person + magnifying lens comparing data between two systems)

**Narration:**
> "When you migrate millions of CRM records from one system to another, how do you know everything landed correctly? Meet Migration Bridge — a purpose-built tool by Roche to validate, reconcile, and report on migrated data."

---

## FRAME 2 — The Problem
**Duration:** 20 seconds
**Avatar:** Visible, left side
**Background Video/Image:** Split screen — Salesforce logo on left, Veeva Vault logo on right, with a question mark in the middle. Or a simple slide showing: "5 million records. 200 fields. How many mismatches?"

**Narration:**
> "Roche is migrating CRM data from IQVIA OCE on Salesforce to Veeva Vault CRM as part of the AMW program. With millions of records across accounts, contacts, calls, and medical events — manual reconciliation is impossible. We needed an automated way to compare source and target data, detect mismatches, and generate actionable reports."

---

## FRAME 3 — What is Migration Bridge
**Duration:** 20 seconds
**Avatar:** Visible, right side
**Background Video/Image:** Screen recording — show the login page, then log in and land on the Projects dashboard

**Narration:**
> "Migration Bridge is a web-based data validation platform. It connects directly to your source and target CRM systems, pulls the data, compares it field by field, and tells you exactly what matches, what doesn't, and what's missing. It was built specifically for Roche's data migration reconciliation, reporting, and bug fixing."

---

## FRAME 4 — Setting Up Connections
**Duration:** 25 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording of the Connections page:
1. Click "New Connection"
2. Select "Salesforce" as system type
3. Fill in instance URL, username
4. Click save
5. Click "Test" → show success message
6. Repeat briefly for Veeva Vault connection

**Narration:**
> "Getting started is simple. You create connection profiles for your source and target systems. Here we're connecting to a Salesforce org and a Veeva Vault instance. Each connection is tested before use to make sure credentials and network access are working. Connections are encrypted and stored securely."

---

## FRAME 5 — Creating a Migration Project
**Duration:** 20 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording of the Projects page:
1. Click "New Project"
2. Enter project name and description
3. Select source connection (Salesforce)
4. Select target connection (Veeva Vault)
5. Click create
6. Click "Open" to enter the project

**Narration:**
> "Next, you create a migration project. A project links a source system to a target system. For example, Salesforce IQVIA OCE as the source and Veeva Vault CRM as the target. You can have multiple projects running simultaneously for different markets or migration waves."

---

## FRAME 6 — Object & Field Mapping
**Duration:** 30 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording inside a project:
1. Show the Object Mappings tab
2. Click "Add Mapping" — select source object (e.g., Account) and target object
3. Click "Auto-Map Fields" — show fields being matched automatically
4. Show the field mapping table with source field → target field
5. Show match keys configuration
6. Briefly show "Export Mapping" button

**Narration:**
> "Inside a project, you map objects from source to target. For example, the Account object in Salesforce maps to the Account object in Veeva Vault. The tool can auto-map fields using intelligent name matching — saving hours of manual work. You can also define match keys, which tell the system how to pair records between the two systems. For example, matching accounts by their external ID. Mappings can be exported and imported as spreadsheets for review with your team."

---

## FRAME 7 — Running Validation
**Duration:** 30 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording:
1. Click "Run Validation" on a mapped object
2. Show the validation running with progress indicator
3. Show results appearing — match percentage, record counts
4. Show the summary: matched records, mismatched records, missing in source, missing in target
5. Drill into mismatched records — show field-level comparison

**Narration:**
> "This is where the magic happens. When you run a validation, Migration Bridge pulls records from both systems, matches them using your defined keys, and compares every mapped field. You get a clear summary — how many records matched perfectly, how many have field-level mismatches, and how many are missing on either side. You can drill into any mismatch to see exactly which fields differ and what the values are on each side."

---

## FRAME 8 — Reporting & Export
**Duration:** 20 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording:
1. Show the validation summary with statistics
2. Click "Export Summary" — show Excel download
3. Open the Excel briefly showing the reconciliation report
4. Show mismatch details export

**Narration:**
> "Every validation run generates a detailed reconciliation report that you can export to Excel. These reports are ready to share with your migration team, market leads, or quality assurance. They show exactly what needs to be fixed before go-live — making bug fixing targeted and efficient."

---

## FRAME 9 — Data Cleanup
**Duration:** 20 seconds
**Avatar:** Small, bottom-right corner
**Background Video/Image:** Screen recording:
1. Show the Cleanup tab
2. Show the object hierarchy view
3. Show creating a cleanup job
4. Show cleanup job running with status

**Narration:**
> "Migration Bridge also supports data cleanup. When test data or incorrect records need to be removed from the target system, the cleanup engine handles it in the correct dependency order — deleting child records before parents — so you never hit referential integrity errors."

---

## FRAME 10 — Flexibility / Multi-System Support
**Duration:** 25 seconds
**Avatar:** Visible, center frame
**Background Video/Image:** A simple diagram/slide showing:
- Salesforce ↔ Veeva Vault (primary use case)
- Salesforce ↔ Salesforce
- Veeva CRM ↔ Veeva Vault
With arrows and check marks

**Narration:**
> "While we built Migration Bridge for the IQVIA OCE to Veeva Vault migration, the architecture is system-agnostic. It works equally well for Salesforce to Salesforce migrations, Veeva CRM to Veeva Vault, or any combination. If your team is migrating CRM data between any two supported systems, Migration Bridge can validate it."

---

## FRAME 11 — Scale & Performance
**Duration:** 15 seconds
**Avatar:** Visible, left side
**Background Video/Image:** A slide or animation showing: "5M+ records validated" / "200+ fields compared" / "Bulk API for speed" / "Background processing for large datasets"

**Narration:**
> "Migration Bridge is built to handle millions of records. It uses bulk APIs for data extraction, background processing for large validation runs, and streaming comparisons so memory is never a bottleneck. Whether you're validating five thousand records or five million, it scales."

---

## FRAME 12 — Closing / Call to Action
**Duration:** 15 seconds
**Avatar:** Visible, center frame
**Background Video/Image:** Login page of Migration Bridge with the illustration visible

**Narration:**
> "Migration Bridge — built by Roche, for Roche. Ensuring every record is accounted for, every field is correct, and every migration is validated before go-live. If your team is involved in CRM data migration, reach out to get access."

---

## FRAME 13 — End Card
**Duration:** 5 seconds
**Avatar:** None
**Background Image:** Roche-branded slide with:
- **Migration Bridge** (logo/title)
- **Post-Migration Data Validation & Reconciliation Platform**
- Contact: [your email]
- Team: [your team name]

**Narration:** None (background music only)

---

# Screen Recordings Needed

Record these from the live app to use as background videos in Synthesia:

| # | What to Record | Duration | Notes |
|---|---------------|----------|-------|
| 1 | Login page (just show it, don't log in) | 10s | Show the illustration and branding |
| 2 | Log in → land on Projects page | 10s | Show the dashboard |
| 3 | Connections page → create new → test | 30s | Show both Salesforce and Veeva |
| 4 | Create a new project | 15s | Fill form, select connections |
| 5 | Inside project → Object Mappings tab | 10s | Show existing mappings |
| 6 | Add mapping → Auto-map fields | 20s | Show the auto-mapping in action |
| 7 | Field mapping table + match keys | 15s | Scroll through fields |
| 8 | Run validation → show progress | 15s | Show the spinner/progress |
| 9 | Validation results → summary | 15s | Show match %, counts |
| 10 | Drill into mismatches | 15s | Show field-level diff |
| 11 | Export to Excel | 10s | Click export, show download |
| 12 | Cleanup tab → hierarchy → job | 15s | Show cleanup flow |
| 13 | Login page again for closing | 5s | Same as #1 |

# Synthesia Setup Tips

1. **Create a new project** in Synthesia
2. **Add one scene per frame** (13 scenes total)
3. **Paste the narration text** into each scene's script box
4. **Upload the screen recordings** as background videos for each scene
5. **Choose avatar position** as noted (center, left, right, or small corner)
6. For slides (Frames 2, 10, 11, 13) — create simple PowerPoint slides and upload as images
7. **Add background music** — subtle, corporate-friendly
8. **Export as 1080p MP4**

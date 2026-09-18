# ServiceNow Infrastructure Request — Migration Bridge

Copy the sections below into your ServiceNow ticket.

---

## Short Description

Linux server provisioning for Migration Bridge — CRM Post-Migration Data Validation Platform

## Category

Infrastructure / Server Provisioning

## Priority

High

## Description

### Summary

We need a **Linux server** to host **Migration Bridge**, an internal web application that validates and compares migrated CRM data between Salesforce IQVIA OCE and Veeva Vault CRM. The application must be always-on and capable of processing millions of records.

### Application Overview

A web-based data validation tool with:
- **Backend:** Python REST API for data validation logic and CRM integration
- **Frontend:** Web UI for managing connections, projects, and viewing validation results
- **Database:** PostgreSQL for storing connection profiles, projects, and validation results
- **Background Processing:** Async task queue for large dataset comparisons

### Server Requirements

| Requirement | Specification |
|-------------|--------------|
| **OS** | Linux (Ubuntu 22.04 LTS or RHEL 8/9) |
| **CPU** | 8 vCPUs minimum |
| **RAM** | 32 GB minimum |
| **Storage** | 500 GB SSD (for database + application data) |
| **Availability** | Always-on, 24/7 |
| **Environment** | Production |

### Network Requirements

| Requirement | Detail |
|-------------|--------|
| **Inbound** | HTTPS (port 443) — accessible within Roche internal network |
| **Domain** | `migration-bridge.[your-domain].roche.com` (or as per convention) |
| **SSL/TLS** | Managed certificate for HTTPS |
| **Outbound access** | Salesforce API (`*.salesforce.com`, `*.force.com`) |
| **Outbound access** | Veeva Vault API (`*.veevavault.com`) |
| **IP whitelisting** | Server's outbound IP must be whitelisted in Salesforce Network Access settings |

### Data Volume

- 1M–5M records per validation run
- 50–200 fields per object type
- Multiple concurrent validation projects
- Results stored for audit trail

### Software to be Installed

- Python 3.12
- PostgreSQL 16
- Redis 7
- Nginx (reverse proxy)

### Team / Contacts

- **Requestor:** [Your Name]
- **Team:** [Your Team Name]
- **Cost Center:** [Your Cost Center]
- **Application Owner:** [Owner Name]
- **Technical Contact:** [Your Email]

---

## Checklist Before Submitting

- [ ] Fill in bracketed `[...]` placeholders
- [ ] Confirm desired domain/URL with your team
- [ ] Confirm cost center for billing

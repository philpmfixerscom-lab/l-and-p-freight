# Expo SQLite Schema Synchronization
**Lawson Freight Platform – Driver Companion App Research & Starter**

## Goal
Enable a future React Native + Expo mobile app to work offline using the exact same data model as the Streamlit dashboard (`lawson_freight.db` / `lp_dispatch.db`).

## Recommended Approach
Mirror the existing SQLite tables so both platforms share the same schema. Use `expo-sqlite` for local storage and a simple export/import or future API for sync.

### Core Tables (Exact Match)

```sql
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT,
  address TEXT,
  status TEXT DEFAULT 'New',
  last_contact TEXT,
  notes TEXT,
  contract_signed TEXT,
  insurance_verified INTEGER DEFAULT 0,
  mc_on_file INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER,
  load_date TEXT,
  commodity TEXT,
  origin TEXT,
  destination TEXT,
  weight_tons REAL,
  rate_per_ton REAL,
  total_amount REAL,
  status TEXT DEFAULT 'Logged',
  bol_number TEXT,
  notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (lead_id) REFERENCES leads (id)
);

CREATE TABLE IF NOT EXISTS contracts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER,
  agreement_type TEXT,
  signed_date TEXT,
  version TEXT DEFAULT 'v1.0',
  file_name TEXT,
  terms_summary TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (lead_id) REFERENCES leads (id)
);

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Expo Implementation Notes

- Primary library: **expo-sqlite** (official, stable)
- Starter code lives in `mobile-expo-starter/db.ts` (copy into an Expo app when ready)
- Use the same column names and types so data can be exported/imported between Streamlit and mobile
- For v1 offline support: store loads + checklist state locally, push status updates when online
- Avoid complex sync engines (WatermelonDB, etc.) until multi-device conflict resolution is required
- `schema_version` supports future migrations

> **Live Streamlit mapping:** production tables today use `company` (not `name`) on leads and `total_revenue` (not `total_amount`) on loads in `lp_helpers/database.py`. Map or migrate at export/import time — do not change the Streamlit schema for mobile.

## Decision
Do not start full React Native development yet.
Priority remains the Streamlit command center until real loads are consistently booked.

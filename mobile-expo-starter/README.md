# Lawson Freight — Expo SQLite Starter

Ready-to-copy offline database layer for a future **driver companion** app.

**Do not start full React Native development yet.** Streamlit remains the command center until loads are booked daily.

## What’s here

| File | Purpose |
|------|---------|
| `db.ts` | `expo-sqlite` open/schema, `Lead`/`Load` types, CRUD helpers, JSON export/import |
| `../docs/mobile-offline-research.md` | Schema research + product decision |

## When you’re ready

```bash
# From a new Expo app (example)
npx create-expo-app lawson-driver
cd lawson-driver
npx expo install expo-sqlite

# Copy the starter
cp /path/to/lawson-freight-platform/mobile-expo-starter/db.ts ./src/db.ts
```

### Minimal usage

```ts
import {
  openDatabase,
  getLeads,
  getLoads,
  updateLoadStatus,
  exportAllDataAsJson,
  importFromJson,
} from "./db";

await openDatabase();
const loads = await getLoads();
await updateLoadStatus(loads[0].id, "In Transit");

const json = await exportAllDataAsJson();
// share json file / upload later
await importFromJson(json);
```

## Sync strategy (v1)

1. Streamlit exports loads/leads as JSON (map `company` → `name`, `total_revenue` → `total_amount`).
2. Driver app imports via `importFromJson`.
3. Cab updates status offline with `updateLoadStatus`.
4. Later: push status deltas when online (simple API or file re-export).

No WatermelonDB / multi-device CRDT until conflict resolution is required.

## Rules

- Do not change Streamlit legal PDFs, BOL terms, or production schema for this starter.
- Prefer matching live `lp_helpers/database.py` columns at the export mapper layer.

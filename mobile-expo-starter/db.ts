/**
 * Lawson Freight — Expo SQLite offline layer (starter)
 *
 * Copy this file into an Expo / React Native app when building the driver companion.
 * Mirrors the research schema in docs/mobile-offline-research.md.
 *
 * Install: npx expo install expo-sqlite
 *
 * NOTE: Live Streamlit DB uses company / total_revenue in places.
 * Map at import/export boundaries if syncing with lp_dispatch.db.
 */

import * as SQLite from "expo-sqlite";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type LeadStatus =
  | "New"
  | "Called Today"
  | "Contacted"
  | "Quoted"
  | "Hot"
  | "Active"
  | "Negotiating"
  | "Closed"
  | string;

export type LoadStatus =
  | "Logged"
  | "Potential"
  | "Quoted"
  | "Booked"
  | "Dispatched"
  | "In Transit"
  | "Delivered"
  | "Paid"
  | string;

export interface Lead {
  id: number;
  name: string;
  phone: string | null;
  address: string | null;
  status: LeadStatus;
  last_contact: string | null;
  notes: string | null;
  contract_signed: string | null;
  insurance_verified: number;
  mc_on_file: number;
  created_at: string | null;
}

export interface Load {
  id: number;
  lead_id: number | null;
  load_date: string | null;
  commodity: string | null;
  origin: string | null;
  destination: string | null;
  weight_tons: number | null;
  rate_per_ton: number | null;
  total_amount: number | null;
  status: LoadStatus;
  bol_number: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface Contract {
  id: number;
  lead_id: number | null;
  agreement_type: string | null;
  signed_date: string | null;
  version: string | null;
  file_name: string | null;
  terms_summary: string | null;
  created_at: string | null;
}

export interface ExportBundle {
  schema_version: number;
  exported_at: string;
  leads: Lead[];
  loads: Load[];
  contracts: Contract[];
}

const DB_NAME = "lawson_freight.db";
const SCHEMA_VERSION = 1;

let dbPromise: Promise<SQLite.SQLiteDatabase> | null = null;

// ---------------------------------------------------------------------------
// Open + schema
// ---------------------------------------------------------------------------

const SCHEMA_SQL = `
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
`;

/**
 * Open (or reuse) the local SQLite database and ensure schema exists.
 */
export async function openDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const db = await SQLite.openDatabaseAsync(DB_NAME);
      await db.execAsync("PRAGMA foreign_keys = ON;");
      await db.execAsync(SCHEMA_SQL);

      const row = await db.getFirstAsync<{ version: number }>(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
      );
      if (!row) {
        await db.runAsync(
          "INSERT INTO schema_version (version) VALUES (?)",
          SCHEMA_VERSION
        );
      }
      // Future: run migrations when row.version < SCHEMA_VERSION

      return db;
    })();
  }
  return dbPromise;
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

export async function getLeads(): Promise<Lead[]> {
  const db = await openDatabase();
  return db.getAllAsync<Lead>(
    "SELECT * FROM leads ORDER BY last_contact DESC, id DESC"
  );
}

export async function getLoads(): Promise<Load[]> {
  const db = await openDatabase();
  return db.getAllAsync<Load>(
    "SELECT * FROM loads ORDER BY load_date DESC, id DESC"
  );
}

export async function getLoadById(id: number): Promise<Load | null> {
  const db = await openDatabase();
  const row = await db.getFirstAsync<Load>(
    "SELECT * FROM loads WHERE id = ?",
    id
  );
  return row ?? null;
}

export async function getContracts(): Promise<Contract[]> {
  const db = await openDatabase();
  return db.getAllAsync<Contract>(
    "SELECT * FROM contracts ORDER BY signed_date DESC, id DESC"
  );
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

/**
 * Update a load status from the cab (e.g. Booked → In Transit → Delivered).
 */
export async function updateLoadStatus(
  loadId: number,
  status: LoadStatus
): Promise<void> {
  const db = await openDatabase();
  await db.runAsync("UPDATE loads SET status = ? WHERE id = ?", status, loadId);
}

export async function upsertLead(
  lead: Omit<Lead, "id" | "created_at"> & { id?: number }
): Promise<number> {
  const db = await openDatabase();
  if (lead.id != null) {
    await db.runAsync(
      `UPDATE leads SET
        name = ?, phone = ?, address = ?, status = ?, last_contact = ?,
        notes = ?, contract_signed = ?, insurance_verified = ?, mc_on_file = ?
       WHERE id = ?`,
      lead.name,
      lead.phone,
      lead.address,
      lead.status,
      lead.last_contact,
      lead.notes,
      lead.contract_signed,
      lead.insurance_verified ?? 0,
      lead.mc_on_file ?? 0,
      lead.id
    );
    return lead.id;
  }
  const result = await db.runAsync(
    `INSERT INTO leads (
      name, phone, address, status, last_contact, notes,
      contract_signed, insurance_verified, mc_on_file
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    lead.name,
    lead.phone,
    lead.address,
    lead.status ?? "New",
    lead.last_contact,
    lead.notes,
    lead.contract_signed,
    lead.insurance_verified ?? 0,
    lead.mc_on_file ?? 0
  );
  return Number(result.lastInsertRowId);
}

// ---------------------------------------------------------------------------
// Simple offline sync (JSON export / import)
// ---------------------------------------------------------------------------

/**
 * Export all local tables as a JSON-serializable bundle for file transfer
 * or a future upload API.
 */
export async function exportAllDataAsJson(): Promise<string> {
  const [leads, loads, contracts] = await Promise.all([
    getLeads(),
    getLoads(),
    getContracts(),
  ]);
  const bundle: ExportBundle = {
    schema_version: SCHEMA_VERSION,
    exported_at: new Date().toISOString(),
    leads,
    loads,
    contracts,
  };
  return JSON.stringify(bundle, null, 2);
}

/**
 * Import a JSON bundle produced by exportAllDataAsJson (or a Streamlit export
 * mapped to this schema). Replaces local rows for matching ids (upsert by id).
 */
export async function importFromJson(json: string): Promise<{
  leads: number;
  loads: number;
  contracts: number;
}> {
  const parsed = JSON.parse(json) as ExportBundle;
  if (!parsed || !Array.isArray(parsed.leads) || !Array.isArray(parsed.loads)) {
    throw new Error("Invalid Lawson export JSON: missing leads/loads arrays");
  }

  const db = await openDatabase();
  let leadCount = 0;
  let loadCount = 0;
  let contractCount = 0;

  await db.withTransactionAsync(async () => {
    for (const lead of parsed.leads) {
      await db.runAsync(
        `INSERT INTO leads (
          id, name, phone, address, status, last_contact, notes,
          contract_signed, insurance_verified, mc_on_file, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name = excluded.name,
          phone = excluded.phone,
          address = excluded.address,
          status = excluded.status,
          last_contact = excluded.last_contact,
          notes = excluded.notes,
          contract_signed = excluded.contract_signed,
          insurance_verified = excluded.insurance_verified,
          mc_on_file = excluded.mc_on_file`,
        lead.id,
        lead.name,
        lead.phone ?? null,
        lead.address ?? null,
        lead.status ?? "New",
        lead.last_contact ?? null,
        lead.notes ?? null,
        lead.contract_signed ?? null,
        lead.insurance_verified ?? 0,
        lead.mc_on_file ?? 0,
        lead.created_at ?? null
      );
      leadCount += 1;
    }

    for (const load of parsed.loads) {
      await db.runAsync(
        `INSERT INTO loads (
          id, lead_id, load_date, commodity, origin, destination,
          weight_tons, rate_per_ton, total_amount, status, bol_number, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          lead_id = excluded.lead_id,
          load_date = excluded.load_date,
          commodity = excluded.commodity,
          origin = excluded.origin,
          destination = excluded.destination,
          weight_tons = excluded.weight_tons,
          rate_per_ton = excluded.rate_per_ton,
          total_amount = excluded.total_amount,
          status = excluded.status,
          bol_number = excluded.bol_number,
          notes = excluded.notes`,
        load.id,
        load.lead_id ?? null,
        load.load_date ?? null,
        load.commodity ?? null,
        load.origin ?? null,
        load.destination ?? null,
        load.weight_tons ?? null,
        load.rate_per_ton ?? null,
        load.total_amount ?? null,
        load.status ?? "Logged",
        load.bol_number ?? null,
        load.notes ?? null,
        load.created_at ?? null
      );
      loadCount += 1;
    }

    for (const contract of parsed.contracts ?? []) {
      await db.runAsync(
        `INSERT INTO contracts (
          id, lead_id, agreement_type, signed_date, version, file_name, terms_summary, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          lead_id = excluded.lead_id,
          agreement_type = excluded.agreement_type,
          signed_date = excluded.signed_date,
          version = excluded.version,
          file_name = excluded.file_name,
          terms_summary = excluded.terms_summary`,
        contract.id,
        contract.lead_id ?? null,
        contract.agreement_type ?? null,
        contract.signed_date ?? null,
        contract.version ?? "v1.0",
        contract.file_name ?? null,
        contract.terms_summary ?? null,
        contract.created_at ?? null
      );
      contractCount += 1;
    }
  });

  return { leads: leadCount, loads: loadCount, contracts: contractCount };
}

/**
 * Map a Streamlit-style lead row (company, etc.) into the mobile Lead shape.
 */
export function mapStreamlitLeadToMobile(row: Record<string, unknown>): Omit<
  Lead,
  "id"
> & { id?: number } {
  return {
    id: typeof row.id === "number" ? row.id : undefined,
    name: String(row.name ?? row.company ?? "Unknown"),
    phone: (row.phone as string) ?? null,
    address: (row.address as string) ?? (row.lane_notes as string) ?? null,
    status: String(row.status ?? "New"),
    last_contact: (row.last_contact as string) ?? null,
    notes: (row.notes as string) ?? null,
    contract_signed: (row.contract_signed as string) ?? null,
    insurance_verified: Number(row.insurance_verified ?? 0),
    mc_on_file: Number(row.mc_on_file ?? 0),
    created_at: (row.created_at as string) ?? null,
  };
}

/**
 * Map a Streamlit-style load row (total_revenue, pickup_date, etc.) into Load.
 */
export function mapStreamlitLoadToMobile(row: Record<string, unknown>): Omit<
  Load,
  "id"
> & { id?: number } {
  const amount =
    row.total_amount != null
      ? Number(row.total_amount)
      : row.total_revenue != null
        ? Number(row.total_revenue)
        : null;
  return {
    id: typeof row.id === "number" ? row.id : undefined,
    lead_id: row.lead_id != null ? Number(row.lead_id) : null,
    load_date:
      (row.load_date as string) ??
      (row.pickup_date as string) ??
      null,
    commodity: (row.commodity as string) ?? null,
    origin: (row.origin as string) ?? null,
    destination: (row.destination as string) ?? null,
    weight_tons: row.weight_tons != null ? Number(row.weight_tons) : null,
    rate_per_ton: row.rate_per_ton != null ? Number(row.rate_per_ton) : null,
    total_amount: amount,
    status: String(row.status ?? "Logged"),
    bol_number: (row.bol_number as string) ?? null,
    notes: (row.notes as string) ?? null,
    created_at: (row.created_at as string) ?? null,
  };
}

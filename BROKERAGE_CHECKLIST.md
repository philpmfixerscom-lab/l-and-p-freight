# L & P Freight — Brokerage Build Checklist

> Source: Lawson's platform notes ("build brokerage and do it quietly — truckers").
> This is an operational/legal tracker, not code. Update statuses as items complete.

## Authority & Legal Formation

| # | Item | Why it's needed | Status | Notes |
|---|------|-----------------|--------|-------|
| 1 | **LLC formation** | Legal entity + liability protection | ☐ Not started | File with NC Secretary of State |
| 2 | **EIN** (Employer ID Number) | Banking, taxes, hiring | ☐ Not started | Free via IRS after LLC |
| 3 | **USDOT number** | Required to operate CMVs interstate | ☐ Not started | FMCSA registration |
| 4 | **MC number** (Operating Authority) | Required to broker/carry freight for hire | ☐ Not started | FMCSA — "Broker of Property" authority for brokerage |
| 5 | **EMC / carrier authority** | Motor carrier authority (if hauling own) | ☐ Not started | Confirm broker vs carrier vs both |
| 6 | **BOC-3 filing** | Process agent for all states | ☐ Not started | Required before authority activates |
| 7 | **Unified Carrier Registration (UCR)** | Annual interstate registration | ☐ Not started | Renews annually |

## Insurance & Bonds

| # | Item | Why it's needed | Status | Notes |
|---|------|-----------------|--------|-------|
| 8 | **Liability insurance** | FMCSA minimum + shipper requirement | ☐ Not started | Auto liability ($750k–$1M typical) |
| 9 | **Cargo insurance** | Covers freight (feldspar/mica/aggregate) | ☐ Not started | Confirm bulk/mineral coverage |
| 10 | **BMC-84 broker surety bond ($75k)** | Required for brokerage authority | ☐ Not started | Or BMC-85 trust |
| 11 | **Contingent cargo / broker liability** | Protects brokerage vs carrier failures | ☐ Not started | Recommended for brokered loads |

## "Do it quietly" — brokerage go-to-market

- Build the carrier network first (owner-operators in the Spruce Pine → GA corridor).
- Use the existing Leads CRM + Rate Calculator to quote and book brokered loads.
- Keep carrier and shipper rates separate in the platform (margin = shipper rate − carrier pay).

## Market Intelligence (from Lawson's notes — verify before relying on)

Production reportedly weak; several plants said to be closing:

- **Closing (reported):** Redhill, Crystal plant, Minpro
- **Remaining / priority shippers:** Schoolhouse, **Covia**, **Sibelco**

> Action: prioritize Covia + Sibelco relationships (already seeded as hot leads in the CRM);
> treat the closures as a chance to consolidate lanes and lock volume with the survivors.

## Platform readiness for brokerage (already built)

- ✅ Leads CRM with follow-up scheduling (`app.py` → Leads tab)
- ✅ Rate Calculator with deadhead + margin (`app.py` → Rate Calculator)
- ✅ Customer Portal with PO / multi-load scheduling + live billing (`app.py` → Customer Portal)
- ✅ Driver pay on **actual miles driven** (`lp_helpers/pay_engine.py`)
- ✅ PDF BOL + settlement statements
- ☐ Separate carrier-pay vs shipper-rate ledger for brokered margin (future)

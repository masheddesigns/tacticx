# TacticX Phase 24 — Controlled Current-Season Operations & Activation Guide

## 1. Overview & Operational Principles

TacticX Phase 24 introduces controlled activation for current-season match data. The system enforces three non-negotiable operational principles:

1. **Qualification Precedes Activation (`QUALIFIED != ACTIVE`)**: Passing provider qualification verifies technical compatibility and schema integrity. It does not automatically begin ingesting live data.
2. **Explicit Operator Authorization**: Transitioning a competition to `ACTIVE` requires an explicit, audited operational invocation with recorded operator identity and rationale.
3. **Temporal Safety & Immutability**: All prediction outputs are content-addressed and time-stamped. Kickoff locks guarantee that match status transitions (e.g. `FINISHED`) never mutate pre-match prediction snapshots.

---

## 2. Activation State Machine

```text
    ┌───────────────┐
    │  UNAVAILABLE  │◄─────────────────────────┐
    └───────┬───────┘                          │
            │ Candidate detected               │
            ▼                                  │
    ┌───────────────┐                          │
    │   DISCOVERY   │                          │
    └───────┬───────┘                          │
            │ Schema probe                     │
            ▼                                  │
    ┌───────────────┐                          │
    │    PROBING    │                          │
    └───────┬───────┘                          │
            │ Bounded qualification probe      │
            ▼                                  │
    ┌───────────────┐                          │
    │  QUALIFYING   │                          │
    └───────┬───────┘                          │
            │ Checks pass                      │
            ▼                                  │
    ┌───────────────┐                          │
    │   QUALIFIED   │                          │
    └───────┬───────┘                          │
            │ Explicit Operator Action         │
            ▼                                  │
    ┌───────────────┐  Data degradation        │
    │    ACTIVE     │─────────────────────►┌───┴──────────┐
    └───────┬───────┘                      │   DEGRADED   │
            │ Operator revocation          └───┬──────────┘
            ▼                                  │
    ┌───────────────┐                          │
    │    REVOKED    │◄─────────────────────────┘
    └───────────────┘
```

---

## 3. Decision Gate (`can_activate_current_season`)

Before activating any provider for a competition and season, the pure decision function evaluates:

| Gate | Check | Rejection Reason |
| :--- | :--- | :--- |
| **League Support** | Target league is in `('EPL', 'LA_LIGA', 'SERIE_A', 'BUNDESLIGA', 'LIGUE_1')` | `unsupported_competition` |
| **Qualification** | Latest `SourceQualification` status is `qualified` or `partially_qualified` | `provider_not_qualified` |
| **Fixture Count** | `fixture_count > 0` | `no_current_season_fixtures_available` |
| **Timestamps** | All fixtures have valid ISO kickoff timestamps with timezone | `fixtures_missing_valid_kickoff_timestamps` |
| **Identity Resolvability** | Zero critical unresolved conflicts in `ReconciliationConflict` for target competition | `critical_unresolved_reconciliation_conflicts` |
| **Evidence Freshness** | Qualification retrieved within the last 7 days ($168\text{ hours}$) | `qualification_evidence_is_stale` |
| **Historical Context** | At least 5 finished historical matches exist in DB for competition feature baselines | `insufficient_historical_context` |

---

## 4. Command-Line Reference

### Audit Readiness
```bash
./scripts/tacticx current-season readiness
```
Output:
```text
Current Season Readiness [2026/27] (as of 2026-09-19T11:26:17.770402+00:00)
Competition        Provider         Fixtures   Qual Status    Activation     Eligible   Blocking Reasons
---------------------------------------------------------------------------------------------------------
EPL                api_football     N/A        unqualified    UNAVAILABLE    NO         no_qualification_evidence_for_api_football
LA_LIGA            api_football     N/A        unqualified    UNAVAILABLE    NO         no_qualification_evidence_for_api_football
SERIE_A            api_football     N/A        unqualified    UNAVAILABLE    NO         no_qualification_evidence_for_api_football
BUNDESLIGA         api_football     N/A        unqualified    UNAVAILABLE    NO         no_qualification_evidence_for_api_football
LIGUE_1            api_football     N/A        unqualified    UNAVAILABLE    NO         no_qualification_evidence_for_api_football
---------------------------------------------------------------------------------------------------------
Total: 5 | Active: 0 | Qualified: 0 | Unavailable: 5
```

### Check Activation Eligibility
```bash
./scripts/tacticx current-season can-activate --competition EPL --source api_football
```

### Activate Competition
```bash
# Normal activation (fails if ineligible)
./scripts/tacticx current-season activate --competition EPL --source api_football --actor "lead_sre" --reason "season opening"

# Force activation override (for testing or staging verification)
./scripts/tacticx current-season activate --competition EPL --source api_football --force --actor "lead_sre" --reason "staging test"
```

---

## 5. Scheduler Integration & Dormancy Guarantee

The background acquisition scheduler (`execute_fixture_refresh`) checks local activation state before performing any operations:
```python
if act_state != ActivationState.ACTIVE.value:
    outcome["sources"][name] = {
        "status": "skipped",
        "reason": f"source '{name}' is {act_state} (only ACTIVE sources trigger acquisition)"
    }
    continue
```
This guarantees:
- Zero external HTTP requests when sources are not active.
- Zero quota consumption during provider unavailability.
- Clean `skipped` status in the scheduler audit log without error alerts or failed jobs.

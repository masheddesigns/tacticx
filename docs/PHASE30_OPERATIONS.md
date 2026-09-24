# Phase 30 Operations Guide

All commands are explicit. Nothing here auto-promotes, auto-rolls back,
or modifies history.

## CLI (`tacticx model ...`)

Requires a database (`DATABASE_URL`). Every production-changing action
needs explicit flags; activation/rollback additionally require `--actor`.

```
tacticx model registry                      # role bindings
tacticx model champion                      # active champion view
tacticx model validate --artifact ART [--experiment EXP] [--actor NAME]
tacticx model validation --validation VAL
tacticx model promotion-request --artifact ART --validation VAL [--mode SHADOW|CANARY|PRODUCTION] [--actor NAME] [--reason TXT]
tacticx model approve --request REQ --actor NAME [--reason TXT]
tacticx model reject --request REQ --actor NAME [--reason TXT]
tacticx model shadow-start --artifact CHALLENGER --champion CHAMPION [--actor NAME]
tacticx model canary-activate --artifact ART [--actor NAME]
tacticx model production-activate --artifact ART --expected-champion CHAMP [--actor NAME] [--reason TXT]
tacticx model rollback --artifact TARGET --actor NAME [--reason TXT]
tacticx model audit [--artifact ART]
```

## Canonical happy path

1. Phase 29: register candidate → build dataset → run experiment.
2. `model validate --artifact ART` (links latest experiment automatically).
3. `model promotion-request --artifact ART --validation VAL --actor NAME`.
4. `model approve --request REQ --actor HUMAN`.
5. `model shadow-start --artifact ART --champion CHAMP`; generate pairs
   (API `shadow/pair` per match/cutoff; ≥10 for canary evidence).
6. `model canary-activate --artifact ART`.
7. `model production-activate --artifact ART --expected-champion CHAMP --actor HUMAN`.
8. If needed: `model rollback --artifact PRIOR --actor HUMAN`.

## Safety rules

- Never pass another operator's name as `--actor`.
- Activation with a stale `--expected-champion` fails safely; re-read
  `model champion` and decide deliberately.
- Rollback targets must be prior champions; verify via `model audit`.
- Shadow pairs never affect production snapshots — if production
  predictions change unexpectedly, stop and investigate; do not proceed.
- `model_registry`/`model_artifacts` rows are append-only by convention;
  fix mistakes with new governance operations, never SQL UPDATEs.

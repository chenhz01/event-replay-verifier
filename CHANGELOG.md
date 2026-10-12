# Changelog

## v0.1.1 — 2026-10-12
- Documentation layer completed: README (Problem / How it works / Quickstart / why-not-X anchored on cuda-event, zymi-core, CluxMate with layering-inversion framing / Minimal Fallback / Trade-offs / Limits / FAQ), ALIGNMENT.md 16-item audit, LICENSE (MIT, "zhengming contributors").
- Self-test re-verified green, no code changes needed this round: `python self_test.py` → `SUMMARY: PASS 55/55`.

## v0.1.0 — 2026-10-11
- Initial implementation: JSONL/array stream loading with line-numbered errors, anomaly scan (out_of_order / duplicate / missing / malformed with bool-seq rejection), canonical projection (first-occurrence dedup, seq sort, type counts, SHA-256 state_hash), replay_check with N passes plus a reordered-input projection for order-independence, CLI (`--json`, `--strict` exit 1, exit 2 on load failure).
- Self-test suite (functional / error / extreme-edge tiers).

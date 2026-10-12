# event-replay-verifier

event-replay-verifier audits a serialized event stream for replay determinism: out-of-order, duplicate, and missing sequence numbers, plus malformed events, and verifies that a canonical projection of the stream is order-independent. It sits *above* event-sourcing frameworks — it audits the log you exported, it is not a store or a bus. Confidence: High (≥80%) for the detection classes, per the 55-check suite.

## Problem

Event-sourced systems break in boring ways that only show up on replay: a producer crashed mid-batch and left a gap in sequence numbers, a retry duplicated an event, a partition reorder scrambled arrival order, or a malformed record snuck into the log. Everything *looks* fine until you rebuild state from the stream and get a different answer than production had. What is needed is a deterministic, offline check of the stream itself.

## How it works

1. **Load** — JSONL or JSON-array file; per-line JSON errors carry line numbers.
2. **Scan** (`analyze`) — for each event: must be an object with an integer `seq` (bools rejected) and a non-empty `type`. Detects:
   - `out_of_order` — a seq lower than its predecessor's;
   - `duplicate` — a seq seen before (with first-seen index);
   - `missing` — seqs absent between the min and max observed;
   - `malformed` — non-object events, missing/non-integer seq, missing type.
3. **Replay check** (`replay_check`) — folds the stream into a canonical projection (dedup keeping first occurrence, sort by seq, `last_seq`/`event_count`/`type_counts`/SHA-256 `state_hash`), replays it N times, adds a projection from a canonically *reordered* input, and reports `deterministic: true` only if all projections match.
4. **CLI contract** — `--strict` exits 1 on any issue; `--json` gives the full report.

## Quickstart (~3 min)

```bash
# step 1: audit a stream (~1 s)
python event_replay_verifier.py events.jsonl
# step 2: CI gate — fail on any issue
python event_replay_verifier.py events.jsonl --strict --json
# full suite (~3 s)
python self_test.py   # SUMMARY: PASS 55/55 [Measured]
```

Library use: `analyze(events)` → `(issues, stats)`; `replay_check(events, passes=3)` → full report.

## Why not X? (as of 2026-10-12)

- **Lucineer/cuda-event** (2★) — "Event system — pub/sub, event sourcing, replay, dead letter queue (Rust)". A *framework* that produces and replays events; the layering is inverted: it owns the store, so it cannot be pointed at an exported log from any other system. This repo audits streams from anywhere, in stdlib Python.
- **metravod/zymi-core** (10★) — "The auditable MCP backend for agents — tools as declarative YAML pipelines: event-sourced, replayable, approva…". Auditability is a property of its own pipeline runtime; it does not verify an arbitrary stream's sequence hygiene. This repo is the standalone checker you run against *any* event log.
- **r1c7/CluxMate** (145★) — "AI coding agent with one Python core and three front-ends". Listed as an adjacent consumer of replayability; an agent runtime, not a stream auditor — included here to delimit the search space, not as a rival.

## Minimal Fallback (PLAN B)

No Python: `jq -s 'map(.seq) | length - unique | length' events.jsonl` counts duplicate seqs, and `jq -s 'map(.seq) | min, max, (unique | length)' events.jsonl` exposes gaps when the span minus the unique count is nonzero. You lose malformed-event detection, order-independence proof, and the state hash.

## Design Trade-offs

Priority order: **order-independence of the verdict > coverage of anomaly classes > zero-dependency > throughput**. The determinism claim is tested, not asserted: the projection is recomputed from a canonically reordered copy of the input and must match — catching projection bugs, not just stream bugs. Duplicate handling keeps the *first* occurrence (deterministic, matches at-least-once delivery intuition) rather than last or merged. Missing-seq detection is bounded by min/max observed: it never invents expectations about seq 0 or negative ranges, because a verifier that guesses the intended range flags phantom gaps.

## Limits & Second-order Effects

- `state_hash` hashes seq/type/payload of the deduplicated, sorted stream — deterministic, but "deterministic" ≠ "correct": a wrong-but-consistent projection still reports true.
- Payloads are hashed as serialized JSON; two logically equal payloads with different key order hash differently (payload-level canonicalization is seq/type-level only).
- Gaps outside the observed min/max (e.g. stream truncated at the tail) are invisible by construction.
- Second-order: teams treat `deterministic: true` as "replay is safe" and skip rebuilding rehearsal — determinism here means *this checker's projection* is stable, not that your consumer logic is. Keep a real replay drill.
- Strict-mode exit 1 can quietly get piped around in CI scripts that ignore exit codes; wire it as a real gate or it becomes a log line nobody reads.

## FAQ

**Does it fix the stream?** No — read-only by design; it reports issues with indices and details so *you* decide on repairs.

**Why deduplicate keeping the first occurrence?** At-least-once delivery systems deliver retries after originals on the wire far more often than before them; first-occurrence matches the intended state in the common case.

### When NOT to use this tool?

- Your framework already guarantees ordered, exactly-once delivery with its own verification — double-checking adds nothing.
- You need a distributed log health monitor (Kafka lag, consumer offsets) — this audits a *file*, not a live cluster.
- Your events have no sequence numbers — nothing to verify; the tool reports everything malformed.
- You need semantic replay validation (business invariants on state) — this checks structure, not meaning.

## License

MIT — see `LICENSE`. Contact: hcac4735@agent.qq.com

---

[Core Assumptions]
- Streams carry monotonically intended integer `seq` values and a `type` per event; anything else is malformed by definition.
- Duplicates resolve to the first occurrence (at-least-once delivery intuition).
- The intended sequence range is exactly [min observed, max observed]; nothing outside it can be declared missing.
- Projection determinism must be *tested* against reordered input, not assumed, as of 2026-10-12.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 55 purpose-built AI-engineering tools across neglected niches.

Related tools: [idempotency-key-spec](https://github.com/chenhz01/idempotency-key-spec) · [timezone-safety-check](https://github.com/chenhz01/timezone-safety-check) · [calendar-conflict-check](https://github.com/chenhz01/calendar-conflict-check)

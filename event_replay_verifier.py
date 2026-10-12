#!/usr/bin/env python3
"""event-replay-verifier: check an event stream for replay determinism --
out-of-order, duplicate, and missing sequence numbers -- plus malformed
events. Sits above (not inside) event-sourcing frameworks: it audits a
serialized stream, it is not a store or a bus. Pure stdlib."""

import argparse
import hashlib
import json
import sys

ISSUE_KINDS = ("out_of_order", "duplicate", "missing", "malformed")


def load_stream(path):
    """Load events from JSONL or a JSON array file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(raw)
    else:
        data = []
        for ln, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("line %d: %s" % (ln, exc))
    if not isinstance(data, list):
        raise ValueError("stream must be a JSON array or JSONL")
    return data


def analyze(events):
    """Scan the stream. Returns (issues, stats).
    issue = {"kind", "index" (may be None), "detail"}."""
    issues = []
    seen = {}
    prev = None
    valid = 0
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            issues.append({"kind": "malformed", "index": i, "detail": "event is not an object"})
            continue
        seq = e.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int):
            issues.append({"kind": "malformed", "index": i, "detail": "missing or non-integer seq"})
            continue
        if not e.get("type"):
            issues.append({"kind": "malformed", "index": i, "detail": "missing type"})
            continue
        valid += 1
        if seq in seen:
            issues.append({"kind": "duplicate", "index": i, "detail": "seq %d first seen at index %d" % (seq, seen[seq])})
        else:
            seen[seq] = i
        if prev is not None and seq < prev:
            issues.append({"kind": "out_of_order", "index": i, "detail": "seq %d appears after seq %d" % (seq, prev)})
        prev = seq
    if seen:
        lo, hi = min(seen), max(seen)
        for m in sorted(set(range(lo, hi + 1)) - set(seen)):
            issues.append({"kind": "missing", "index": None, "detail": "seq %d absent between %d and %d" % (m, lo, hi)})
    counts = {k: 0 for k in ISSUE_KINDS}
    for it in issues:
        counts[it["kind"]] += 1
    stats = {
        "total_events": len(events),
        "valid_events": valid,
        "distinct_seqs": len(seen),
        "min_seq": min(seen) if seen else None,
        "max_seq": max(seen) if seen else None,
        "issue_counts": counts,
    }
    return issues, stats


def _project(events):
    """Deterministic fold: canonical projection of a stream.
    Duplicate seqs are deduplicated keeping the first occurrence."""
    seen = set()
    canon_src = []
    for e in events:
        if (isinstance(e, dict) and isinstance(e.get("seq"), int)
                and not isinstance(e.get("seq"), bool) and e.get("type")
                and e["seq"] not in seen):
            seen.add(e["seq"])
            canon_src.append(e)
    canon = sorted(canon_src, key=lambda e: e["seq"])
    type_counts = {}
    for e in canon:
        type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
    payload = json.dumps([{"seq": e["seq"], "type": e["type"], "payload": e.get("payload")}
                          for e in canon], sort_keys=True, ensure_ascii=False)
    return {"last_seq": canon[-1]["seq"] if canon else None,
            "event_count": len(canon),
            "type_counts": type_counts,
            "state_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def replay_check(events, passes=3):
    """Replay the canonical stream N times; deterministic iff all
    projections are identical and independent of input order."""
    issues, stats = analyze(events)
    projections = [_project(events) for _ in range(max(1, passes))]
    shuffled_src = sorted((e for e in events if isinstance(e, dict)),
                          key=lambda e: (e.get("seq") if isinstance(e.get("seq"), int)
                                         and not isinstance(e.get("seq"), bool) else 10**12,
                                         json.dumps(e, sort_keys=True, ensure_ascii=False)))
    projections.append(_project(shuffled_src))
    deterministic = all(p == projections[0] for p in projections)
    return {"issues": issues, "stats": stats, "deterministic": deterministic,
            "projection": projections[0]}


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="event-replay-verifier",
        description="Verify replay determinism of an event stream: out-of-order / duplicate / missing seq detection.",
    )
    p.add_argument("stream", help="event stream file (JSONL or JSON array)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="exit 1 if any issue found")
    args = p.parse_args(argv)

    try:
        events = load_stream(args.stream)
    except Exception as exc:
        print("error: cannot load stream: %s" % exc, file=sys.stderr)
        return 2

    result = replay_check(events)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result["stats"]
        print("events=%d valid=%d seq_range=[%s..%s] deterministic=%s" %
              (s["total_events"], s["valid_events"], s["min_seq"], s["max_seq"],
               result["deterministic"]))
        for k in ISSUE_KINDS:
            print("  %-12s %d" % (k, s["issue_counts"][k]))
        for it in result["issues"][:20]:
            print("  ! [%s] idx=%s: %s" % (it["kind"], it["index"], it["detail"]))
        if len(result["issues"]) > 20:
            print("  ... %d more issues" % (len(result["issues"]) - 20))
    if args.strict and result["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

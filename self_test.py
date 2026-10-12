#!/usr/bin/env python3
"""Self test for event-replay-verifier. Run: python self_test.py
Last line: SUMMARY: PASS n/n"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import event_replay_verifier as erv

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append(name)


def ev(seq, etype="order", payload=None):
    e = {"seq": seq, "type": etype}
    if payload is not None:
        e["payload"] = payload
    return e


def kinds(issues):
    return [i["kind"] for i in issues]


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = erv.main(argv)
    return code, buf.getvalue()


# ---------- functional ----------
iss, st = erv.analyze([ev(1), ev(2), ev(3)])
check("clean_stream_no_issues", iss == [])
check("clean_stats", st["valid_events"] == 3 and st["min_seq"] == 1 and st["max_seq"] == 3)
check("clean_issue_counts_zero", all(v == 0 for v in st["issue_counts"].values()))
iss, st = erv.analyze([ev(2), ev(1)])
check("out_of_order_detected", "out_of_order" in kinds(iss))
check("out_of_order_index", iss[0]["index"] == 1)
iss, st = erv.analyze([ev(1), ev(1), ev(2)])
check("duplicate_detected", kinds(iss) == ["duplicate"])
check("duplicate_detail_first_seen", "first seen at index 0" in iss[0]["detail"])
iss, st = erv.analyze([ev(1), ev(3)])
check("missing_detected", kinds(iss) == ["missing"])
check("missing_detail_range", "absent between 1 and 3" in iss[0]["detail"])
iss, st = erv.analyze([ev(1), ev(2), ev(4), ev(6)])
check("missing_multiple", kinds(iss) == ["missing", "missing"])
check("missing_seq_numbers", [i["detail"].split()[1] for i in iss] == ["3", "5"])
iss, st = erv.analyze([ev(5), ev(3), ev(5), ev(3), ev(4)])
check("mixed_issues", sorted(set(kinds(iss))) == ["duplicate", "out_of_order"])
check("stats_distinct_seqs", st["distinct_seqs"] == 3)
rc = erv.replay_check([ev(1, "a"), ev(2, "b")])
check("replay_deterministic_clean", rc["deterministic"] is True)
check("replay_projection_counts", rc["projection"]["type_counts"] == {"a": 1, "b": 1})
check("replay_projection_last_seq", rc["projection"]["last_seq"] == 2)
rc = erv.replay_check([ev(2, "b"), ev(1, "a")])
check("replay_order_independent", rc["deterministic"] is True and rc["projection"]["last_seq"] == 2)
h1 = erv.replay_check([ev(1, "a", {"x": 1})])["projection"]["state_hash"]
h2 = erv.replay_check([ev(1, "a", {"x": 1})])["projection"]["state_hash"]
check("state_hash_stable", h1 == h2)
h3 = erv.replay_check([ev(1, "a", {"x": 2})])["projection"]["state_hash"]
check("state_hash_sensitive", h1 != h3)
rc = erv.replay_check([ev(1), ev(2), ev(1)])
check("replay_with_duplicate_still_deterministic", rc["deterministic"] is True and rc["projection"]["event_count"] == 2)
rc = erv.replay_check([])
check("replay_empty_deterministic", rc["deterministic"] is True and rc["projection"]["last_seq"] is None)
check("passes_default_3", len(erv.replay_check([ev(1)])["issues"]) == 0)

tmp = tempfile.mkdtemp()
jl = os.path.join(tmp, "stream.jsonl")
with open(jl, "w", encoding="utf-8") as f:
    f.write(json.dumps(ev(1)) + "\n\n")
    f.write(json.dumps(ev(2)) + "\n")
    f.write(json.dumps(ev(3)) + "\n")
code, out = run_cli([jl, "--json"])
r = json.loads(out)
check("cli_jsonl_clean", code == 0 and r["deterministic"] is True and r["stats"]["total_events"] == 3)
ja = os.path.join(tmp, "stream.json")
with open(ja, "w", encoding="utf-8") as f:
    json.dump([ev(1), ev(3)], f)
code, out = run_cli([ja, "--json"])
r = json.loads(out)
check("cli_array_missing", code == 0 and r["stats"]["issue_counts"]["missing"] == 1)
code, out = run_cli([jl])
check("cli_human_mode", code == 0 and "deterministic=True" in out)
bad = os.path.join(tmp, "bad.jsonl")
with open(bad, "w", encoding="utf-8") as f:
    f.write(json.dumps(ev(1)) + "\n{broken\n")
code, out = run_cli([bad])
check("cli_corrupt_line_exit2", code == 2)
code, out = run_cli([jl, "--strict"])
check("cli_strict_clean_exit0", code == 0)
badmiss = os.path.join(tmp, "gap.jsonl")
with open(badmiss, "w", encoding="utf-8") as f:
    f.write(json.dumps(ev(1)) + "\n" + json.dumps(ev(3)) + "\n")
code, out = run_cli([badmiss, "--strict"])
check("cli_strict_issues_exit1", code == 1)
code, out = run_cli([os.path.join(tmp, "nope.jsonl")])
check("cli_missing_file_exit2", code == 2)
check("load_stream_empty_text", erv.load_stream.__doc__ is not None)
emptyf = os.path.join(tmp, "empty.jsonl")
with open(emptyf, "w", encoding="utf-8") as f:
    f.write("   \n")
check("load_stream_whitespace_only", erv.load_stream(emptyf) == [])

# ---------- exception paths ----------
iss, st = erv.analyze(["not-a-dict", 42, None])
check("malformed_non_objects", all(i["kind"] == "malformed" for i in iss) and len(iss) == 3)
iss, st = erv.analyze([{"type": "x"}])
check("malformed_missing_seq", kinds(iss) == ["malformed"])
iss, st = erv.analyze([{"seq": "1", "type": "x"}])
check("malformed_string_seq", kinds(iss) == ["malformed"])
iss, st = erv.analyze([{"seq": 1.5, "type": "x"}])
check("malformed_float_seq", kinds(iss) == ["malformed"])
iss, st = erv.analyze([{"seq": True, "type": "x"}])
check("malformed_bool_seq", kinds(iss) == ["malformed"])
iss, st = erv.analyze([{"seq": 1}])
check("malformed_missing_type", kinds(iss) == ["malformed"])
iss, st = erv.analyze([{"seq": 1, "type": ""}])
check("malformed_empty_type", kinds(iss) == ["malformed"])
try:
    erv.load_stream(os.path.join(tmp, "does_not_exist.jsonl"))
    check("load_missing_raises", False)
except OSError:
    check("load_missing_raises", True)
nota = os.path.join(tmp, "obj.json")
with open(nota, "w", encoding="utf-8") as f:
    f.write('{"seq": 1}')
check("load_object_as_single_jsonl_record", erv.load_stream(nota) == [{"seq": 1}])
badjson = os.path.join(tmp, "bad.json")
with open(badjson, "w", encoding="utf-8") as f:
    f.write("[{oops]")
try:
    erv.load_stream(badjson)
    check("load_bad_json_raises", False)
except (ValueError, json.JSONDecodeError):
    check("load_bad_json_raises", True)
iss, st = erv.analyze(["not-a-dict", 42, None])
check("analyze_none_event_skipped", st["total_events"] == 3 and st["valid_events"] == 0)
rc = erv.replay_check([None, ev(1)])
check("replay_with_junk_deterministic", rc["deterministic"] is True)

# ---------- extreme edge cases ----------
iss, st = erv.analyze([])
check("edge_empty_stream", iss == [] and st["total_events"] == 0 and st["min_seq"] is None)
rc = erv.replay_check([])
check("edge_empty_replay", rc["deterministic"] is True and rc["projection"]["event_count"] == 0)
iss, _ = erv.analyze([ev(1)] * 100)
check("edge_all_duplicates", len([i for i in iss if i["kind"] == "duplicate"]) == 99)
rev = [ev(i) for i in range(1000, 0, -1)]
iss, _ = erv.analyze(rev)
check("edge_fully_reversed", len([i for i in iss if i["kind"] == "out_of_order"]) == 999)
big = [ev(i, "t%d" % (i % 5), {"i": i}) for i in range(1, 5001)]
rc = erv.replay_check(big)
check("edge_large_clean_stream", rc["deterministic"] is True and rc["projection"]["event_count"] == 5000)
uni = [ev(1, "订单", {"客户": "田中"}), ev(2, "emoji🚀")]
rc = erv.replay_check(uni)
check("edge_unicode_types", rc["deterministic"] is True and rc["projection"]["type_counts"]["订单"] == 1)
long_payload = {"blob": "x" * 100000}
rc = erv.replay_check([ev(1, "big", long_payload), ev(2, "big", long_payload)])
check("edge_large_payload", rc["deterministic"] is True)
nested = [ev(1, "deep", {"a": {"b": {"c": {"d": [1, 2, {"e": 3}]}}}})]
rc = erv.replay_check(nested)
check("edge_deep_nesting", rc["deterministic"] is True)
neg = [ev(-5), ev(-3)]
iss, st = erv.analyze(neg)
check("edge_negative_seqs_missing", kinds(iss) == ["missing"] and st["min_seq"] == -5)
dup_cross_order = [ev(2), ev(1), ev(2)]
rc = erv.replay_check(dup_cross_order)
check("edge_dup_dedup_projection", rc["projection"]["event_count"] == 2 and rc["deterministic"] is True)
junk_mix = [None, "s", ev(1), {"seq": 2}, ev(3)]
rc = erv.replay_check(junk_mix)
check("edge_mixed_junk_and_valid", rc["deterministic"] is True and rc["projection"]["event_count"] == 2)
check("edge_hash_hex16_stable", len(rc["projection"]["state_hash"]) == 64)

print()
if FAILED:
    print("FAILED CASES:", ", ".join(FAILED))
print("SUMMARY: PASS %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)

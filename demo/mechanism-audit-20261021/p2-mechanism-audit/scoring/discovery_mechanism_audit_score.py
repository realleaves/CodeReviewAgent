"""Offline scoring of P2; semantic decisions are explicit, never keyword matches."""

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def score(phase, adjudications):
    phase = Path(phase)
    manifest = load(phase / "manifest.json")
    records = load(phase / "results.json")["records"]
    assert manifest["repetitions"] == 1
    arms = ["baseline", "mechanism_audit"]
    assert set(manifest["strategies"]) == set(arms)
    cases = sorted({row["case"] for row in manifest["input_windows"]})
    expected = {
        (case, arm, side)
        for case in cases
        for arm in arms
        for side in ["buggy", "fixed"]
    }
    windows = {(r["case"], r["strategy"], r["side"]): r for r in records}
    decisions = {(r["case"], r["mode"], r["variant"]): r for r in adjudications}
    assert len(windows) == len(records) == len(expected), "Missing/duplicate windows"
    assert len(decisions) == len(adjudications) == len(expected), (
        "Missing/duplicate decisions"
    )
    assert set(windows) == set(decisions) == expected
    for key, record in windows.items():
        decision = decisions[key]
        assert record["api_calls"] == len(record["calls"])
        actual = {f["id"]: f for f in record["findings"]}
        active = {f["id"]: f for f in decision["active_findings"]}
        assert actual == active
        reviews = {f["id"]: f for f in decision["finding_reviews"]}
        assert len(reviews) == len(decision["finding_reviews"]) == len(actual)
        assert set(reviews) == set(actual)
        assert all(
            type(r["reference_match"]) is bool and r["reason"] for r in reviews.values()
        )
        matched = {fid for fid, review in reviews.items() if review["reference_match"]}
        assert matched == set(decision["matched_finding_ids"])
        assert type(decision["target_issue_detected"]) is bool
        assert decision["target_issue_detected"] == bool(matched)
        assert decision["reason"] and decision["adjudicator"]

    metrics = []
    for arm in arms:
        selected = [r for key, r in windows.items() if key[1] == arm]
        eligible = [
            case
            for case in cases
            if all(
                windows[case, arm, side]["status"] == "completed"
                for side in ["buggy", "fixed"]
            )
        ]
        hit_cases = [
            case
            for case in eligible
            if decisions[case, arm, "buggy"]["target_issue_detected"]
        ]
        alarm_cases = [
            case
            for case in cases
            if decisions[case, arm, "fixed"]["target_issue_detected"]
        ]
        traces = [
            t
            for r in selected
            for t in r.get("trace", [])
            if t.get("stage") == "mechanism_audit"
        ]
        metrics.append(
            {
                "arm": arm,
                "planned_cases": len(cases),
                "eligible_pairs": len(eligible),
                "eligible_cases": eligible,
                "candidate_hits": len(hit_cases),
                "candidate_hit_cases": hit_cases,
                "observed_buggy_hits": sum(
                    decisions[case, arm, "buggy"]["target_issue_detected"]
                    for case in cases
                ),
                "fixed_side_alarms": len(alarm_cases),
                "fixed_side_alarm_cases": alarm_cases,
                "correctly_discriminated_cases": sum(
                    case not in alarm_cases for case in hit_cases
                ),
                "candidate_findings": sum(len(r["findings"]) for r in selected),
                "planned_windows": len(cases) * 2,
                "completed_windows": sum(r["status"] == "completed" for r in selected),
                "failed_windows": sum(r["status"] != "completed" for r in selected),
                "calls": sum(r["api_calls"] for r in selected),
                "failed_provider_calls": sum(
                    c["status"] == "failed" for r in selected for c in r["calls"]
                ),
                "usage": {
                    name: sum(
                        c.get("usage", {}).get(name, 0)
                        for r in selected
                        for c in r["calls"]
                    )
                    for name in ["prompt_tokens", "completion_tokens"]
                },
                "tool_reads": sum(len(r.get("tool_reads", [])) for r in selected),
                "audit_windows": len(traces),
                "audit_removed": sum(len(t["removed"]) for t in traces),
                "audit_added": sum(len(t["added"]) for t in traces),
                "fallback_initial": sum(t["fallback_initial"] is True for t in traces),
                "initial_reference_hypothesis_windows": sum(
                    decisions[key]
                    .get("initial_hypothesis_review", {})
                    .get("reference_hypothesis_present")
                    is True
                    for key in windows
                    if key[1] == arm
                ),
            }
        )
    baseline, audit = metrics
    delta = {
        key: audit[key] - baseline[key]
        for key in baseline
        if type(baseline[key]) is int
    }
    delta["usage"] = {
        key: audit["usage"][key] - baseline["usage"][key] for key in baseline["usage"]
    }
    complete = all(m["eligible_pairs"] == len(cases) for m in metrics)
    gate = (
        complete
        and audit["candidate_hits"] >= 1
        and audit["fixed_side_alarms"] <= baseline["fixed_side_alarms"]
    )
    return {
        "metrics": metrics,
        "delta_mechanism_audit_minus_baseline": delta,
        "smoke_gate_met": gate,
        "decision": "eligible for a separately budgeted expansion, not default adoption"
        if gate
        else "do not expand or change the baseline default",
        "rule": "At least one strict reference candidate hit in mechanism_audit and no increase in fixed-side same-reference alarms; both arms must have complete pairs.",
        "scoring": "Reference root cause/symptom plus a valid trigger. Hits use complete pairs; all observed fixed-side alarms, failures and costs remain reported. Extra findings are not automatic false positives.",
        "adjudicators": sorted({r["adjudicator"] for r in adjudications}),
        "scope": {
            "development_cases": len(cases),
            "repetitions": 1,
            "evidence_stage_run": False,
            "holdout_run": False,
        },
        "limitations": [
            "A single smoke repetition cannot establish reproducibility or generalization.",
            "Candidate hits do not measure valid evidence conversion; no evidence engine was run.",
            "Removed/added counts compare path, line, category and title, not semantic mechanisms.",
            "Semantic adjudication is by Codex against the frozen rubric; independent human review is pending.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score(args.phase, load(args.adjudications))
    target = args.output or args.phase / "scores.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# P2 mechanism audit smoke scores",
        "",
        "| arm | eligible | hits | fixed alarms | findings | completed/failed | calls | prompt/completion tokens | removed/added/fallback |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in result["metrics"]:
        lines.append(
            f"| {m['arm']} | {m['eligible_pairs']}/{m['planned_cases']} | {m['candidate_hits']} | {m['fixed_side_alarms']} | {m['candidate_findings']} | {m['completed_windows']}/{m['failed_windows']} | {m['calls']} | {m['usage']['prompt_tokens']}/{m['usage']['completion_tokens']} | {m['audit_removed']}/{m['audit_added']}/{m['fallback_initial']} |"
        )
    lines += ["", result["decision"], "", *result["limitations"], ""]
    target.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

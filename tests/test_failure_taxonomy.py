from evaluation.evidence_failure_taxonomy import build


def test_failure_taxonomy_keeps_the_frozen_counts():
    result = build()
    assert result["counts"] == {
        "eligible_pairs": 26,
        "candidate_hits": 4,
        "valid_evidence": 1,
        "misses": 22,
        "candidate_hit_evidence_failed": 3,
        "no_candidate": 8,
        "off_target_reproduced": 4,
        "off_target_unproven": 10,
    }


def test_no_candidate_and_off_target_cases_are_explicit():
    result = build()
    by_category = {}
    for row in result["records"]:
        by_category.setdefault(row["category"], []).append(row["case"])
    assert by_category["no_candidate"] == [
        "tornado-3",
        "tornado-5",
        "tornado-7",
        "tornado-8",
        "tornado-9",
        "youtube-dl-1",
        "youtube-dl-2",
        "youtube-dl-3",
    ]
    assert len(by_category["off_target_reproduced"]) == 4
    assert len(by_category["off_target_unproven"]) == 10
    assert by_category["candidate_hit_evidence_failed"] == [
        "tornado-4",
        "youtube-dl-11",
        "youtube-dl-6",
    ]

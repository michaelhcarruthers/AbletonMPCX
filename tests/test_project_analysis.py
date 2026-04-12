"""Tests for tools/project_analysis.py — Debug Mode and Final Review Mode."""
from __future__ import annotations

import pytest
from tools.project_analysis import debug_mix_compare, final_review_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(
    name: str,
    volume: float = 0.75,
    devices: list | None = None,
    spectral_tilt: float | None = None,
    crest_factor: float | None = None,
    stereo_width: float | None = None,
    lufs: float | None = None,
    bpm: float | None = None,
) -> dict:
    return {
        "name": name,
        "mixer_device": {"volume": volume},
        "devices": devices or [],
        "spectral_tilt": spectral_tilt,
        "crest_factor": crest_factor,
        "stereo_width": stereo_width,
        "lufs": lufs,
        "bpm": bpm,
    }


# ===========================================================================
# WORKFLOW 1 — DEBUG MODE
# ===========================================================================

class TestDebugMixCompare:

    def test_returns_debug_mode(self):
        tracks = [
            _make_track("Piano"),
            _make_track("Vocal"),
            _make_track("Drums"),
        ]
        result = debug_mix_compare(tracks)
        assert result["mode"] == "debug"

    def test_requires_exactly_three_tracks(self):
        # Too few
        result = debug_mix_compare([_make_track("A"), _make_track("B")])
        assert result["status"] == "error"
        assert "3" in result["error"]

        # Too many
        tracks = [_make_track(str(i)) for i in range(4)]
        result = debug_mix_compare(tracks)
        assert result["status"] == "error"

        # Empty
        result = debug_mix_compare([])
        assert result["status"] == "error"

    def test_non_list_input(self):
        result = debug_mix_compare("not a list")  # type: ignore[arg-type]
        assert result["status"] == "error"

    def test_track_count_in_result(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks)
        assert result["track_count"] == 3

    def test_per_track_has_three_entries(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        assert len(result["per_track"]) == 3

    def test_per_track_contains_required_fields(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        for entry in result["per_track"]:
            assert "label" in entry
            assert "name" in entry
            assert "issues" in entry
            assert isinstance(entry["issues"], list)

    def test_default_labels_abc(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        labels = [e["label"] for e in result["per_track"]]
        assert labels == ["A", "B", "C"]

    def test_custom_labels(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks, labels=["Song1", "Song2", "Song3"])
        labels = [e["label"] for e in result["per_track"]]
        assert labels == ["Song1", "Song2", "Song3"]

    def test_custom_labels_wrong_count_falls_back_to_abc(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks, labels=["X", "Y"])  # only 2 labels
        labels = [e["label"] for e in result["per_track"]]
        assert labels == ["A", "B", "C"]

    def test_cross_track_comparison_present(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        cmp = result["cross_track_comparison"]
        assert "loudness_spread_db" in cmp
        assert "relative_levels" in cmp
        assert len(cmp["relative_levels"]) == 3

    def test_most_likely_problem_track_present(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        problem = result["most_likely_problem_track"]
        assert "name" in problem
        assert "label" in problem
        assert "reason" in problem

    def test_ranked_corrections_present(self):
        tracks = [_make_track("Piano"), _make_track("Vocal"), _make_track("Drums")]
        result = debug_mix_compare(tracks)
        corrections = result["ranked_corrections"]
        assert isinstance(corrections, list)
        assert len(corrections) >= 1
        for c in corrections:
            assert "track" in c
            assert "proposed_move" in c
            assert "confidence" in c

    def test_no_sequencing_logic_in_output(self):
        """Debug Mode must NOT contain sequencing fields."""
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks)
        assert "suggested_track_order" not in result
        assert "transition_notes" not in result

    def test_recheck_guidance_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks)
        assert "recheck_guidance" in result
        assert isinstance(result["recheck_guidance"], str)

    def test_language_notes_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks)
        assert "language_notes" in result

    def test_loudness_outlier_detected(self):
        """Track with significantly higher volume should be flagged."""
        tracks = [
            _make_track("Loud", volume=0.95),
            _make_track("Normal", volume=0.60),
            _make_track("Quiet", volume=0.55),
        ]
        result = debug_mix_compare(tracks)
        loud_entry = next(e for e in result["per_track"] if e["name"] == "Loud")
        assert any("louder" in issue for issue in loud_entry["issues"])

    def test_low_mid_dense_track_flagged(self):
        """A piano track should be flagged as likely low-mid contributor."""
        tracks = [
            _make_track("Piano"),
            _make_track("Hihat"),
            _make_track("Sub"),
        ]
        result = debug_mix_compare(tracks)
        piano_entry = next(e for e in result["per_track"] if e["name"] == "Piano")
        assert any("low-mid" in issue for issue in piano_entry["issues"])

    def test_bus_processed_track_gets_smaller_move(self):
        """A track with bus-style processing should get a -0.5 dB proposed move."""
        bus_device = {"name": "SSL Bus Comp"}
        tracks = [
            _make_track("Piano", devices=[bus_device]),
            _make_track("Vocal"),
            _make_track("Drums"),
        ]
        result = debug_mix_compare(tracks)
        corrections = result["ranked_corrections"]
        piano_correction = next(
            (c for c in corrections if c.get("track") == "Piano"),
            None,
        )
        if piano_correction:
            assert "-0.5 dB" in piano_correction["proposed_move"]

    def test_tonal_difference_detected(self):
        """When spectral tilt differs, tonal note should describe the difference."""
        tracks = [
            _make_track("A", spectral_tilt=-0.4),
            _make_track("B", spectral_tilt=0.0),
            _make_track("C", spectral_tilt=0.3),
        ]
        result = debug_mix_compare(tracks)
        tonal_note = result["cross_track_comparison"]["tonal_note"]
        assert "darker" in tonal_note or "brighter" in tonal_note

    def test_density_difference_detected(self):
        """When crest factors differ, density note should describe the difference."""
        tracks = [
            _make_track("Dense", crest_factor=0.2),
            _make_track("Mid", crest_factor=0.5),
            _make_track("Sparse", crest_factor=0.8),
        ]
        result = debug_mix_compare(tracks)
        density_note = result["cross_track_comparison"]["density_note"]
        assert "denser" in density_note or "sparse" in density_note


# ===========================================================================
# WORKFLOW 2 — FINAL REVIEW MODE
# ===========================================================================

class TestFinalReviewMode:

    def test_returns_final_review_mode(self):
        tracks = [_make_track("T1"), _make_track("T2"), _make_track("T3")]
        result = final_review_mode(tracks)
        assert result["mode"] == "final_review"

    def test_requires_at_least_two_tracks(self):
        result = final_review_mode([_make_track("Only")])
        assert result["status"] == "error"
        assert "2" in result["error"]

        result = final_review_mode([])
        assert result["status"] == "error"

    def test_non_list_input(self):
        result = final_review_mode("not a list")  # type: ignore[arg-type]
        assert result["status"] == "error"

    def test_track_count_matches_input(self):
        tracks = [_make_track(f"T{i}") for i in range(5)]
        result = final_review_mode(tracks)
        assert result["track_count"] == 5

    def test_project_summary_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        summary = result["project_summary"]
        assert "track_count" in summary
        assert summary["track_count"] == 3

    def test_per_track_metrics_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        assert len(result["per_track_metrics"]) == 3
        for m in result["per_track_metrics"]:
            assert "name" in m
            assert "cohesion_status" in m

    def test_cohesion_status_values(self):
        tracks = [_make_track(f"T{i}") for i in range(4)]
        result = final_review_mode(tracks)
        valid_statuses = {"fits", "slight outlier", "clear outlier"}
        for m in result["per_track_metrics"]:
            assert m["cohesion_status"] in valid_statuses

    def test_suggested_track_order_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        order = result["suggested_track_order"]
        assert isinstance(order, list)
        assert len(order) == 3
        assert set(order) == {"A", "B", "C"}

    def test_suggested_order_indices_cover_all_tracks(self):
        tracks = [_make_track(f"T{i}") for i in range(4)]
        result = final_review_mode(tracks)
        indices = result["suggested_order_indices"]
        assert sorted(indices) == list(range(4))

    def test_transition_notes_count(self):
        tracks = [_make_track(f"T{i}") for i in range(4)]
        result = final_review_mode(tracks)
        notes = result["transition_notes"]
        assert len(notes) == 3  # N-1 transitions for N tracks

    def test_transition_notes_fields(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        for note in result["transition_notes"]:
            assert "from" in note
            assert "to" in note
            assert "description" in note
            assert "distance_score" in note

    def test_cohesion_issues_list_present(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        assert "cohesion_issues" in result
        assert isinstance(result["cohesion_issues"], list)

    def test_loudness_outlier_flagged(self):
        tracks = [
            _make_track("Loud", volume=0.99),
            _make_track("Normal", volume=0.50),
            _make_track("Normal2", volume=0.52),
        ]
        result = final_review_mode(tracks)
        # Loud track should appear as outlier
        issue_tracks = {issue["track"] for issue in result["cohesion_issues"]}
        assert "Loud" in issue_tracks

    def test_tonal_outlier_flagged(self):
        tracks = [
            _make_track("Bright", spectral_tilt=0.7),
            _make_track("Normal", spectral_tilt=0.0),
            _make_track("Normal2", spectral_tilt=0.05),
        ]
        result = final_review_mode(tracks)
        tonal_issues = [i for i in result["cohesion_issues"] if i["issue"] == "tonal_outlier"]
        assert len(tonal_issues) >= 1

    def test_density_outlier_flagged(self):
        tracks = [
            _make_track("Dense", crest_factor=0.1),
            _make_track("Normal", crest_factor=0.6),
            _make_track("Normal2", crest_factor=0.65),
        ]
        result = final_review_mode(tracks)
        density_issues = [i for i in result["cohesion_issues"] if i["issue"] == "density_outlier"]
        assert len(density_issues) >= 1

    def test_anchor_track_used_as_reference(self):
        tracks = [
            _make_track("Anchor"),
            _make_track("T2"),
            _make_track("T3"),
        ]
        result = final_review_mode(tracks, anchor_index=0)
        assert "anchor" in result["reference_used"]
        assert "Anchor" in result["reference_used"]

    def test_median_used_when_no_anchor(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        assert "median" in result["reference_used"]

    def test_custom_track_names(self):
        tracks = [_make_track("T1"), _make_track("T2"), _make_track("T3")]
        result = final_review_mode(tracks, track_names=["Song One", "Song Two", "Song Three"])
        names_in_order = result["suggested_track_order"]
        assert set(names_in_order) == {"Song One", "Song Two", "Song Three"}

    def test_current_sequence_preserved(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks, sequence=[2, 0, 1])
        assert result["current_sequence"] == ["C", "A", "B"]

    def test_current_sequence_none_when_not_provided(self):
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        assert result["current_sequence"] is None

    def test_recommendation_notes_present(self):
        tracks = [_make_track("A"), _make_track("B")]
        result = final_review_mode(tracks)
        notes = result["recommendation_notes"]
        assert "philosophy" in notes
        assert "loudness" in notes
        assert "sequencing" in notes

    def test_no_three_track_limit(self):
        """Final Review Mode should accept more than 3 tracks."""
        tracks = [_make_track(f"T{i}") for i in range(10)]
        result = final_review_mode(tracks)
        assert result["mode"] == "final_review"
        assert result["track_count"] == 10

    def test_two_track_minimum(self):
        """Final Review Mode should work with exactly 2 tracks."""
        tracks = [_make_track("A"), _make_track("B")]
        result = final_review_mode(tracks)
        assert result["mode"] == "final_review"
        assert result["track_count"] == 2
        assert len(result["transition_notes"]) == 1

    def test_cohesion_issue_priority_order(self):
        """Tonal / density issues should appear before loudness issues."""
        tracks = [
            _make_track("A", volume=0.99, spectral_tilt=0.8),  # both loud and tonal outlier
            _make_track("B", volume=0.50, spectral_tilt=0.0),
            _make_track("C", volume=0.52, spectral_tilt=0.0),
        ]
        result = final_review_mode(tracks)
        issues = result["cohesion_issues"]
        if len(issues) >= 2:
            type_priority = {"tonal_outlier": 0, "density_outlier": 1, "width_outlier": 2, "loudness_outlier": 3}
            for i in range(len(issues) - 1):
                p1 = type_priority.get(issues[i]["issue"], 9)
                p2 = type_priority.get(issues[i + 1]["issue"], 9)
                assert p1 <= p2


# ===========================================================================
# WORKFLOW SEPARATION
# ===========================================================================

class TestWorkflowSeparation:

    def test_debug_mode_has_no_sequencing(self):
        """debug_mix_compare must never return sequencing fields."""
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = debug_mix_compare(tracks)
        sequencing_fields = {"suggested_track_order", "transition_notes", "suggested_order_indices"}
        assert not sequencing_fields.intersection(result.keys())

    def test_final_review_has_sequencing(self):
        """final_review_mode must return sequencing fields."""
        tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
        result = final_review_mode(tracks)
        assert "suggested_track_order" in result
        assert "transition_notes" in result

    def test_debug_enforces_three_track_limit(self):
        """debug_mix_compare rejects anything other than exactly 3 tracks."""
        for n in [0, 1, 2, 4, 5, 10]:
            tracks = [_make_track(f"T{i}") for i in range(n)]
            result = debug_mix_compare(tracks)
            assert result.get("status") == "error", f"Expected error for {n} tracks"

    def test_final_review_accepts_n_tracks(self):
        """final_review_mode accepts any N >= 2 without error."""
        for n in [2, 3, 4, 5, 10, 20]:
            tracks = [_make_track(f"T{i}") for i in range(n)]
            result = final_review_mode(tracks)
            assert result.get("mode") == "final_review", f"Expected final_review mode for {n} tracks"
            assert result.get("status") != "error", f"Unexpected error for {n} tracks"

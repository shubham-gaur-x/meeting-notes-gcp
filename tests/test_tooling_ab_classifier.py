"""The classifier A/B tool.

Not a phase deliverable, so it sits outside the `test_phaseNN_*` naming — it
covers `scripts/ab_classifier.py`, the same way `test_phase06_doctor.py` covers
the other operator script.

Everything here runs with no database and no network. The two classifier
revisions under comparison are injected as stub modules, so these tests do not
depend on what `meeting_notes/classifier.py` happens to score today — a tool
whose tests move every time the thing it measures changes is not a useful tool.

The one test that does touch the filesystem shells out to `git show` against
this repo, which is local and is what the function under test exists to do.
"""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from meeting_notes.models import StagedRecord
from scripts.ab_classifier import (
    Scored,
    build_parser,
    label,
    load_classifier_at_revision,
    render,
    score_records,
    select_records,
)

THRESHOLD = 0.40
SUBJECT = "Quarterly planning sync"


def _record(source_id: str, subject: str = SUBJECT, *, processed: bool = False) -> StagedRecord:
    """One staged email thread, shaped the way `sources/gmail.py` stages it."""
    return StagedRecord(
        id=f"row-{source_id}",
        source_id=source_id,
        source_type="email",
        payload={
            "subject": subject,
            "from": "someone@example.com",
            "to": "shubham@example.com",
            "body": "Agenda attached.",
        },
        fetched_at="2026-08-29T00:00:00+00:00",
        processed=processed,
    )


def _classifier(score: float) -> ModuleType:
    """A stub revision that scores everything the same."""
    return cast(ModuleType, SimpleNamespace(classify=lambda text, metadata: score))


def _scored(base: float, head: float, subject: str = SUBJECT) -> Scored:
    return Scored(
        source_id="abc123",
        title=subject,
        base_score=base,
        head_score=head,
        base_passes=base >= THRESHOLD,
        head_passes=head >= THRESHOLD,
    )


# ─── the two properties the report is built on ────────────────────────────────


def test_flipped_is_true_only_when_the_gate_decision_changes() -> None:
    assert _scored(0.47, 0.00).flipped  # crossed down through the gate
    assert _scored(0.10, 0.90).flipped  # crossed up
    assert not _scored(0.47, 0.44).flipped  # moved, both still above
    assert not _scored(0.28, 0.00).flipped  # moved, both still below


def test_moved_catches_a_score_change_that_leaves_the_decision_alone() -> None:
    """The interesting near-miss case: a pattern fired but changed nothing.

    This is what tells a reviewer their rules are working but aimed at mail
    that was already being dropped.
    """
    assert _scored(0.28, 0.00).moved
    assert not _scored(0.28, 0.28).moved


# ─── scoring ──────────────────────────────────────────────────────────────────


def test_score_records_runs_both_revisions_over_every_record() -> None:
    records = [_record("a"), _record("b")]

    scored = score_records(records, "email", _classifier(0.9), _classifier(0.1), THRESHOLD)

    assert [s.source_id for s in scored] == ["a", "b"]
    assert all(s.base_score == 0.9 and s.head_score == 0.1 for s in scored)


def test_score_records_applies_the_threshold_to_both_sides() -> None:
    scored = score_records([_record("a")], "email", _classifier(0.47), _classifier(0.0), THRESHOLD)

    assert scored[0].base_passes is True
    assert scored[0].head_passes is False
    assert scored[0].flipped


def test_score_records_feeds_the_real_adapter_text_to_the_classifier() -> None:
    """The point of the tool is that it scores what the pipeline would score.

    If this stopped going through `pipeline.adapter_for`, the tool would be
    measuring a string the pipeline never builds, and its numbers would not
    transfer to a real run.
    """
    seen: list[tuple[str, dict[str, Any]]] = []

    def capture(text: str, metadata: dict[str, Any]) -> float:
        seen.append((text, metadata))
        return 0.0

    revision = cast(ModuleType, SimpleNamespace(classify=capture))
    score_records([_record("a")], "email", revision, revision, THRESHOLD)

    text, metadata = seen[0]
    assert SUBJECT in text
    assert "Agenda attached." in text
    assert metadata["from"] == "someone@example.com"


def test_score_records_handles_an_empty_corpus() -> None:
    assert score_records([], "email", _classifier(0.9), _classifier(0.1), THRESHOLD) == []


# ─── corpus selection ─────────────────────────────────────────────────────────


def test_select_records_keeps_everything_by_default() -> None:
    records = [_record("a", processed=True), _record("b", processed=False)]
    assert len(select_records(records, unprocessed_only=False)) == 2


def test_select_records_can_narrow_to_rows_the_pipeline_has_not_drained() -> None:
    records = [_record("a", processed=True), _record("b", processed=False)]
    assert [r.source_id for r in select_records(records, unprocessed_only=True)] == ["b"]


# ─── the privacy guarantee ────────────────────────────────────────────────────
#
# Staged payloads are real mail and the repo is public. The default output has
# to be safe to paste into a pull request, so this is a behaviour under test
# rather than a convention.


def test_label_withholds_the_subject_by_default() -> None:
    item = _scored(0.47, 0.00, subject="Confidential: acquisition terms")
    assert label(item, show_subjects=False) == "abc123"
    assert "acquisition" not in label(item, show_subjects=False)


def test_label_shows_the_subject_when_explicitly_asked() -> None:
    item = _scored(0.47, 0.00, subject="Confidential: acquisition terms")
    assert label(item, show_subjects=True) == "Confidential: acquisition terms"


def test_render_leaks_no_subject_without_show_subjects(capsys: pytest.CaptureFixture[str]) -> None:
    secret = "Confidential: acquisition terms"
    scored = [_scored(0.47, 0.00, subject=secret), _scored(0.28, 0.00, subject=secret)]

    render(scored, base="master", threshold=THRESHOLD, show_subjects=False)

    out = capsys.readouterr().out
    assert secret not in out
    assert "acquisition" not in out
    assert "abc123" in out


def test_render_shows_subjects_when_asked(capsys: pytest.CaptureFixture[str]) -> None:
    subject = "Quarterly planning sync"
    render([_scored(0.47, 0.00, subject=subject)], base="master", threshold=THRESHOLD, show_subjects=True)

    assert subject in capsys.readouterr().out


# ─── the report ───────────────────────────────────────────────────────────────


def test_render_counts_each_bucket_once(capsys: pytest.CaptureFixture[str]) -> None:
    scored = [
        _scored(0.47, 0.00),  # flipped: extracted -> dropped
        _scored(0.90, 0.90),  # extracted by both
        _scored(0.10, 0.10),  # dropped by both
        _scored(0.28, 0.00),  # moved, decision unchanged
    ]

    render(scored, base="master", threshold=THRESHOLD, show_subjects=False)

    out = capsys.readouterr().out
    assert "records: 4" in out
    assert "extracted by both:      1" in out
    assert "dropped by both:        2" in out
    assert "GATE DECISION CHANGED:  1" in out
    assert "of the unchanged, 1 scored differently" in out


def test_render_flags_a_record_the_change_newly_sends_to_the_llm(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rule that lets more mail through is the expensive direction, so the
    report calls it out rather than reporting a bare count."""
    render([_scored(0.10, 0.90)], base="master", threshold=THRESHOLD, show_subjects=False)

    out = capsys.readouterr().out
    assert "DROPPED -> EXTRACTED" in out
    assert "new work for the LLM" in out


def test_render_survives_a_corpus_with_no_differences(
    capsys: pytest.CaptureFixture[str],
) -> None:
    render([_scored(0.90, 0.90)], base="master", threshold=THRESHOLD, show_subjects=False)

    out = capsys.readouterr().out
    assert "GATE DECISION CHANGED:  0" in out
    assert "scores that moved" not in out


# ─── loading a revision out of git ────────────────────────────────────────────


def test_load_classifier_at_revision_returns_a_usable_module() -> None:
    module = load_classifier_at_revision("HEAD")

    assert callable(module.classify)
    assert isinstance(module.classify("Standup agenda for Monday", {}), float)


def test_load_classifier_at_revision_does_not_shadow_the_imported_one() -> None:
    """Loaded under a private name so the head-side import stays untouched."""
    from meeting_notes import classifier as head

    module = load_classifier_at_revision("HEAD")

    assert module is not head
    assert module.__name__ == "_classifier_base"


def test_load_classifier_at_revision_fails_loudly_on_an_unknown_revision() -> None:
    with pytest.raises(SystemExit) as excinfo:
        load_classifier_at_revision("no-such-revision-abcdef")

    assert "no-such-revision-abcdef" in str(excinfo.value)


# ─── the CLI ──────────────────────────────────────────────────────────────────


def test_parser_defaults_to_email_against_master() -> None:
    args = build_parser().parse_args([])

    assert args.base == "master"
    assert args.source == "email"
    assert args.unprocessed_only is False
    assert args.show_subjects is False
    assert args.threshold is None


def test_parser_accepts_every_staged_source() -> None:
    for source in ("email", "calendar", "meet"):
        assert build_parser().parse_args(["--source", source]).source == source


def test_parser_rejects_a_source_that_has_no_adapter() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--source", "jira"])


def test_parser_takes_a_threshold_override() -> None:
    assert build_parser().parse_args(["--threshold", "0.25"]).threshold == 0.25


def test_render_buckets_are_disjoint_and_sum_to_the_corpus(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A record belongs to exactly one of the three headline buckets.

    `moved` overlaps both unchanged buckets, so printing it as a peer made the
    four numbers exceed the corpus size and quietly misreport the comparison.
    """
    scored = [_scored(0.47, 0.00), _scored(0.90, 0.90), _scored(0.10, 0.10), _scored(0.28, 0.00)]

    render(scored, base="master", threshold=THRESHOLD, show_subjects=False)

    out = capsys.readouterr().out
    counts = [
        int(line.split(":")[1].strip())
        for line in out.splitlines()
        if line.strip().startswith(("extracted by both", "dropped by both", "GATE DECISION"))
    ]
    assert sum(counts) == len(scored)

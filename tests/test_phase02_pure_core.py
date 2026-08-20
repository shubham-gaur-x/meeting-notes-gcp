"""Phase 2 — the pure core. No I/O, no network, no database.

Every test here runs with no GCP, no Postgres, no Memgraph and no LLM.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from meeting_notes.access_control import (
    ADMIN,
    LEAD,
    MEMBER,
    AccessDenied,
    Principal,
    Scope,
    aggregates_only,
    authorize,
    load_policy,
    parse_scope,
    scope_predicate,
)
from meeting_notes.classifier import classify
from meeting_notes.config import Settings
from meeting_notes.dedup import best_match, cosine, similarity
from meeting_notes.meeting_quality import (
    composite_quality,
    percentile_rank,
    score_action_completion,
    score_agenda_present,
    score_attendance_ratio,
    score_recurrence_health,
    top_and_bottom,
)
from meeting_notes.meeting_type_router import TYPES, prompt_hint, route
from meeting_notes.models import (
    ActionItem,
    Attendee,
    Decision,
    ExtractedMeeting,
    RawEmail,
    StagedRecord,
)
from meeting_notes.person_resolver import (
    Roster,
    RosterEntry,
    load_roster,
    normalize_email,
    resolve,
    resolve_attendees,
)
from meeting_notes.utils import (
    extract_ticket_keys,
    priority_from_due,
    strip_json_fences,
    uuid5_id,
)

# ─── config ───────────────────────────────────────────────────────────────────


def test_settings_read_from_an_explicit_mapping_not_the_process_env() -> None:
    """Settings must be constructible from an explicit dict so tests never
    depend on the ambient environment."""
    s = Settings(GCP_PROJECT_ID="proj", LLM_BACKEND="fake")
    assert s.gcp_project_id == "proj"
    assert s.llm_backend == "fake"


def test_settings_default_to_the_tier_zero_backend() -> None:
    """A clone with no .env at all must default to the offline backend —
    that is what makes `make demo` work with no credentials (ADR-014)."""
    assert Settings(_env_file=None).llm_backend == "fake"


def test_settings_reject_an_unknown_llm_backend() -> None:
    with pytest.raises(ValueError):
        Settings(LLM_BACKEND="not-a-backend")


def test_embedding_dimension_is_768() -> None:
    """Both Memgraph vector indexes are built for 768. Changing this without
    migrating them silently breaks semantic search (CLAUDE.md)."""
    assert Settings(_env_file=None).embedding_dimension == 768


def test_jira_is_disabled_by_default() -> None:
    """Tier 0 and tier 1 must run the pipeline fully and create no tickets."""
    assert Settings(_env_file=None).jira_enabled is False


def test_cloud_sql_connection_name_blank_means_local() -> None:
    """ADR-015: db.py branches on this to pick its connection mode."""
    assert Settings(_env_file=None).cloud_sql_connection_name == ""


# ─── utils ────────────────────────────────────────────────────────────────────


def test_uuid5_id_is_deterministic() -> None:
    """The whole MERGE-not-CREATE strategy rests on this. Same input, same id,
    forever — including across processes and machines."""
    assert uuid5_id("meeting", "abc") == uuid5_id("meeting", "abc")


def test_uuid5_id_separates_namespaces() -> None:
    assert uuid5_id("meeting", "abc") != uuid5_id("person", "abc")


def test_uuid5_id_matches_the_value_v5_produces() -> None:
    """Pinned against v5's exact construction: a uuid5 of the namespace string
    under the DNS namespace, then a uuid5 of the value under THAT.

    Not `uuid5(NS, f"{namespace}:{value}")` — an easy and silent mistake to
    make, and it would fork every id in a restored graph so MERGE starts
    creating duplicates instead of matching.
    """
    import uuid

    ns = uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "meeting")
    assert uuid5_id("meeting", "abc") == str(uuid.uuid5(ns, "abc"))


def test_strip_json_fences_removes_a_fenced_block() -> None:
    """Local models wrap JSON in ```json fences despite being told not to.
    Found by live testing in v5, not by unit tests (CLAUDE.md)."""
    assert strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_json_fences_leaves_bare_json_alone() -> None:
    assert strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_strip_json_fences_on_empty_input() -> None:
    assert strip_json_fences("") == ""


def test_extract_ticket_keys_finds_jira_style_keys() -> None:
    assert extract_ticket_keys("fixes SCRUM-12 and PROJ-3") == ["SCRUM-12", "PROJ-3"]


def test_extract_ticket_keys_dedupes_preserving_order() -> None:
    assert extract_ticket_keys("SCRUM-12, PROJ-3, SCRUM-12") == ["SCRUM-12", "PROJ-3"]


def test_extract_ticket_keys_on_none_is_empty() -> None:
    assert extract_ticket_keys(None) == []


def test_priority_from_due_escalates_as_the_date_approaches() -> None:
    """v5's actual boundaries: <= 14 days high, <= 60 medium, beyond that low."""
    today = date.today()
    assert priority_from_due(today + timedelta(days=1)) == "high"
    assert priority_from_due(today + timedelta(days=14)) == "high"
    assert priority_from_due(today + timedelta(days=30)) == "medium"
    assert priority_from_due(today + timedelta(days=90)) == "low"


def test_priority_from_due_with_no_date_is_low() -> None:
    """Deliberately 'low', not 'medium' — an item with no due date is not
    urgent. Matches v5."""
    assert priority_from_due(None) == "low"


# ─── models (ADR-018) ─────────────────────────────────────────────────────────


def test_staged_record_carries_an_opaque_payload() -> None:
    """ADR-018: one table, JSONB payload, source_type as the discriminator."""
    rec = StagedRecord(
        id="1",
        source_id="gmail-abc",
        source_type="email",
        payload={"subject": "hi", "body": "there"},
        fetched_at="2026-08-20T00:00:00Z",
    )
    assert rec.processed is False
    assert rec.payload["subject"] == "hi"


def test_staged_record_rejects_an_unknown_source_type() -> None:
    """A typo'd source must fail loudly here, not silently skip the drain."""
    with pytest.raises(ValueError):
        StagedRecord(
            id="1",
            source_id="x",
            source_type="carrier-pigeon",  # type: ignore[arg-type]
            payload={},
            fetched_at="2026-08-20T00:00:00Z",
        )


def test_raw_models_survive_as_adapter_parse_targets() -> None:
    """ADR-018 is a storage change, not a loss of typing. The typed models
    still validate a payload as strictly as v5 did."""
    email = RawEmail.model_validate(
        {
            "id": "1",
            "source_id": "abc",
            "subject": "s",
            "from_email": "a@b.c",
            "to_emails": ["d@e.f"],
            "body": "b",
            "received_at": "2026-08-20T00:00:00Z",
        }
    )
    assert email.subject == "s"


def test_raw_models_no_longer_carry_source_table() -> None:
    """StagedRecord.source_type is the discriminator now. A lingering
    source_table field would be a second source of truth."""
    assert "source_table" not in RawEmail.model_fields


def test_airbyte_webhook_payload_is_gone() -> None:
    """MIGRATION_FROM_V5.md §4 — Airbyte residue must not be ported."""
    import meeting_notes.models as m

    assert not hasattr(m, "AirbyteWebhookPayload")


def test_decisions_accept_plain_strings() -> None:
    """LLM output sometimes gives decisions as bare strings. v5's coercion is
    load-bearing; dropping it would start raising on real extractions."""
    meeting = ExtractedMeeting.model_validate(
        {
            "title": "t",
            "kind": "meeting",
            "platform": "meet",
            "date": "2026-08-20",
            "summary": "s",
            "decisions": ["we shipped it"],
        }
    )
    assert meeting.decisions[0].text == "we shipped it"
    assert meeting.decisions[0].confidence == 1.0


def test_confidence_defaults_do_not_gate_unscored_items() -> None:
    """ActionItem/Decision default to 1.0 so items the model did not score are
    not silently dropped below JIRA_CONFIDENCE_THRESHOLD."""
    assert ActionItem(owner="a", task="t").confidence == 1.0
    assert Decision(text="d").confidence == 1.0


def test_extracted_meeting_ignores_unknown_fields() -> None:
    """CLAUDE.md mandates extra='ignore' — an LLM adding a field must not
    fail the whole extraction."""
    meeting = ExtractedMeeting.model_validate(
        {
            "title": "t",
            "kind": "meeting",
            "platform": "meet",
            "date": "2026-08-20",
            "summary": "s",
            "invented_field": "???",
        }
    )
    assert not hasattr(meeting, "invented_field")


# ─── classifier (no v5 tests existed) ─────────────────────────────────────────


def test_marketing_noise_short_circuits_to_zero() -> None:
    """Two or more noise markers return 0.0 immediately, before any positive
    signal is counted — a newsletter that happens to say 'meeting' and list
    attendees must not score its way past the threshold."""
    text = "Unsubscribe from our newsletter. Marketing meeting agenda, action item, deadline."
    assert classify(text, {"attendees": ["a@b.c"], "start_time": "10:00"}) == 0.0


def test_a_single_noise_marker_does_not_short_circuit() -> None:
    """The gate is >= 2. One stray 'unsubscribe' in a genuine thread is not
    enough to discard it."""
    assert classify("Standup agenda. Unsubscribe link at the bottom.", {}) > 0.0


def test_a_real_meeting_scores_above_the_default_threshold() -> None:
    """CLASSIFIER_SCORE_THRESHOLD defaults to 0.40."""
    text = (
        "Sprint planning meeting agenda. We decided to ship on Friday. "
        "Action item: alice@corp.com to review by the deadline. Duration 60 minutes."
    )
    score = classify(text, {"attendees": ["alice@corp.com", "bob@corp.com"], "start_time": "10:00"})
    assert score > 0.40


def test_unrelated_text_scores_below_the_threshold() -> None:
    assert classify("The parcel was delivered to your porch.", {}) < 0.40


def test_empty_text_scores_zero() -> None:
    assert classify("", {}) == 0.0


def test_score_never_exceeds_one() -> None:
    """Every signal is individually capped and the total is clamped. Without
    the clamp a keyword-dense email could exceed 1.0 and break any caller
    treating this as a probability."""
    text = (
        "meeting call standup sync review demo interview discussion workshop agenda "
        "action item todo deadline owner assigned to next step "
        "we decided we agreed approved going forward we will "
        "10:00 am duration 60 minutes hours "
        "a@b.com c@d.com e@f.com"
    )
    assert classify(text, {"attendees": ["x"], "start_time": "t", "end_time": "u"}) <= 1.0


def test_calendar_metadata_raises_the_score() -> None:
    """Signal 7: a record with real calendar times is more likely a meeting."""
    bare = classify("weekly sync", {})
    with_times = classify("weekly sync", {"start_time": "10:00", "end_time": "11:00"})
    assert with_times > bare


def test_attendees_raise_the_score() -> None:
    """Signal 2 accepts either a list or a count."""
    assert classify("weekly sync", {"attendees": ["a"]}) > classify("weekly sync", {})
    assert classify("weekly sync", {"attendees_count": 3}) > classify("weekly sync", {})


# ─── meeting type router ──────────────────────────────────────────────────────


def test_email_source_always_routes_to_email_thread() -> None:
    """Source type wins over any keyword in the subject."""
    assert route("sprint planning", source_type="email") == "email_thread"


def test_standup_is_matched_before_the_generic_review_keywords() -> None:
    """Order matters: 'session' lives in review's keywords and would otherwise
    swallow titles that are really standups."""
    assert route("daily standup session") == "standup"


def test_unmatched_titles_fall_back_to_general() -> None:
    assert route("misc") == "general"


def test_every_type_has_a_defined_hint() -> None:
    """A type missing from _HINTS would silently extract with no type-specific
    instruction. Note `general` maps to the empty string ON PURPOSE — it means
    'append nothing' — so this asserts the key exists, not that it is truthy."""
    from meeting_notes.meeting_type_router import _HINTS

    for meeting_type in TYPES:
        assert meeting_type in _HINTS


def test_specific_types_carry_real_instructions() -> None:
    """Everything except the deliberate `general` no-op must actually say
    something, or type routing buys nothing."""
    for meeting_type in TYPES:
        if meeting_type == "general":
            continue
        assert prompt_hint(meeting_type).strip()


def test_prompt_hint_is_safe_for_an_unknown_type() -> None:
    assert prompt_hint("not-a-type") == ""


def test_router_types_and_extracted_meeting_kind_are_deliberately_different() -> None:
    """These two vocabularies are NOT interchangeable and must not be merged.

    `ExtractedMeeting.kind` is what the LLM reports the meeting was.
    `route()` picks which extraction prompt to use. route() can return
    'planning', 'one_on_one' or 'general', none of which validate as a kind —
    so `meeting.kind = route(...)` raises. This test exists to make that
    failure appear here rather than in production.
    """
    import typing

    kinds = set(typing.get_args(ExtractedMeeting.model_fields["kind"].annotation))
    router_only = set(TYPES) - kinds

    assert router_only, "the vocabularies have been merged — see this test's docstring"
    assert {"planning", "one_on_one", "general"} <= router_only


# ─── dedup ────────────────────────────────────────────────────────────────────


def test_cosine_of_identical_vectors_is_one() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_of_orthogonal_vectors_is_zero() -> None:
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_handles_a_zero_vector_without_dividing_by_zero() -> None:
    """An all-zero embedding is what a failed embed() call looks like. It must
    return 0.0, not raise ZeroDivisionError inside the drain."""
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_handles_mismatched_lengths() -> None:
    """A dimension change (768 vs anything else) must not crash the pipeline."""
    assert cosine([1.0, 0.0], [1.0]) == 0.0


def test_identical_text_is_maximally_similar_without_embeddings() -> None:
    """Dedup must still work when embeddings are unavailable — the text path
    is the fallback, not an optimisation. Candidates are keyed on `task`."""
    assert similarity("deploy the api", None, {"task": "deploy the api"}) == 1.0


def test_text_similarity_ignores_case_and_whitespace() -> None:
    assert similarity("Deploy   The API", None, {"task": "deploy the api"}) == 1.0


def test_unrelated_text_is_not_similar() -> None:
    assert similarity("deploy the api", None, {"task": "order more coffee"}) < 0.9


def test_embeddings_take_precedence_over_text_when_both_sides_have_them() -> None:
    """Identical text but orthogonal embeddings must score by the embedding —
    otherwise the cheaper text path would silently win."""
    score = similarity("same words", [1.0, 0.0], {"task": "same words", "embedding": [0.0, 1.0]})
    assert score == 0.0


def test_best_match_returns_none_below_threshold() -> None:
    """Below threshold there is no duplicate, so jira_pusher opens a new ticket."""
    assert best_match("deploy the api", None, [{"task": "order more coffee"}], 0.9) is None


def test_best_match_returns_the_winner_with_its_score() -> None:
    """The caller needs the score to log why it deduped."""
    match = best_match(
        "deploy the api",
        None,
        [{"task": "order more coffee"}, {"task": "deploy the api", "jira_key": "SCRUM-1"}],
        0.9,
    )
    assert match is not None
    assert match["jira_key"] == "SCRUM-1"
    assert match["score"] == 1.0


def test_best_match_on_no_candidates_is_none() -> None:
    assert best_match("anything", None, [], 0.9) is None


# ─── person resolver ──────────────────────────────────────────────────────────


def test_normalize_email_lowercases_and_strips() -> None:
    assert normalize_email("  Alice@Corp.COM ") == "alice@corp.com"


def test_normalize_email_drops_plus_tags() -> None:
    """alice+jira@corp.com and alice@corp.com are one person. Not collapsing
    them is how v5 grew duplicate Person nodes and split its PageRank."""
    assert normalize_email("alice+jira@corp.com") == "alice@corp.com"


def test_normalize_email_on_none_is_empty() -> None:
    assert normalize_email(None) == ""


def test_email_match_beats_fuzzy_name_match() -> None:
    """Deterministic resolution first, probabilistic second (CLAUDE.md).
    An exact roster email must never lose to a similar-looking name."""
    roster = Roster(
        [
            RosterEntry(name="Alice Smith", email="alice@corp.com", tracked=True),
            RosterEntry(name="Alicia Smyth", email="alicia@corp.com"),
        ]
    )
    res = resolve(Attendee(name="Alicia Smyth", email="alice@corp.com"), roster)
    assert res.name == "Alice Smith"
    assert res.reason == "roster-email"


def test_an_unresolvable_attendee_is_held_for_review_not_dropped() -> None:
    """Attendees are never silently dropped — an unresolved one becomes a
    PersonReview node downstream (CLAUDE.md)."""
    res = resolve(Attendee(name="Nobody Known"), Roster([]))
    assert res.status == "review"
    assert res.email is None


def test_an_unknown_email_still_resolves_to_the_normalized_address() -> None:
    """A real email that is simply not on the roster is a new person, not a
    review case."""
    res = resolve(Attendee(name="New Hire", email="New+tag@Corp.com"), Roster([]))
    assert res.status == "resolved"
    assert res.email == "new@corp.com"


def test_tracked_comes_from_the_matched_person_not_the_last_one_iterated() -> None:
    """Regression test for a real v5 bug found during this port.

    v5's tier-2 branch read `bool(p.get("tracked"))` where `p` is the leaked
    loop variable — the LAST entry in known_people, not the one that matched.
    `Person.tracked` is the governance gate: per-person analytics must filter
    on it, and naming individuals is opt-in (CLAUDE.md). So the bug could mark
    somebody tracked who never opted in, decided purely by list ordering.
    """
    known = [
        {"name": "Alice Smith", "email": "alice@corp.com", "tracked": True},
        {"name": "Zebedee Nomatch", "email": "zeb@corp.com", "tracked": False},
    ]
    res = resolve(Attendee(name="Alice Smith"), Roster([]), known_people=known)

    assert res.email == "alice@corp.com"
    assert res.tracked is True, "tracked was taken from the last iterated person, not the match"


def test_resolve_attendees_splits_resolved_from_review() -> None:
    roster = Roster([RosterEntry(name="Alice Smith", email="alice@corp.com")])
    resolved, reviews = resolve_attendees(
        [Attendee(name="Alice Smith", email="alice@corp.com"), Attendee(name="Ghost")],
        roster,
    )
    assert [r.name for r in resolved] == ["Alice Smith"]
    assert [r.name for r in reviews] == ["Ghost"]


def test_load_roster_takes_an_explicit_path_not_the_environment() -> None:
    """CLAUDE.md: nothing outside config.py reads os.environ. v5 read
    PERSON_ROSTER_PATH here directly."""
    import inspect

    from meeting_notes import person_resolver

    assert "path" in inspect.signature(person_resolver.load_roster).parameters
    # Check for the import rather than the string "os.environ": the module
    # docstring legitimately mentions it while explaining the change, and a
    # module cannot reach the environment without importing os.
    assert not re.search(r"^import os$", inspect.getsource(person_resolver), re.M)


def test_load_roster_with_no_path_is_empty_not_an_error() -> None:
    assert load_roster(None).entries == []


# ─── access control ───────────────────────────────────────────────────────────


def _policy(**people: Principal) -> dict[str, Principal]:
    return dict(people)


def test_parse_scope_accepts_the_four_shapes() -> None:
    assert parse_scope("all").kind == "all"
    assert parse_scope("org").kind == "org"
    assert parse_scope("team:platform") == Scope("team", "platform")
    assert parse_scope("project:SCRUM") == Scope("project", "SCRUM")


def test_parse_scope_rejects_garbage() -> None:
    """An unparseable scope must raise, not silently widen access."""
    with pytest.raises(ValueError):
        parse_scope("team:")
    with pytest.raises(ValueError):
        parse_scope("nonsense")


def test_a_member_cannot_reach_another_team() -> None:
    policy = _policy(bob=Principal(name="bob", role=MEMBER, team="platform"))
    with pytest.raises(AccessDenied):
        authorize("bob", "team:payments", policy=policy)


def test_a_member_can_reach_their_own_team() -> None:
    policy = _policy(bob=Principal(name="bob", role=MEMBER, team="platform"))
    assert authorize("bob", "team:platform", policy=policy) == Scope("team", "platform")


def test_a_member_cannot_reach_org_level() -> None:
    policy = _policy(bob=Principal(name="bob", role=MEMBER, team="platform"))
    with pytest.raises(AccessDenied):
        authorize("bob", "org", policy=policy)


def test_an_admin_can_reach_everything() -> None:
    policy = _policy(root=Principal(name="root", role=ADMIN))
    assert authorize("root", "team:payments", policy=policy)
    assert authorize("root", "all", policy=policy)


def test_an_unknown_principal_is_denied_not_defaulted() -> None:
    """Failing open here would hand a stranger whatever the default role is."""
    with pytest.raises(AccessDenied):
        authorize("nobody", "org", policy=_policy())


def test_a_lead_gets_aggregates_not_row_level_detail_at_org_scope() -> None:
    """The governance promise: aggregates are the default and naming
    individuals is opt-in (CLAUDE.md, Person.tracked)."""
    policy = _policy(lead=Principal(name="lead", role=LEAD, team="platform"))
    assert aggregates_only("lead", "org", policy=policy) is True


def test_an_admin_is_not_restricted_to_aggregates() -> None:
    policy = _policy(root=Principal(name="root", role=ADMIN))
    assert aggregates_only("root", "org", policy=policy) is False


def test_an_explicit_allow_list_beats_the_role_derived_rule() -> None:
    policy = _policy(
        bob=Principal(name="bob", role=MEMBER, team="platform", allowed_scopes=("team:payments",))
    )
    assert authorize("bob", "team:payments", policy=policy) == Scope("team", "payments")


def test_scope_predicate_filters_team_and_project_but_not_org() -> None:
    """This dict is injected into generated Cypher — an empty dict for org is
    deliberate (rollups filter later), not a missing filter."""
    assert scope_predicate(Scope("team", "platform")) == {"scope_team": "platform"}
    assert scope_predicate(Scope("project", "SCRUM")) == {"scope_project": "SCRUM"}
    assert scope_predicate(Scope("org")) == {}


def test_load_policy_takes_an_explicit_path_not_the_environment() -> None:
    """CLAUDE.md: nothing outside config.py reads os.environ."""
    import inspect

    from meeting_notes import access_control

    assert "path" in inspect.signature(access_control.load_policy).parameters
    assert not re.search(r"^import os$", inspect.getsource(access_control), re.M)


def test_load_policy_with_no_path_returns_the_in_code_default() -> None:
    policy = load_policy(None)
    assert policy
    assert all(isinstance(p, Principal) for p in policy.values())


# ─── meeting quality ──────────────────────────────────────────────────────────


def test_percentile_rank_of_the_maximum_is_one() -> None:
    assert percentile_rank(10.0, [1.0, 5.0, 10.0]) == 1.0


def test_percentile_rank_on_too_small_a_population_is_neutral() -> None:
    """A first-ever meeting has nothing to rank against. Returning a neutral
    0.5 is honest; returning 0.0 would punish it for being first."""
    assert percentile_rank(1.0, []) == 0.5
    assert percentile_rank(1.0, [3.0]) == 0.5


def test_missing_inputs_score_none_rather_than_zero() -> None:
    """None means 'not measurable', 0.0 means 'measured and bad'. Collapsing
    the two would drag composite scores down for meetings that simply lack
    attendance data."""
    assert score_attendance_ratio(None, 10) is None
    assert score_attendance_ratio(5, None) is None
    assert score_attendance_ratio(5, 0) is None
    assert score_action_completion(None, None) is None
    assert score_action_completion(3, 0) is None


def test_attendance_ratio_is_a_clamped_fraction() -> None:
    assert score_attendance_ratio(5, 10) == 0.5
    assert score_attendance_ratio(20, 10) == 1.0


def test_agenda_detection_distinguishes_absent_from_unmeasurable() -> None:
    """The whole None-vs-0.0 contract in one place: no text at all cannot be
    judged (None); prose that simply has no agenda was judged (0.0)."""
    assert score_agenda_present("Agenda:\n1. budget\n2. hiring") == 1.0
    assert score_agenda_present("hey, are we still on for later?") == 0.0
    assert score_agenda_present("") is None
    assert score_agenda_present("   ") is None
    assert score_agenda_present(None) is None


def test_composite_ignores_missing_components_and_renormalizes() -> None:
    """A meeting missing one signal is scored on the rest, not penalised."""
    both = composite_quality({"attendance_ratio": 1.0, "action_completion": 1.0})
    one = composite_quality({"attendance_ratio": 1.0, "action_completion": None})
    assert both == 1.0
    assert one == 1.0


def test_composite_with_no_data_at_all_is_none_not_zero() -> None:
    """Honest 'insufficient data'. Scoring it 0.0 would rank a meeting we know
    nothing about below one we know was bad."""
    assert composite_quality({"attendance_ratio": None}) is None
    assert composite_quality({}) is None


def test_recurrence_health_needs_a_series() -> None:
    assert score_recurrence_health([0.5]) is None
    assert score_recurrence_health([]) is None


def test_a_declining_series_scores_below_its_mean() -> None:
    declining = score_recurrence_health([0.9, 0.7, 0.5])
    improving = score_recurrence_health([0.5, 0.7, 0.9])
    assert declining is not None and improving is not None
    assert declining < improving


def test_top_and_bottom_ignores_unscored_meetings() -> None:
    """Meetings with insufficient data must not appear in a leaderboard at
    either end — they are unknown, not bad."""
    ranked = top_and_bottom(
        [
            {"id": "a", "quality_score": 0.9},
            {"id": "b", "quality_score": 0.1},
            {"id": "c", "quality_score": None},
        ],
        k=5,
    )
    assert [m["id"] for m in ranked["lowest"]] == ["b", "a"]
    assert [m["id"] for m in ranked["highest"]] == ["a", "b"]
    assert all(m["id"] != "c" for m in ranked["lowest"] + ranked["highest"])

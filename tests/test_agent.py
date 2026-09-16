"""Tests for the controls, not for the model.

Each test here corresponds to a claim the assessment makes. If a test fails,
the corresponding sentence in the assessment is false, which is the point: the
document should not be able to drift from the code without something going red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.document import Document, normalise  # noqa: E402
from agent.guardrails import (  # noqa: E402
    ActionTier,
    Approval,
    CitationCheck,
    GuardrailError,
    RunBudget,
    ToolAllowlist,
    Tier,
)
from agent.loop import AgentRun  # noqa: E402
from agent.providers import ReplayProvider  # noqa: E402
from agent.tools import TOOL_TIERS, Toolbox, rollback_run  # noqa: E402

REPORT = ROOT / "data" / "soc2_northwind_2026.md"
REQS = ROOT / "data" / "requirements.yaml"
REPLAY = ROOT / "data" / "replay" / "session_default.json"


@pytest.fixture
def document():
    return Document(REPORT)


@pytest.fixture
def requirements():
    return yaml.safe_load(REQS.read_text(encoding="utf-8"))


class StubProvider:
    """Emits scripted turns so a control can be tested deterministically."""

    name = "stub"
    model = "stub"

    def __init__(self, turns):
        self.turns = list(turns)
        self.index = 0
        self.seen_tools = None

    def create(self, system, messages, tools):
        self.seen_tools = tools
        if self.index >= len(self.turns):
            return {"stop_reason": "end_turn", "content": [], "usage": {}}
        turn = self.turns[self.index]
        self.index += 1
        turn.setdefault("usage", {"input_tokens": 10, "output_tokens": 10})
        return turn


def use(tid, name, **args):
    return {"type": "tool_use", "id": tid, "name": name, "input": args}


# ------------------------------------------------------------------ document
def test_sections_carry_page_numbers(document):
    section = document.get_section("cc6-2-access-provisioning-and-removal")
    assert section is not None
    assert section.page == 26
    assert "Exception noted" in section.body


def test_contains_survives_reflowed_whitespace(document):
    quote = "Northwind does not currently engage an independent\n   third   party"
    assert normalise(quote) == "northwind does not currently engage an independent third party"
    assert document.contains(quote)


def test_contains_rejects_invented_text(document):
    assert not document.contains(
        "Northwind engages an independent third party to perform penetration testing"
    )


def test_search_returns_located_snippets(document):
    hits = document.search("penetration test")
    assert hits
    assert all("page" in h and "section_id" in h for h in hits)


# ------------------------------------------------------------------ AC-1
def test_allowlist_rejects_unknown_tool():
    allowlist = ToolAllowlist(TOOL_TIERS)
    assert allowlist.check("read_section") is Tier.READ
    with pytest.raises(GuardrailError, match="AC-1"):
        allowlist.check("delete_register")


# ------------------------------------------------------------------ AC-2
def test_write_tier_requires_approval_and_declining_blocks_the_write(
    tmp_path, requirements
):
    turns = [
        {
            "stop_reason": "tool_use",
            "content": [
                use("t1", "read_section", section_id="3-8-security-testing"),
            ],
        },
        {
            "stop_reason": "tool_use",
            "content": [
                use(
                    "t2",
                    "record_finding",
                    requirement_id="R-04",
                    verdict="not_met",
                    rationale="Internal team only.",
                    citation=(
                        "Northwind does not currently engage an independent third "
                        "party to perform penetration testing."
                    ),
                    section_id="3-8-security-testing",
                )
            ],
        },
        {"stop_reason": "end_turn", "content": []},
    ]
    run = AgentRun(
        provider=StubProvider(turns),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        approver=lambda name, payload: Approval(False, "interactive", "declined"),
        verbose=False,
    )
    result = run.run()
    assert result["findings"] == []
    assert result["declined"] == ["R-04"]
    assert not result["complete"]


def test_auto_approve_is_recorded_as_such(tmp_path):
    tier = ActionTier(auto_approve=True)
    approval = tier.request("record_finding", {"requirement_id": "R-01"})
    assert approval.granted and approval.mode == "auto"


# ------------------------------------------------------------------ AC-3
def test_budget_stops_at_iteration_ceiling():
    budget = RunBudget(max_iterations=2)
    budget.tick()
    budget.tick()
    with pytest.raises(GuardrailError, match="AC-3"):
        budget.tick()


def test_budget_stops_at_token_ceiling():
    budget = RunBudget(max_tokens=100)
    budget.record_usage({"input_tokens": 90, "output_tokens": 30})
    with pytest.raises(GuardrailError, match="AC-3"):
        budget.tick()


def test_loop_halts_and_still_commits_what_it_had(tmp_path, requirements):
    turns = [
        {
            "stop_reason": "tool_use",
            "content": [use(f"t{i}", "search_report", query="access")],
        }
        for i in range(10)
    ]
    run = AgentRun(
        provider=StubProvider(turns),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        budget=RunBudget(max_iterations=3),
        auto_approve=True,
        verbose=False,
    )
    result = run.run()
    assert not result["complete"]
    assert "AC-3" in result["stopped_by"]


# ------------------------------------------------------------------ AC-4
def test_audit_log_records_every_call_and_survives_reread(tmp_path, requirements):
    run = AgentRun(
        provider=ReplayProvider(REPLAY),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        auto_approve=True,
        verbose=False,
    )
    result = run.run()
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert events[0] == "run_started"
    assert events[-1] == "run_finished"
    assert events.count("tool_executed") == 31
    assert events.count("approval_decision") == 10
    assert all(json.loads(line)["run_id"] == result["run_id"] for line in lines)


# ------------------------------------------------------------------ AC-5
def test_citation_must_exist_in_source(document):
    check = CitationCheck(document)
    check.check(
        "Northwind does not currently engage an independent third party to "
        "perform penetration testing.",
        "3-8-security-testing",
    )
    with pytest.raises(GuardrailError, match="AC-5"):
        check.check(
            "Northwind engages a qualified independent third party annually.",
            "3-8-security-testing",
        )


def test_citation_must_be_substantial(document):
    with pytest.raises(GuardrailError, match="AC-5"):
        CitationCheck(document).check("AES-256", "3-7-encryption-and-data-protection")


def test_hallucinated_citation_is_blocked_end_to_end(tmp_path, requirements):
    turns = [
        {
            "stop_reason": "tool_use",
            "content": [use("t1", "read_section", section_id="3-8-security-testing")],
        },
        {
            "stop_reason": "tool_use",
            "content": [
                use(
                    "t2",
                    "record_finding",
                    requirement_id="R-04",
                    verdict="met",
                    rationale="The report says testing is independent.",
                    citation=(
                        "Northwind engages a qualified independent third party to "
                        "perform annual penetration testing of the production "
                        "environment."
                    ),
                    section_id="3-8-security-testing",
                )
            ],
        },
        {"stop_reason": "end_turn", "content": []},
    ]
    run = AgentRun(
        provider=StubProvider(turns),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        auto_approve=True,
        verbose=False,
    )
    result = run.run()
    assert result["findings"] == []
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    ]
    assert "tool_blocked" in events
    assert not (tmp_path / "gap_register.csv").exists()


def test_finding_requires_the_section_to_have_been_read(tmp_path, requirements, document):
    box = Toolbox(document, requirements, "run-test", tmp_path)
    with pytest.raises(GuardrailError, match="has not been read"):
        box.record_finding(
            requirement_id="R-04",
            verdict="not_met",
            rationale="x",
            citation="Northwind does not currently engage an independent third party",
            section_id="3-8-security-testing",
        )


# ------------------------------------------------------------------ tools
def test_one_finding_per_requirement(tmp_path, requirements, document):
    box = Toolbox(document, requirements, "run-test", tmp_path)
    box.read_section("3-8-security-testing")
    args = dict(
        requirement_id="R-04",
        verdict="not_met",
        rationale="x",
        citation="Northwind does not currently engage an independent third party",
        section_id="3-8-security-testing",
    )
    box.record_finding(**args)
    with pytest.raises(GuardrailError, match="already has a finding"):
        box.record_finding(**args)


def test_unknown_verdict_and_unknown_requirement_are_rejected(
    tmp_path, requirements, document
):
    box = Toolbox(document, requirements, "run-test", tmp_path)
    box.read_section("3-8-security-testing")
    with pytest.raises(GuardrailError, match="not permitted"):
        box.record_finding("R-04", "looks_fine", "x", "y" * 30, "3-8-security-testing")
    with pytest.raises(GuardrailError, match="not a requirement"):
        box.record_finding("R-99", "met", "x", "y" * 30, "3-8-security-testing")


def test_cannot_finish_with_requirements_unassessed(tmp_path, requirements, document):
    box = Toolbox(document, requirements, "run-test", tmp_path)
    with pytest.raises(GuardrailError, match="cannot finish"):
        box.finish_review("done")


# ------------------------------------------------------------------ AC-6
def test_rollback_removes_only_that_run(tmp_path, requirements):
    for _ in range(2):
        AgentRun(
            provider=ReplayProvider(REPLAY),
            document_path=REPORT,
            requirements=requirements,
            out_dir=tmp_path,
            auto_approve=True,
            verbose=False,
        ).run()

    import csv

    register = tmp_path / "gap_register.csv"
    rows = list(csv.DictReader(register.open(encoding="utf-8")))
    assert len(rows) == 20
    target = rows[0]["run_id"]

    removed = rollback_run(tmp_path, target)
    assert removed == 10

    remaining = list(csv.DictReader(register.open(encoding="utf-8")))
    assert len(remaining) == 10
    assert all(r["run_id"] != target for r in remaining)

    # the audit log still records what the rolled back run did
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert target in audit


# ------------------------------------------------------------------ end to end
def test_replay_run_assesses_every_requirement(tmp_path, requirements):
    run = AgentRun(
        provider=ReplayProvider(REPLAY),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        auto_approve=True,
        verbose=False,
    )
    result = run.run()
    assert result["complete"]
    ids = [f["requirement_id"] for f in result["findings"]]
    assert ids == [f"R-{i:02d}" for i in range(1, 11)]
    assert {f["verdict"] for f in result["findings"]} == {
        "met",
        "partially_met",
        "not_met",
        "not_covered",
        "user_entity_control",
    }
    document = Document(REPORT)
    for finding in result["findings"]:
        assert document.contains(finding["citation"])
        assert finding["page"]


def test_tool_schemas_match_implemented_methods(requirements, document, tmp_path):
    run = AgentRun(
        provider=StubProvider([{"stop_reason": "end_turn", "content": []}]),
        document_path=REPORT,
        requirements=requirements,
        out_dir=tmp_path,
        verbose=False,
    )
    names = {s["name"] for s in run.schemas}
    assert names == set(TOOL_TIERS)
    for name in names:
        assert callable(getattr(run.toolbox, name))

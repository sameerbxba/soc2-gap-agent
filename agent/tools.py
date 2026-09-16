"""Tool definitions and their implementations.

Six tools. Four read, one writes, one ends the run. The schemas are the
contract the model sees; the Toolbox methods are what actually executes. The
split matters because the schema is also the thing the assessment describes,
and a schema that drifts from the implementation is exactly the finding this
project exists to make.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .guardrails import GuardrailError, Tier

TOOL_TIERS = {
    "list_report_sections": Tier.READ,
    "read_section": Tier.READ,
    "search_report": Tier.READ,
    "get_requirements": Tier.READ,
    "record_finding": Tier.WRITE,
    "finish_review": Tier.TERMINAL,
}

REGISTER_FIELDS = [
    "run_id",
    "requirement_id",
    "requirement_title",
    "verdict",
    "rationale",
    "citation",
    "section_id",
    "page",
    "approved_by",
]


def tool_schemas(allowed_verdicts: list[str]) -> list[dict]:
    return [
        {
            "name": "list_report_sections",
            "description": (
                "List every section of the vendor report with its id, title and "
                "page number. Call this first to see what the report contains."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "read_section",
            "description": (
                "Return the full text of one section of the vendor report. Use "
                "this before recording any finding that depends on that section."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "section_id": {
                        "type": "string",
                        "description": "Section id from list_report_sections.",
                    }
                },
                "required": ["section_id"],
            },
        },
        {
            "name": "search_report",
            "description": (
                "Keyword search across the vendor report. Returns located "
                "snippets with section id and page number."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Words to search for, e.g. 'penetration test'.",
                    }
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_requirements",
            "description": (
                "Return the receiving organisation's control requirements that "
                "the vendor report is being assessed against."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "record_finding",
            "description": (
                "Record one assessed requirement in the gap register. This is a "
                "write action: it requires human approval and the citation must "
                "be text quoted verbatim from the report. Record exactly one "
                "finding per requirement."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "requirement_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": allowed_verdicts},
                    "rationale": {
                        "type": "string",
                        "description": (
                            "Two or three sentences. State what the report shows "
                            "and what that means for the requirement. If the "
                            "verdict is anything other than met, say what the "
                            "receiving organisation now has to do."
                        ),
                    },
                    "citation": {
                        "type": "string",
                        "description": (
                            "Text quoted verbatim from the report, at least 25 "
                            "characters. Checked by string comparison against the "
                            "source. Paraphrase is rejected."
                        ),
                    },
                    "section_id": {"type": "string"},
                },
                "required": [
                    "requirement_id",
                    "verdict",
                    "rationale",
                    "citation",
                    "section_id",
                ],
            },
        },
        {
            "name": "finish_review",
            "description": (
                "End the review. Call this only after every requirement has a "
                "recorded finding. Provide a short summary for the reviewer."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Three to five sentences for a human reviewer.",
                    }
                },
                "required": ["summary"],
            },
        },
    ]


class Toolbox:
    def __init__(self, document, requirements: dict, run_id: str, out_dir: Path):
        self.document = document
        self.requirements = requirements
        self.run_id = run_id
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.findings: list[dict] = []
        self.sections_read: set[str] = set()
        self.summary: str | None = None

    # -------------------------------------------------- read tier
    def list_report_sections(self) -> dict:
        return {"sections": self.document.list_sections()}

    def read_section(self, section_id: str) -> dict:
        section = self.document.get_section(section_id)
        if section is None:
            raise GuardrailError(
                f"no section '{section_id}'. Call list_report_sections for valid ids."
            )
        self.sections_read.add(section_id)
        return {
            "section_id": section.id,
            "title": section.title,
            "page": section.page,
            "text": section.body,
        }

    def search_report(self, query: str) -> dict:
        hits = self.document.search(query)
        return {"query": query, "hits": hits, "hit_count": len(hits)}

    def get_requirements(self) -> dict:
        return {
            "organisation": self.requirements.get("organisation"),
            "standard": self.requirements.get("standard"),
            "fiscal_year_end": self.requirements.get("fiscal_year_end"),
            "allowed_verdicts": self.requirements.get("allowed_verdicts", []),
            "requirements": self.requirements.get("requirements", []),
        }

    # -------------------------------------------------- write tier
    def record_finding(
        self,
        requirement_id: str,
        verdict: str,
        rationale: str,
        citation: str,
        section_id: str,
        approved_by: str = "unknown",
    ) -> dict:
        known = {r["id"] for r in self.requirements.get("requirements", [])}
        if requirement_id not in known:
            raise GuardrailError(
                f"'{requirement_id}' is not a requirement in this standard."
            )
        if any(f["requirement_id"] == requirement_id for f in self.findings):
            raise GuardrailError(
                f"{requirement_id} already has a finding in this run. "
                "Record one finding per requirement."
            )
        allowed = self.requirements.get("allowed_verdicts", [])
        if verdict not in allowed:
            raise GuardrailError(
                f"verdict '{verdict}' is not permitted. Use one of: {', '.join(allowed)}."
            )
        if section_id not in self.sections_read:
            raise GuardrailError(
                f"AC-5: section '{section_id}' has not been read in this run. "
                "Call read_section before recording a finding against it."
            )

        title = next(
            r["title"]
            for r in self.requirements["requirements"]
            if r["id"] == requirement_id
        )
        section = self.document.get_section(section_id)
        finding = {
            "run_id": self.run_id,
            "requirement_id": requirement_id,
            "requirement_title": title,
            "verdict": verdict,
            "rationale": rationale.strip(),
            "citation": citation.strip(),
            "section_id": section_id,
            "page": section.page if section else "",
            "approved_by": approved_by,
        }
        self.findings.append(finding)
        return {
            "recorded": requirement_id,
            "verdict": verdict,
            "page": finding["page"],
            "findings_so_far": len(self.findings),
            "remaining": sorted(known - {f["requirement_id"] for f in self.findings}),
        }

    # -------------------------------------------------- terminal
    def finish_review(self, summary: str) -> dict:
        known = {r["id"] for r in self.requirements.get("requirements", [])}
        assessed = {f["requirement_id"] for f in self.findings}
        missing = sorted(known - assessed)
        if missing:
            raise GuardrailError(
                "cannot finish: no finding recorded for " + ", ".join(missing) + "."
            )
        self.summary = summary.strip()
        return {"status": "complete", "findings": len(self.findings)}

    # -------------------------------------------------- persistence
    def register_path(self) -> Path:
        return self.out_dir / "gap_register.csv"

    def commit_register(self) -> Path:
        path = self.register_path()
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=REGISTER_FIELDS)
            if not exists:
                writer.writeheader()
            for finding in self.findings:
                writer.writerow(finding)
        return path


def rollback_run(out_dir: Path, run_id: str) -> int:
    """AC-6: remove every row this run wrote to the register.

    The audit log is never touched. Reversing what the agent did and erasing
    the record that it did it are different operations, and only one of them is
    something an operator should be able to do.
    """
    path = Path(out_dir) / "gap_register.csv"
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    keep = [r for r in rows if r.get("run_id") != run_id]
    removed = len(rows) - len(keep)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REGISTER_FIELDS)
        writer.writeheader()
        writer.writerows(keep)
    return removed

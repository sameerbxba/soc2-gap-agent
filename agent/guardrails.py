"""The five controls, as enforced code rather than as policy text.

Each class here corresponds to a control in the accompanying risk assessment.
They are separated from the tools on purpose: a tool should not be trusted to
police itself, and a reviewer should be able to read the whole control surface
in one file without reading the business logic.

AC-1  ToolAllowlist       declared capability surface
AC-2  ActionTier          read executes, write requires a human
AC-3  RunBudget           iteration, token and wall-clock ceilings
AC-4  AuditLog            in audit.py, append-only
AC-5  CitationCheck       a finding must quote text that exists in the source
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class GuardrailError(Exception):
    """Raised when the agent attempts something outside its authority.

    Caught by the loop and returned to the model as a tool error, so refusal is
    a normal part of the conversation rather than a crash. The model gets to
    see why it was stopped and try a permitted route instead.
    """


class Tier(str, Enum):
    READ = "read"
    WRITE = "write"
    TERMINAL = "terminal"


# ---------------------------------------------------------------- AC-1
class ToolAllowlist:
    """The agent may call these tools and no others.

    An agent's real capability surface is whatever its tools can reach, not
    whatever its prompt says it does. This list is that surface, declared in
    one place so the assessment can describe it accurately.
    """

    def __init__(self, allowed: dict[str, Tier]):
        self.allowed = dict(allowed)

    def check(self, name: str) -> Tier:
        if name not in self.allowed:
            raise GuardrailError(
                f"AC-1: tool '{name}' is not on the allowlist. "
                f"Permitted tools: {', '.join(sorted(self.allowed))}."
            )
        return self.allowed[name]


# ---------------------------------------------------------------- AC-2
@dataclass
class Approval:
    granted: bool
    mode: str
    note: str = ""


class ActionTier:
    """Read actions run. Write actions stop and ask a person.

    This is the difference between a tool and an agent. The moment the thing
    can change state, the interesting governance question is not accuracy but
    authority, and authority has to be granted per action or the audit trail is
    describing a decision nobody made.
    """

    def __init__(self, approver=None, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self.approver = approver or self._prompt

    def request(self, tool_name: str, payload: dict) -> Approval:
        if self.auto_approve:
            return Approval(True, "auto", "approval suppressed by --approve-all")
        return self.approver(tool_name, payload)

    @staticmethod
    def _prompt(tool_name: str, payload: dict) -> Approval:
        print("\n  ── approval required ──────────────────────────────")
        print(f"  the agent wants to call: {tool_name}")
        for k, v in payload.items():
            text = str(v)
            if len(text) > 300:
                text = text[:300] + " ..."
            print(f"    {k}: {text}")
        answer = input("  approve? [y/N] ").strip().lower()
        granted = answer in {"y", "yes"}
        return Approval(granted, "interactive", "" if granted else "declined by operator")


# ---------------------------------------------------------------- AC-3
@dataclass
class RunBudget:
    """Ceilings on the loop.

    An agent without a stopping condition is a billing incident waiting to
    happen, and more importantly it removes the operator's ability to say how
    much the system is allowed to do before someone looks at it.
    """

    max_iterations: int = 30
    max_tokens: int = 200_000
    max_seconds: int = 300

    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def tick(self) -> None:
        self.iterations += 1
        if self.iterations > self.max_iterations:
            raise GuardrailError(
                f"AC-3: iteration ceiling reached ({self.max_iterations})."
            )
        if self.elapsed > self.max_seconds:
            raise GuardrailError(
                f"AC-3: wall clock ceiling reached ({self.max_seconds}s)."
            )
        if self.total_tokens > self.max_tokens:
            raise GuardrailError(
                f"AC-3: token ceiling reached ({self.max_tokens})."
            )

    def record_usage(self, usage: dict) -> None:
        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage.get("output_tokens", 0) or 0)

    def snapshot(self) -> dict:
        return {
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_seconds": round(self.elapsed, 2),
        }


# ---------------------------------------------------------------- AC-5
MIN_CITATION_CHARS = 25


class CitationCheck:
    """A finding must quote the source, and the quote must actually be there.

    This is the control that does the most work. The model can reason however
    it likes, but it cannot enter a finding into the register without attaching
    a span of text that appears verbatim in the report, checked by string
    comparison rather than by asking the model whether it was being careful.

    It does not make the reasoning correct. It makes the reasoning checkable,
    which is a smaller claim and the only one the code can support.
    """

    def __init__(self, document):
        self.document = document

    def check(self, citation: str, section_id: str | None = None) -> None:
        if not citation or len(citation.strip()) < MIN_CITATION_CHARS:
            raise GuardrailError(
                f"AC-5: citation must be at least {MIN_CITATION_CHARS} characters "
                "of text quoted from the report."
            )
        if not self.document.contains(citation):
            raise GuardrailError(
                "AC-5: the quoted citation does not appear in the source document. "
                "Quote the report exactly. Do not paraphrase, and do not quote "
                "text you have not read through read_section or search_report."
            )
        if section_id:
            section = self.document.get_section(section_id)
            if section is None:
                raise GuardrailError(
                    f"AC-5: section '{section_id}' does not exist in this document."
                )

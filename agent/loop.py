"""The agent loop.

This is the whole concept, and it is about a hundred lines. A model, a set of
tools, a loop, and a stopping condition. Everything in this project that is not
this file is either a tool, a control on the loop, or a record of what it did.

    send messages with a tools array
      -> model returns a tool_use block instead of text
      -> execute the tool, send back a tool_result block
      -> repeat until the model stops or a control stops it

Every guardrail decision happens between the model asking and the tool running.
That is the only place it can happen, and it is why the loop is written out
here rather than delegated to a framework.
"""

from __future__ import annotations

import json
from pathlib import Path

from .audit import AuditLog, digest, new_run_id
from .document import Document
from .guardrails import (
    ActionTier,
    CitationCheck,
    GuardrailError,
    RunBudget,
    ToolAllowlist,
    Tier,
)
from .tools import TOOL_TIERS, Toolbox, tool_schemas

SYSTEM_PROMPT = """You review a vendor's SOC 2 report against the receiving \
organisation's own control requirements, and you record one finding per \
requirement.

How to work:

1. Call get_requirements and list_report_sections before anything else.
2. For each requirement, find the relevant part of the report using \
search_report, then read the section in full with read_section. Do not record a \
finding against a section you have not read.
3. Record the finding with record_finding, quoting the report verbatim in the \
citation field. The citation is checked by string comparison against the source \
document. A paraphrase will be rejected and you will have to try again.
4. When every requirement has a finding, call finish_review.

How to judge:

- A SOC 2 report is evidence about the vendor's controls, not about yours. \
Where the report says a criterion depends on a complementary user entity \
control, the requirement is met only if the receiving organisation operates \
that control, so the verdict is user_entity_control and the rationale says what \
the receiving organisation now has to do.
- Controls of a carved-out subservice organisation are not covered by this \
report, however well they are described in it.
- A category that is out of scope is not a failure by the vendor. It is an \
absence of evidence, and the verdict is not_covered.
- Design described in the system description is not the same as operating \
effectiveness tested in the test matrix. If a control is described but not \
tested, say so, and do not treat the description as the evidence.
- An exception noted in the test matrix means the control did not operate \
throughout the period. Management's response to an exception is management's \
assertion and is not covered by the auditor's opinion. Say which one you are \
relying on.
- The examination period is a fact about what the report can support. If it \
ends before the receiving organisation's fiscal year end, the gap is a finding \
in its own right.

Be specific and be short. Every rationale is read by someone who has to act on \
it."""

TASK_PROMPT = """Review the vendor SOC 2 report against every requirement in \
the standard, and record a finding for each one. There are {n} requirements. \
Work through them in order."""


class AgentRun:
    def __init__(
        self,
        provider,
        document_path: str | Path,
        requirements: dict,
        out_dir: str | Path = "out",
        budget: RunBudget | None = None,
        auto_approve: bool = False,
        approver=None,
        operator: str = "operator",
        verbose: bool = True,
    ):
        self.run_id = new_run_id()
        self.provider = provider
        self.document = Document(document_path)
        self.requirements = requirements
        self.out_dir = Path(out_dir)
        self.budget = budget or RunBudget()
        self.verbose = verbose
        self.operator = operator

        self.allowlist = ToolAllowlist(TOOL_TIERS)
        self.tier = ActionTier(approver=approver, auto_approve=auto_approve)
        self.citations = CitationCheck(self.document)
        self.toolbox = Toolbox(
            self.document, requirements, self.run_id, self.out_dir
        )
        self.log = AuditLog(self.out_dir / "audit.jsonl", self.run_id)
        self.schemas = tool_schemas(requirements.get("allowed_verdicts", []))
        self.declined: list[str] = []
        self.stopped_by: str | None = None

    # ------------------------------------------------------------------
    def say(self, text: str) -> None:
        if self.verbose:
            print(text)

    def run(self) -> dict:
        self.log.write(
            "run_started",
            provider=self.provider.name,
            model=getattr(self.provider, "model", "unknown"),
            document=str(self.document.path),
            document_digest=digest(self.document.raw),
            standard=self.requirements.get("standard"),
            requirement_count=len(self.requirements.get("requirements", [])),
            budget={
                "max_iterations": self.budget.max_iterations,
                "max_tokens": self.budget.max_tokens,
                "max_seconds": self.budget.max_seconds,
            },
            approval_mode="auto" if self.tier.auto_approve else "interactive",
        )
        self.say(f"\nrun {self.run_id}  ({self.provider.name})")
        self.say(f"document: {self.document.path.name}")
        self.say(f"standard: {self.requirements.get('standard')}\n")

        messages: list[dict] = [
            {
                "role": "user",
                "content": TASK_PROMPT.format(
                    n=len(self.requirements.get("requirements", []))
                ),
            }
        ]

        while True:
            try:
                self.budget.tick()
            except GuardrailError as exc:
                self.stopped_by = str(exc)
                self.log.write("run_halted", reason=str(exc), control="AC-3")
                self.say(f"\n  halted: {exc}")
                break

            turn = self.provider.create(SYSTEM_PROMPT, messages, self.schemas)
            self.budget.record_usage(turn.get("usage", {}))
            content = turn.get("content", [])
            messages.append({"role": "assistant", "content": content})

            for block in content:
                if block.get("type") == "text" and block.get("text", "").strip():
                    self.log.write("model_text", text=block["text"][:2000])

            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            if not tool_uses:
                self.stopped_by = f"model stopped ({turn.get('stop_reason')})"
                self.log.write(
                    "run_halted",
                    reason=self.stopped_by,
                    control="none",
                )
                self.say(f"\n  model stopped without finishing the review.")
                break

            results = [self._invoke(b) for b in tool_uses]
            messages.append({"role": "user", "content": results})

            if self.toolbox.summary is not None:
                break

        return self._finalise()

    # ------------------------------------------------------------------
    def _invoke(self, block: dict) -> dict:
        name = block.get("name", "")
        args = block.get("input", {}) or {}
        self.log.write("tool_requested", tool=name, arguments=args)

        try:
            tier = self.allowlist.check(name)

            if tier is Tier.WRITE:
                # Validate before asking a human. Nobody should be asked to
                # approve a write that the controls will reject anyway.
                if name == "record_finding":
                    self.citations.check(
                        args.get("citation", ""), args.get("section_id")
                    )
                approval = self.tier.request(name, args)
                self.log.write(
                    "approval_decision",
                    tool=name,
                    granted=approval.granted,
                    mode=approval.mode,
                    note=approval.note,
                    requirement_id=args.get("requirement_id"),
                )
                if not approval.granted:
                    self.declined.append(args.get("requirement_id", name))
                    raise GuardrailError(
                        "AC-2: the operator declined this write. Do not retry it. "
                        "Move on to the next requirement."
                    )
                args = {**args, "approved_by": f"{self.operator}:{approval.mode}"}

            method = getattr(self.toolbox, name)
            result = method(**args)

        except GuardrailError as exc:
            self.log.write(
                "tool_blocked", tool=name, control=str(exc).split(":")[0], reason=str(exc)
            )
            self.say(f"  blocked  {name}: {exc}")
            return {
                "type": "tool_result",
                "tool_use_id": block.get("id"),
                "is_error": True,
                "content": str(exc),
            }
        except TypeError as exc:
            self.log.write("tool_error", tool=name, reason=str(exc))
            return {
                "type": "tool_result",
                "tool_use_id": block.get("id"),
                "is_error": True,
                "content": f"invalid arguments for {name}: {exc}",
            }

        self.log.write(
            "tool_executed",
            tool=name,
            tier=tier.value,
            result_digest=digest(result),
            requirement_id=args.get("requirement_id"),
            verdict=args.get("verdict"),
        )
        if name == "record_finding":
            self.say(
                f"  recorded {args['requirement_id']}  {args['verdict']}"
                f"  (p.{result.get('page')})"
            )
        elif name == "read_section":
            self.say(f"  read     {args.get('section_id')}")
        elif name == "search_report":
            self.say(f"  searched '{args.get('query')}'")

        return {
            "type": "tool_result",
            "tool_use_id": block.get("id"),
            "content": json.dumps(result, default=str),
        }

    # ------------------------------------------------------------------
    def _finalise(self) -> dict:
        complete = self.toolbox.summary is not None
        register = None
        if self.toolbox.findings:
            register = self.toolbox.commit_register()
            self.log.write(
                "register_committed",
                path=str(register),
                rows=len(self.toolbox.findings),
            )

        self.log.write(
            "run_finished",
            complete=complete,
            findings=len(self.toolbox.findings),
            declined=self.declined,
            stopped_by=self.stopped_by,
            usage=self.budget.snapshot(),
        )

        return {
            "run_id": self.run_id,
            "complete": complete,
            "summary": self.toolbox.summary,
            "findings": self.toolbox.findings,
            "declined": self.declined,
            "stopped_by": self.stopped_by,
            "register": str(register) if register else None,
            "audit_log": str(self.log.path),
            "usage": self.budget.snapshot(),
        }

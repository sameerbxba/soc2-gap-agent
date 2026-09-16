# Control matrix

Each control below is stated the way it would be stated in an assessment, then
mapped to the code that enforces it and the test that proves it does. The
column that matters is the last one: a control with no test is a claim, not a
control.

| id | control statement | type | implementation | test |
|---|---|---|---|---|
| AC-1 | The agent may invoke only tools on a declared allowlist. Any other tool call is refused and logged. | Preventive | `agent/guardrails.py` `ToolAllowlist.check`, applied in `loop.AgentRun._invoke` | `test_allowlist_rejects_unknown_tool`, and end to end in the tampered session |
| AC-2 | Tools that change state require explicit human approval of that specific call. Approval is requested per action, never per run. | Preventive | `agent/guardrails.py` `ActionTier.request`; tiers declared in `tools.TOOL_TIERS` | `test_write_tier_requires_approval_and_declining_blocks_the_write` |
| AC-2a | Where approval is suppressed, the suppression is recorded rather than hidden. | Detective | `ActionTier.request` returns `mode="auto"`; `loop` writes `approval_decision` | `test_auto_approve_is_recorded_as_such` |
| AC-3 | The loop halts at a declared ceiling on iterations, cumulative tokens, or wall-clock time. | Preventive | `agent/guardrails.py` `RunBudget.tick` | `test_budget_stops_at_iteration_ceiling`, `test_budget_stops_at_token_ceiling`, `test_loop_halts_and_still_commits_what_it_had` |
| AC-4 | Every tool call, argument, control decision and approval is written to an append-only log before the result returns to the model. | Detective | `agent/audit.py` `AuditLog.write`, opened in append mode and fsynced per record | `test_audit_log_records_every_call_and_survives_reread` |
| AC-5 | A finding may not be recorded unless its citation appears verbatim in the source document and the cited section was read in the same run. | Preventive | `agent/guardrails.py` `CitationCheck.check` plus the read-before-write check in `tools.Toolbox.record_finding` | `test_citation_must_exist_in_source`, `test_citation_must_be_substantial`, `test_hallucinated_citation_is_blocked_end_to_end`, `test_finding_requires_the_section_to_have_been_read` |
| AC-6 | An operator can reverse everything a run wrote to the register. The reversal does not alter the audit log. | Corrective | `agent/tools.py` `rollback_run`, `cli` `rollback` | `test_rollback_removes_only_that_run` |
| AC-7 | The register accepts one finding per requirement, from a closed set of verdicts, against a known requirement id. | Preventive | `tools.Toolbox.record_finding`, plus the `enum` on the tool schema | `test_one_finding_per_requirement`, `test_unknown_verdict_and_unknown_requirement_are_rejected` |
| AC-8 | The run cannot be declared complete while any requirement is unassessed. | Detective | `tools.Toolbox.finish_review` | `test_cannot_finish_with_requirements_unassessed` |
| AC-9 | The tool schemas presented to the model match the methods that execute. | Detective | asserted in test rather than enforced at runtime | `test_tool_schemas_match_implemented_methods` |

## Where the controls do not reach

Listed here rather than omitted, because the gap between what a control does
and what it is assumed to do is the thing worth writing down.

**AC-2 depends on a human.** The control moves the decision to a person; it
does not make the person read it. `--approve-all` removes it entirely, and AC-2a
only records that this happened. In any real deployment the approval would need
to be a named individual with a reason captured, not a keypress.

**AC-5 proves grounding, not correctness.** A verbatim quote can support a
wrong conclusion, and nothing in the code evaluates the reasoning between the
quote and the verdict. The claim the control supports is narrow: a reviewer can
verify any finding against the source in seconds.

**Nothing here detects an omission.** Every control operates on what the agent
did. If the agent never searches for the right section, no control fires,
because nothing was attempted. AC-8 catches a missing finding, but not a
finding that is present and shallow. This is the largest residual risk in the
system and the hardest to control for.

**The audit log is append-only by convention, not by permission.** The process
writes it and could overwrite it. On a real deployment it would belong on
write-once storage or be shipped to a log platform the agent has no credentials
for.

**AC-9 is asserted, not enforced.** Schema and implementation are checked in a
test rather than generated from one source, so they can diverge between test
runs. Generating the schemas from the method signatures would close this.

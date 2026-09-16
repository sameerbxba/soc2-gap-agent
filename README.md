# SOC 2 control-gap agent

An agent that reads a vendor's SOC 2 report, assesses it against a receiving
organisation's own control requirements, and records one cited finding per
requirement in a gap register. It cannot write anything without a human
approving that specific write, and it cannot record a finding without quoting
text that actually exists in the source document.

The interesting part is not that it reads the report. It is what it is stopped
from doing.

```
git clone <this repo> && cd soc2-gap-agent
pip install -r requirements.txt
python -m agent.cli run --replay --approve-all
```

That runs the full agent loop end to end with no API key and no cost, from a
recorded session. Drop `--approve-all` to approve each of the ten writes
yourself.

---

## Why this exists

NIST AI RMF and ISO/IEC 42001 were written for models that produce outputs.
An agent takes actions, and the governance questions change:

- what tools is it allowed to call
- what may it do without a human
- what stops it running forever
- what did it actually do, in order
- how do you reverse something it did

This project is an attempt to answer those five questions in code rather than
in a policy document, on a task where getting it wrong has consequences.

---

## What it does

`data/soc2_northwind_2026.md` is a synthetic SOC 2 Type 2 report for a vendor
that does not exist. It contains conditions a real reviewer has to catch:

- a tested **exception** at CC6.2, with a management response that sits in the
  unaudited section of the report
- **AWS carved out** as a subservice organisation
- **Availability out of scope**, so backup restoration is never tested
- **encryption at rest described but not tested**
- penetration testing performed by an **internal** team
- five **complementary user entity controls** that shift work onto the customer
- an examination period that ends **six months before** the customer's fiscal
  year end

`data/requirements.yaml` is the receiving organisation's standard: ten
requirements the vendor has to satisfy. The agent works through them and
returns one of five verdicts for each, then writes them to
`out/gap_register.csv` with the page number and the quoted evidence attached.

The distinctions it has to hold are the ones that matter in practice: design
versus operating effectiveness, tested evidence versus management's assertion,
out of scope versus failed, and the vendor's control versus yours.

---

## The loop

The whole concept is about a hundred lines, in `agent/loop.py`:

```
send messages with a tools array
  -> model returns a tool_use block instead of text
  -> execute the tool, send back a tool_result block
  -> repeat until the model stops or a control stops it
```

It is written out rather than delegated to a framework because every guardrail
decision happens in the gap between the model asking and the tool running, and
that gap is the only place a control can live.

Six tools, in `agent/tools.py`:

| tool | tier | what it does |
|---|---|---|
| `list_report_sections` | read | section ids, titles, page numbers |
| `read_section` | read | full text of one section |
| `search_report` | read | keyword search, returns located snippets |
| `get_requirements` | read | the standard being assessed against |
| `record_finding` | **write** | one row in the register. Needs approval. |
| `finish_review` | terminal | ends the run, refuses if anything is unassessed |

---

## The controls

| id | control | where | what it stops |
|---|---|---|---|
| AC-1 | Tool allowlist | `guardrails.ToolAllowlist` | calling anything not declared |
| AC-2 | Action tiers | `guardrails.ActionTier` | writing without a human approving that write |
| AC-3 | Run budget | `guardrails.RunBudget` | running past an iteration, token or time ceiling |
| AC-4 | Audit log | `audit.AuditLog` | acting without a record |
| AC-5 | Citation check | `guardrails.CitationCheck` | recording a finding it cannot evidence |
| AC-6 | Rollback | `tools.rollback_run` | leaving a bad run in the register |

AC-5 does the most work. A finding is rejected unless its citation appears
verbatim in the source document, checked by string comparison rather than by
asking the model whether it was being careful, and unless the agent read that
section earlier in the same run. It does not make the reasoning correct. It
makes the reasoning **checkable**, which is a smaller claim and the only one
the code can support.

AC-6 reverses what the agent wrote and deliberately does not touch the audit
log. Undoing an action and erasing the record of it are different operations,
and only one of them should be available to an operator.

### Watching them fire

```
python -m agent.cli run --replay data/replay/session_tampered.json --approve-all
```

A recorded session in which the model invents a citation, cites a real quote
from a section it never read, and then reaches for a tool that does not exist.

```
  read     3-8-security-testing
  blocked  record_finding: AC-5: the quoted citation does not appear in the source document.
  blocked  record_finding: AC-5: section 'cc8-1-change-management' has not been read in this run.
  blocked  delete_register: AC-1: tool 'delete_register' is not on the allowlist.

  gap register  (0 findings)
  complete:  False
```

Nothing is written. Each refusal goes back to the model as a tool error rather
than a crash, so the agent can try a permitted route instead.

---

## Everything it did

```
python -m agent.cli audit <run-id>
```

Every tool call, its arguments, the tier, the approval decision and who granted
it, a digest of what came back, and the token and time spend. This is the part
an auditor asks for. `out/audit.jsonl` is append-only and is fsynced on each
write, so a run that crashes still leaves a complete record up to the failure.

```
python -m agent.cli rollback <run-id>
```

Removes that run's rows from the register and writes the rollback itself into
the audit log.

---

## Running it live

```
cp .env.example .env          # add your key
python -m agent.cli run --record data/replay/my_session.json
```

Without `--approve-all` it stops at each write and shows you the finding, the
verdict and the quote before anything is recorded. Approval is per action, so
ten findings means ten prompts, and only `y` or `n` counts as an answer:
anything else re-prompts rather than being recorded as a decision you made. `--record` saves the run's
turns so it can be replayed later without the API.

The replay provider is not only a cost saver. It makes the loop deterministic,
which is what makes the controls testable at all: a control you can only
exercise against a non-deterministic model is a control you cannot test.

---

## Tests

```
python -m pytest tests/ -q
```

Twenty-four tests, one or more per control, including an end-to-end run, a
declined approval, a hallucinated citation blocked before it reaches the
register, a budget ceiling halting the loop mid-run, and a rollback that
removes one run's rows and leaves another's. Each test corresponds to a claim
the accompanying assessment makes, so the document cannot drift from the code
without something going red.

---

## Layout

```
agent/
  loop.py         the agent loop, and where every control is applied
  tools.py        tool schemas and implementations, register, rollback
  guardrails.py   AC-1, AC-2, AC-3, AC-5
  audit.py        AC-4, append-only log
  document.py     the only way the agent sees the report
  providers.py    live Messages API, or recorded turns
  cli.py          run / audit / rollback
data/
  soc2_northwind_2026.md   synthetic vendor report
  requirements.yaml        the standard being assessed against
  replay/                  recorded sessions
scripts/
  build_replay.py          regenerates recordings, verifying every citation
tests/
out/                       register and audit log, gitignored
```

---

## What this does not do

Stated plainly, because the point of the project is not to overclaim:

- **It has not been run against a real SOC 2 report.** The report is synthetic
  and the gaps in it were planted. Real reports are longer, are PDFs, and hide
  their exceptions less neatly.
- **The citation control proves grounding, not correctness.** A real quote can
  be attached to a wrong conclusion. It guarantees a reviewer can check the
  finding in seconds, not that the finding is right.
- **Search is keyword based.** If a requirement is discussed in language the
  query does not contain, the agent can miss the section entirely, and nothing
  here detects a miss. Absence of a finding is not evidence of absence of a gap.
- **Approval is a person clicking y.** The control is only as strong as the
  attention of whoever is approving, and `--approve-all` removes it completely.
  It is logged when used, which is the most the code can do about it.
- **The recorded session is one path through the report.** It demonstrates the
  loop and the controls. It is not evidence of how a live model behaves across
  many documents, and it should not be read as an accuracy claim.
- **No PDF ingestion, no OCR, no multi-document reasoning**, and no handling of
  a bridge letter or a subservice report even though the findings ask for both.

`CONTROLS.md` maps each control to its implementation and its tests.

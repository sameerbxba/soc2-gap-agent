"""Source document handling.

The agent is only ever allowed to see the report through this module. That is
deliberate: every piece of text the model reads arrives with a section id and a
page number attached, so a finding can always be traced back to a location in
the source rather than to the model's memory of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PAGE_MARKER = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
HEADING = re.compile(r"^(#{2,3})\s+(.*)$")


def normalise(text: str) -> str:
    """Collapse whitespace and lowercase, for citation matching.

    Citation checking has to survive the model reflowing a quote across lines
    or changing a run of spaces. It must not survive the model inventing words,
    so nothing here removes or reorders characters.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


@dataclass
class Section:
    id: str
    title: str
    page: int
    body: str

    def summary(self) -> dict:
        return {
            "section_id": self.id,
            "title": self.title,
            "page": self.page,
            "characters": len(self.body),
        }


class Document:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.raw = self.path.read_text(encoding="utf-8")
        self.normalised = normalise(self.raw)
        self.sections = self._parse()
        self._by_id = {s.id: s for s in self.sections}

    def _parse(self) -> list[Section]:
        sections: list[Section] = []
        page = 1
        current: dict | None = None
        buffer: list[str] = []

        def flush() -> None:
            if current is not None:
                sections.append(
                    Section(
                        id=current["id"],
                        title=current["title"],
                        page=current["page"],
                        body="\n".join(buffer).strip(),
                    )
                )

        for line in self.raw.splitlines():
            marker = PAGE_MARKER.search(line)
            if marker:
                page = int(marker.group(1))
                continue
            if line.strip().startswith("<!--"):
                continue
            heading = HEADING.match(line)
            if heading:
                flush()
                buffer = []
                title = heading.group(2).strip()
                base = slug(title)
                sid, n = base, 2
                while any(s.id == sid for s in sections):
                    sid, n = f"{base}-{n}", n + 1
                current = {"id": sid, "title": title, "page": page}
                continue
            buffer.append(line)

        flush()
        return [s for s in sections if s.body]

    def list_sections(self) -> list[dict]:
        return [s.summary() for s in self.sections]

    def get_section(self, section_id: str) -> Section | None:
        return self._by_id.get(section_id)

    def search(self, query: str, max_hits: int = 6) -> list[dict]:
        """Case-insensitive term search returning located snippets.

        Deliberately dumb. A semantic index would make the agent look cleverer
        and make its findings harder to trace, which is the wrong trade for a
        document whose purpose is evidence.
        """
        terms = [t for t in re.split(r"\s+", query.lower()) if len(t) > 2]
        hits = []
        for section in self.sections:
            body_l = section.body.lower()
            score = sum(body_l.count(t) for t in terms)
            if not score:
                continue
            first = min(
                (body_l.find(t) for t in terms if body_l.find(t) != -1),
                default=0,
            )
            start = max(0, first - 200)
            hits.append(
                {
                    "section_id": section.id,
                    "title": section.title,
                    "page": section.page,
                    "score": score,
                    "snippet": section.body[start : start + 700],
                }
            )
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:max_hits]

    def contains(self, quote: str) -> bool:
        """True if quote appears verbatim in the document, ignoring whitespace."""
        return normalise(quote) in self.normalised

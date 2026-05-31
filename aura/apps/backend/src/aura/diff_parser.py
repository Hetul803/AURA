from __future__ import annotations

import re
from dataclasses import dataclass, field


_DIFF_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*?)$")
_HUNK_HEADER = re.compile(r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<section>.*)$")


@dataclass(frozen=True)
class DiffLine:
    kind: str
    content: str
    old_lineno: int | None = None
    new_lineno: int | None = None


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str = ""
    lines: tuple[DiffLine, ...] = ()


@dataclass(frozen=True)
class ChangedFile:
    old_path: str
    new_path: str
    status: str = "modified"
    hunks: tuple[DiffHunk, ...] = ()
    is_binary: bool = False
    additions: int = 0
    deletions: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return self.new_path if self.status != "deleted" else self.old_path

    @property
    def added_text(self) -> str:
        return "\n".join(line.content for hunk in self.hunks for line in hunk.lines if line.kind == "add")


@dataclass(frozen=True)
class ParsedDiff:
    files: tuple[ChangedFile, ...]
    raw: str = ""

    @property
    def additions(self) -> int:
        return sum(file.additions for file in self.files)

    @property
    def deletions(self) -> int:
        return sum(file.deletions for file in self.files)


def _finish_hunk(hunks: list[DiffHunk], hunk_header: dict | None, lines: list[DiffLine]) -> None:
    if not hunk_header:
        return
    hunks.append(DiffHunk(lines=tuple(lines), **hunk_header))


def _finish_file(files: list[ChangedFile], current: dict | None, hunks: list[DiffHunk]) -> None:
    if not current:
        return
    additions = sum(1 for hunk in hunks for line in hunk.lines if line.kind == "add")
    deletions = sum(1 for hunk in hunks for line in hunk.lines if line.kind == "delete")
    status = current.get("status") or "modified"
    if current.get("new_path") == "/dev/null":
        status = "deleted"
    elif current.get("old_path") == "/dev/null":
        status = "added"
    elif current.get("rename_from") or current.get("rename_to"):
        status = "renamed"
    files.append(
        ChangedFile(
            old_path=current.get("old_path") or current.get("rename_from") or "",
            new_path=current.get("new_path") or current.get("rename_to") or "",
            status=status,
            hunks=tuple(hunks),
            is_binary=bool(current.get("is_binary")),
            additions=additions,
            deletions=deletions,
            metadata={k: str(v) for k, v in current.items() if k not in {"old_path", "new_path", "status", "is_binary"}},
        )
    )


def parse_unified_diff(diff_text: str | None) -> ParsedDiff:
    """Parse a unified git diff without executing or applying it."""

    raw = diff_text or ""
    files: list[ChangedFile] = []
    current: dict | None = None
    hunks: list[DiffHunk] = []
    hunk_header: dict | None = None
    hunk_lines: list[DiffLine] = []
    old_lineno: int | None = None
    new_lineno: int | None = None

    for raw_line in raw.splitlines():
        header = _DIFF_HEADER.match(raw_line)
        if header:
            _finish_hunk(hunks, hunk_header, hunk_lines)
            _finish_file(files, current, hunks)
            old_path, new_path = header.groups()
            current = {"old_path": old_path, "new_path": new_path, "status": "modified"}
            hunks = []
            hunk_header = None
            hunk_lines = []
            old_lineno = None
            new_lineno = None
            continue

        if current is None:
            continue

        if raw_line.startswith("new file mode"):
            current["status"] = "added"
            continue
        if raw_line.startswith("deleted file mode"):
            current["status"] = "deleted"
            continue
        if raw_line.startswith("rename from "):
            current["rename_from"] = raw_line.removeprefix("rename from ").strip()
            continue
        if raw_line.startswith("rename to "):
            current["rename_to"] = raw_line.removeprefix("rename to ").strip()
            current["new_path"] = current["rename_to"]
            current["status"] = "renamed"
            continue
        if raw_line.startswith("Binary files "):
            current["is_binary"] = True
            continue
        if raw_line.startswith("--- "):
            current["old_path"] = raw_line[4:].removeprefix("a/").strip()
            continue
        if raw_line.startswith("+++ "):
            current["new_path"] = raw_line[4:].removeprefix("b/").strip()
            continue

        hunk_match = _HUNK_HEADER.match(raw_line)
        if hunk_match:
            _finish_hunk(hunks, hunk_header, hunk_lines)
            old_start = int(hunk_match.group("old_start"))
            new_start = int(hunk_match.group("new_start"))
            hunk_header = {
                "old_start": old_start,
                "old_count": int(hunk_match.group("old_count") or "1"),
                "new_start": new_start,
                "new_count": int(hunk_match.group("new_count") or "1"),
                "section": hunk_match.group("section").strip(),
            }
            hunk_lines = []
            old_lineno = old_start
            new_lineno = new_start
            continue

        if hunk_header is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            hunk_lines.append(DiffLine(kind="add", content=raw_line[1:], old_lineno=None, new_lineno=new_lineno))
            new_lineno = None if new_lineno is None else new_lineno + 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            hunk_lines.append(DiffLine(kind="delete", content=raw_line[1:], old_lineno=old_lineno, new_lineno=None))
            old_lineno = None if old_lineno is None else old_lineno + 1
        elif raw_line.startswith("\\"):
            continue
        else:
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            hunk_lines.append(DiffLine(kind="context", content=content, old_lineno=old_lineno, new_lineno=new_lineno))
            old_lineno = None if old_lineno is None else old_lineno + 1
            new_lineno = None if new_lineno is None else new_lineno + 1

    _finish_hunk(hunks, hunk_header, hunk_lines)
    _finish_file(files, current, hunks)
    return ParsedDiff(files=tuple(files), raw=raw)

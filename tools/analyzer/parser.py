"""WhatsApp chat export parser.

Handles the format variations across iOS/Android exports and locales:

    iOS       [15/03/2024, 14:23:11] Name: message
    iOS 12h   [15/03/2024, 2:23:11 PM] Name: message
    Android   15/03/2024, 14:23 - Name: message
    Android   3/15/24, 2:23 PM - Name: message

Date component order (DD/MM vs MM/DD) is genuinely ambiguous within a single
line, so it is inferred from the whole corpus: a component that ever exceeds 12
must be the day. Ties default to day-first (the non-US convention).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Directional marks WhatsApp sprinkles into exports; they break naive matching.
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬⁦⁧⁨⁩﻿"))

# ---------------------------------------------------------------------------
# Line grammars
# ---------------------------------------------------------------------------

_IOS_HEADER = re.compile(
    r"^\[(?P<date>[0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4}),\s*"
    r"(?P<time>[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?(?:\s*[APap]\.?[Mm]\.?)?)\]\s*"
    r"(?P<rest>.*)$"
)

_ANDROID_HEADER = re.compile(
    r"^(?P<date>[0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4}),\s*"
    r"(?P<time>[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?(?:\s*[APap]\.?[Mm]\.?)?)\s+-\s+"
    r"(?P<rest>.*)$"
)

_DATE_PARTS = re.compile(r"^([0-9]{1,4})[./\-]([0-9]{1,2})[./\-]([0-9]{1,4})$")
_TIME_PARTS = re.compile(
    r"^([0-9]{1,2}):([0-9]{2})(?::([0-9]{2}))?\s*([APap])?\.?[Mm]?\.?$"
)

# A sender name never realistically exceeds this; anything longer means the
# colon we split on belonged to the message body, not a "Name:" prefix.
_MAX_SENDER_LEN = 60

# ---------------------------------------------------------------------------
# Attachment / placeholder grammars
# ---------------------------------------------------------------------------

_MEDIA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bimage omitted\b", re.I), "image"),
    (re.compile(r"\bvideo omitted\b", re.I), "video"),
    (re.compile(r"\baudio omitted\b", re.I), "audio"),
    (re.compile(r"\bsticker omitted\b", re.I), "sticker"),
    (re.compile(r"\bGIF omitted\b", re.I), "gif"),
    (re.compile(r"\bdocument omitted\b", re.I), "document"),
    (re.compile(r"\bContact card omitted\b", re.I), "contact"),
    (re.compile(r"\bmedia omitted\b", re.I), "unknown"),
    (re.compile(r"\.(jpe?g|png|heic|webp)\b", re.I), "image"),
    (re.compile(r"\.(mp4|mov|3gp|avi)\b", re.I), "video"),
    (re.compile(r"\.(opus|m4a|mp3|aac|ogg|wav)\b", re.I), "audio"),
    (re.compile(r"\.(pdf|docx?|xlsx?|pptx?|csv|txt|zip)\b", re.I), "document"),
    (re.compile(r"\.webp\b", re.I), "sticker"),
    (re.compile(r"\.vcf\b", re.I), "contact"),
]

_ATTACHMENT_MARKERS = (
    re.compile(r"<attached:\s*(?P<name>[^>]+)>", re.I),
    re.compile(r"(?P<name>\S+)\s*\((?:file|document) attached\)", re.I),
)

_DELETED = re.compile(
    r"(this message was deleted|you deleted this message|message deleted)", re.I
)
_EDITED = re.compile(r"<\s*this message was edited\s*>", re.I)

# Group-lifecycle lines carry no "Name:" prefix. Matched on the whole line.
_SYSTEM_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"messages and calls are end-to-end encrypted",
        r"\bcreated (this )?group\b",
        r"\badded\b.*",
        r"\bjoined using this group's invite link\b",
        r"\bleft\b$",
        r"\bremoved\b",
        r"\bchanged the subject\b",
        r"\bchanged this group's (icon|description|settings)\b",
        r"\bchanged their phone number\b",
        r"\bchanged to\b",
        r"\byou're now an admin\b",
        r"\bnow an admin\b",
        r"\bturned on disappearing messages\b",
        r"\bturned off disappearing messages\b",
        r"\bpinned a message\b",
        r"\bdeleted this group's icon\b",
        r"\bsecurity code changed\b",
        r"\bmissed (voice|video) call\b",
        r"\btap to (call back|learn more)\b",
        r"\bwaiting for this message\b",
    )
]


@dataclass
class Message:
    """One parsed chat line (with any continuation lines folded in)."""

    timestamp: datetime
    sender: str | None  # None for system/lifecycle lines
    text: str
    kind: str = "text"  # text | media | deleted | system
    media_type: str | None = None
    attachment_name: str | None = None
    is_edited: bool = False

    @property
    def is_from_person(self) -> bool:
        return self.sender is not None and self.kind != "system"


@dataclass
class Chat:
    """A fully parsed export."""

    messages: list[Message]
    source_name: str
    date_order: str  # "day-first" | "month-first"
    warnings: list[str] = field(default_factory=list)
    unparsed_lines: int = 0

    @property
    def people_messages(self) -> list[Message]:
        return [m for m in self.messages if m.is_from_person]

    @property
    def participants(self) -> list[str]:
        seen = Counter(m.sender for m in self.people_messages)
        return [name for name, _ in seen.most_common()]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_text(path: Path) -> tuple[str, str]:
    """Return (raw_text, display_name) from a .txt or .zip export."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            candidates = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not candidates:
                raise ValueError(f"No .txt chat file found inside {path.name}")
            # WhatsApp names it _chat.txt; otherwise take the largest .txt.
            chat_name = next(
                (n for n in candidates if n.lower().endswith("_chat.txt")),
                max(candidates, key=lambda n: zf.getinfo(n).file_size),
            )
            raw = zf.read(chat_name).decode("utf-8", errors="replace")
        return raw, path.stem
    raw = path.read_text(encoding="utf-8", errors="replace")
    return raw, path.stem


# ---------------------------------------------------------------------------
# Date / time
# ---------------------------------------------------------------------------


def _infer_date_order(date_strings: list[str]) -> str:
    """Decide DD/MM vs MM/DD by looking for a component that can't be a month."""
    first_over_12 = second_over_12 = False
    for ds in date_strings:
        m = _DATE_PARTS.match(ds)
        if not m:
            continue
        a, b, c = (int(g) for g in m.groups())
        if len(m.group(1)) == 4:  # ISO YYYY-MM-DD, unambiguous
            continue
        if a > 12:
            first_over_12 = True
        if b > 12:
            second_over_12 = True
    if first_over_12 and not second_over_12:
        return "day-first"
    if second_over_12 and not first_over_12:
        return "month-first"
    return "day-first"  # non-US default; ties are unresolvable from the data


def _parse_datetime(date_s: str, time_s: str, order: str) -> datetime | None:
    dm = _DATE_PARTS.match(date_s)
    tm = _TIME_PARTS.match(time_s.strip())
    if not dm or not tm:
        return None

    a, b, c = (int(g) for g in dm.groups())
    if len(dm.group(1)) == 4:  # YYYY-MM-DD
        year, month, day = a, b, c
    else:
        day, month = (a, b) if order == "day-first" else (b, a)
        year = c
        if year < 100:  # two-digit year
            year += 2000 if year < 70 else 1900

    hour, minute = int(tm.group(1)), int(tm.group(2))
    second = int(tm.group(3) or 0)
    meridiem = tm.group(4)
    if meridiem:
        upper = meridiem.upper()
        if upper == "P" and hour != 12:
            hour += 12
        elif upper == "A" and hour == 12:
            hour = 0

    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Body classification
# ---------------------------------------------------------------------------


def _looks_like_system(body: str) -> bool:
    return any(p.search(body) for p in _SYSTEM_PATTERNS)


def _split_sender(rest: str) -> tuple[str | None, str]:
    """Split 'Name: message' into its parts, or return (None, line) for system lines."""
    idx = rest.find(": ")
    if idx == -1:
        # A bare "Name:" with an empty body is still a sender line.
        if rest.endswith(":") and 0 < len(rest) - 1 <= _MAX_SENDER_LEN:
            return rest[:-1].strip(), ""
        return None, rest
    sender = rest[:idx].strip()
    body = rest[idx + 2 :]
    if not sender or len(sender) > _MAX_SENDER_LEN or "\n" in sender:
        return None, rest
    return sender, body


def _classify(body: str) -> tuple[str, str | None, str | None]:
    """Return (kind, media_type, attachment_name) for a message body."""
    if _DELETED.search(body):
        return "deleted", None, None

    attachment_name = None
    for marker in _ATTACHMENT_MARKERS:
        m = marker.search(body)
        if m:
            attachment_name = m.group("name").strip()
            break

    probe = attachment_name or body
    is_placeholder = attachment_name is not None or re.search(
        r"\bomitted\b", body, re.I
    )
    if is_placeholder:
        for pattern, media_type in _MEDIA_PATTERNS:
            if pattern.search(probe):
                return "media", media_type, attachment_name
        return "media", "unknown", attachment_name

    return "text", None, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse(path: Path) -> Chat:
    raw, display_name = load_text(path)
    raw = raw.translate(_INVISIBLE).replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")

    # Pass 1 — find the header grammar and collect dates for order inference.
    headers: list[tuple[re.Match[str], int]] = []
    for i, line in enumerate(lines):
        m = _IOS_HEADER.match(line) or _ANDROID_HEADER.match(line)
        if m:
            headers.append((m, i))

    if not headers:
        raise ValueError(
            "Could not find any WhatsApp-formatted messages in this file. "
            "Make sure it is a chat export (.txt or .zip) and not a screenshot "
            "or a partial copy-paste."
        )

    date_order = _infer_date_order([m.group("date") for m, _ in headers])

    # Pass 2 — build messages, folding continuation lines into the message above.
    messages: list[Message] = []
    warnings: list[str] = []
    unparsed = 0
    header_index = {i: m for m, i in headers}
    current: Message | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        if buffer:
            current.text = (current.text + "\n" + "\n".join(buffer)).strip("\n")
        # Re-classify now that the full multi-line body is assembled.
        if current.kind == "text":
            kind, media_type, name = _classify(current.text)
            current.kind, current.media_type, current.attachment_name = (
                kind,
                media_type,
                name,
            )
        messages.append(current)
        current, buffer = None, []

    for i, line in enumerate(lines):
        m = header_index.get(i)
        if m is None:
            if current is not None:
                buffer.append(line)
            elif line.strip():
                unparsed += 1
            continue

        flush()
        ts = _parse_datetime(m.group("date"), m.group("time"), date_order)
        if ts is None:
            unparsed += 1
            continue

        rest = m.group("rest")
        sender, body = _split_sender(rest)

        if sender is None or (body == "" and _looks_like_system(rest)):
            current = Message(timestamp=ts, sender=None, text=rest, kind="system")
            continue

        is_edited = bool(_EDITED.search(body))
        if is_edited:
            body = _EDITED.sub("", body).strip()

        kind, media_type, attachment_name = _classify(body)
        current = Message(
            timestamp=ts,
            sender=sender,
            text=body,
            kind=kind,
            media_type=media_type,
            attachment_name=attachment_name,
            is_edited=is_edited,
        )

    flush()

    if unparsed:
        warnings.append(
            f"{unparsed} line(s) could not be parsed and were skipped. "
            "This is normal for a handful of lines; if the count is large, the "
            "export format may be unusual."
        )
    if date_order == "day-first" and not any(
        int(_DATE_PARTS.match(m.group("date")).group(1)) > 12
        for m, _ in headers
        if _DATE_PARTS.match(m.group("date"))
        and len(_DATE_PARTS.match(m.group("date")).group(1)) != 4
    ):
        warnings.append(
            "Every date in this export has a day of 12 or lower, so DD/MM vs "
            "MM/DD cannot be determined from the file. Assuming DD/MM "
            "(day first). If the dates look wrong in the report, that's why."
        )

    messages.sort(key=lambda msg: msg.timestamp)
    return Chat(
        messages=messages,
        source_name=display_name,
        date_order=date_order,
        warnings=warnings,
        unparsed_lines=unparsed,
    )

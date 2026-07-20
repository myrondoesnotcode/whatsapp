"""Activity statistics and conversation dynamics."""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .parser import Chat, Message

_WORD = re.compile(r"[\w']+", re.UNICODE)
_URL_IN_TEXT = re.compile(r"\b(?:https?://|www\.)\S+", re.I)

#: A reply is a message from someone else within this window.
REPLY_WINDOW = timedelta(minutes=15)
#: A new conversation starts after this much silence.
CONVERSATION_GAP = timedelta(hours=3)


@dataclass
class PersonStats:
    name: str
    messages: int = 0
    words: int = 0
    characters: int = 0
    media: int = 0
    links: int = 0
    questions: int = 0
    emoji: int = 0
    deleted: int = 0
    edited: int = 0
    active_days: set[date] = field(default_factory=set)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    hours: Counter = field(default_factory=Counter)
    conversations_started: int = 0
    replies_received: int = 0
    longest_message: str = ""

    @property
    def avg_words(self) -> float:
        return round(self.words / self.messages, 1) if self.messages else 0.0

    @property
    def days_active(self) -> int:
        return len(self.active_days)


@dataclass
class Overview:
    total_messages: int
    people_messages: int
    system_messages: int
    participants: int
    first_message: datetime
    last_message: datetime
    span_days: int
    active_days: int
    media_count: int
    link_count: int
    question_count: int
    deleted_count: int
    total_words: int
    busiest_day: tuple[date, int]
    quietest_stretch_days: int
    avg_messages_per_active_day: float


def _count_emoji(text: str) -> int:
    return sum(
        1
        for ch in text
        if ord(ch) > 0x2100
        and not (0xFE00 <= ord(ch) <= 0xFE0F)  # variation selectors
        and not (0x200D == ord(ch))  # ZWJ
    )


def build_overview(chat: Chat, link_count: int) -> Overview:
    people = chat.people_messages
    if not people:
        raise ValueError("This export contains no messages from participants.")

    per_day: Counter = Counter(m.timestamp.date() for m in people)
    days_present = sorted(per_day)
    longest_gap = 0
    for earlier, later in zip(days_present, days_present[1:]):
        longest_gap = max(longest_gap, (later - earlier).days - 1)

    first, last = people[0].timestamp, people[-1].timestamp
    busiest = per_day.most_common(1)[0]

    return Overview(
        total_messages=len(chat.messages),
        people_messages=len(people),
        system_messages=len(chat.messages) - len(people),
        participants=len(chat.participants),
        first_message=first,
        last_message=last,
        span_days=max((last.date() - first.date()).days + 1, 1),
        active_days=len(per_day),
        media_count=sum(1 for m in people if m.kind == "media"),
        link_count=link_count,
        question_count=sum(1 for m in people if m.kind == "text" and "?" in m.text),
        deleted_count=sum(1 for m in people if m.kind == "deleted"),
        total_words=sum(len(_WORD.findall(m.text)) for m in people if m.kind == "text"),
        busiest_day=busiest,
        quietest_stretch_days=longest_gap,
        avg_messages_per_active_day=round(len(people) / max(len(per_day), 1), 1),
    )


def build_person_stats(chat: Chat) -> list[PersonStats]:
    stats: dict[str, PersonStats] = {}
    people = chat.people_messages

    for msg in people:
        name = msg.sender  # type: ignore[assignment]
        person = stats.get(name)
        if person is None:
            person = stats[name] = PersonStats(name=name)

        person.messages += 1
        person.active_days.add(msg.timestamp.date())
        person.hours[msg.timestamp.hour] += 1
        if person.first_seen is None or msg.timestamp < person.first_seen:
            person.first_seen = msg.timestamp
        if person.last_seen is None or msg.timestamp > person.last_seen:
            person.last_seen = msg.timestamp

        if msg.is_edited:
            person.edited += 1
        if msg.kind == "media":
            person.media += 1
            continue
        if msg.kind == "deleted":
            person.deleted += 1
            continue

        body = msg.text
        person.characters += len(body)
        person.words += len(_WORD.findall(body))
        person.emoji += _count_emoji(body)
        person.links += len(_URL_IN_TEXT.findall(body))
        if "?" in body:
            person.questions += 1
        if len(body) > len(person.longest_message):
            person.longest_message = body[:500]

    # Conversation starters and replies received need message adjacency.
    previous: Message | None = None
    for msg in people:
        if previous is None or msg.timestamp - previous.timestamp >= CONVERSATION_GAP:
            stats[msg.sender].conversations_started += 1  # type: ignore[index]
        elif (
            msg.sender != previous.sender
            and msg.timestamp - previous.timestamp <= REPLY_WINDOW
        ):
            stats[previous.sender].replies_received += 1  # type: ignore[index]
        previous = msg

    return sorted(stats.values(), key=lambda p: p.messages, reverse=True)


def daily_timeline(chat: Chat) -> list[tuple[date, int]]:
    counts: Counter = Counter(m.timestamp.date() for m in chat.people_messages)
    if not counts:
        return []
    start, end = min(counts), max(counts)
    out: list[tuple[date, int]] = []
    cursor = start
    while cursor <= end:
        out.append((cursor, counts.get(cursor, 0)))
        cursor += timedelta(days=1)
    return out


def monthly_timeline(chat: Chat) -> list[tuple[str, int]]:
    counts: Counter = Counter(
        m.timestamp.strftime("%Y-%m") for m in chat.people_messages
    )
    return sorted(counts.items())


def hour_weekday_matrix(chat: Chat) -> list[list[int]]:
    """7x24 grid, Monday-first, of message volume."""
    grid = [[0] * 24 for _ in range(7)]
    for msg in chat.people_messages:
        grid[msg.timestamp.weekday()][msg.timestamp.hour] += 1
    return grid


def interaction_matrix(chat: Chat, top_n: int = 12) -> tuple[list[str], list[list[int]]]:
    """Who speaks right after whom, as a proxy for who engages with whom."""
    people = chat.people_messages
    counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for earlier, later in zip(people, people[1:]):
        if (
            earlier.sender != later.sender
            and later.timestamp - earlier.timestamp <= REPLY_WINDOW
        ):
            counts[(later.sender, earlier.sender)] += 1  # type: ignore[index]

    volume: Counter = Counter(m.sender for m in people)
    names = [name for name, _ in volume.most_common(top_n)]
    index = {name: i for i, name in enumerate(names)}
    matrix = [[0] * len(names) for _ in names]
    for (responder, target), n in counts.items():
        if responder in index and target in index:
            matrix[index[responder]][index[target]] = n
    return names, matrix


def response_times(chat: Chat) -> dict[str, float]:
    gaps: list[float] = []
    people = chat.people_messages
    for earlier, later in zip(people, people[1:]):
        if (
            earlier.sender != later.sender
            and later.timestamp - earlier.timestamp <= REPLY_WINDOW
        ):
            gaps.append((later.timestamp - earlier.timestamp).total_seconds() / 60)
    if not gaps:
        return {}
    gaps.sort()
    return {
        "median_minutes": round(statistics.median(gaps), 1),
        "fastest_quartile": round(gaps[len(gaps) // 4], 1),
        "slowest_quartile": round(gaps[3 * len(gaps) // 4], 1),
        "sample": len(gaps),
    }


def membership_events(chat: Chat) -> list[tuple[datetime, str]]:
    """Joins, leaves, adds and removals pulled from group-lifecycle lines."""
    interesting = re.compile(
        r"(joined using|added|left|removed|created (this )?group|changed the subject)",
        re.I,
    )
    return [
        (m.timestamp, m.text)
        for m in chat.messages
        if m.kind == "system" and interesting.search(m.text)
    ]


def engagement_peaks(chat: Chat, top_n: int = 15) -> list[tuple[Message, int]]:
    """Messages followed by the most distinct-sender activity in 10 minutes.

    A rough proxy for "this one got the room talking".
    """
    people = chat.people_messages
    window = timedelta(minutes=10)
    scored: list[tuple[Message, int]] = []
    for i, msg in enumerate(people):
        if msg.kind != "text" or len(msg.text) < 15:
            continue
        responders: set[str] = set()
        for later in people[i + 1 :]:
            if later.timestamp - msg.timestamp > window:
                break
            if later.sender != msg.sender:
                responders.add(later.sender)  # type: ignore[arg-type]
        if len(responders) >= 2:
            scored.append((msg, len(responders)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]

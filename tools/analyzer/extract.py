"""Content extraction: links, tools, builder signals, questions, asks.

Everything here is pattern-matching over message text — no model calls. The
design bias is precision over recall: a number in the report should be one you
can trust without spot-checking it.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from .parser import Chat, Message
from .tools_dict import COMPILED, DISCOVERY_STOPWORDS

# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'\]\)]+", re.I)
_TRAILING_JUNK = ".,;:!?)]}'\"…"

_GITHUB_REPO = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)", re.I)
_YOUTUBE = re.compile(r"(?:youtube\.com/watch|youtu\.be/|youtube\.com/shorts)", re.I)

#: domain fragment -> human-facing bucket
_LINK_KINDS: list[tuple[str, str]] = [
    ("github.com", "Code"),
    ("gitlab.com", "Code"),
    ("npmjs.com", "Code"),
    ("pypi.org", "Code"),
    ("huggingface.co", "Models & datasets"),
    ("arxiv.org", "Research"),
    ("scholar.google", "Research"),
    ("youtube.com", "Video"),
    ("youtu.be", "Video"),
    ("vimeo.com", "Video"),
    ("loom.com", "Video"),
    ("twitter.com", "Social"),
    ("x.com", "Social"),
    ("linkedin.com", "Social"),
    ("reddit.com", "Social"),
    ("news.ycombinator.com", "Social"),
    ("producthunt.com", "Product launches"),
    ("medium.com", "Articles"),
    ("substack.com", "Articles"),
    ("dev.to", "Articles"),
    ("notion.so", "Docs"),
    ("notion.site", "Docs"),
    ("docs.google.com", "Docs"),
    ("figma.com", "Design"),
    ("lu.ma", "Events"),
    ("eventbrite", "Events"),
    ("meetup.com", "Events"),
    ("calendly.com", "Scheduling"),
    ("chat.whatsapp.com", "Group invites"),
]


@dataclass
class Link:
    url: str
    domain: str
    kind: str
    sender: str
    timestamp: datetime
    context: str
    repo: str | None = None  # owner/name for GitHub links


def _clean_url(raw: str) -> str:
    url = raw.rstrip(_TRAILING_JUNK)
    # Balance a trailing paren that belongs to the URL (common in wiki links).
    if url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def _domain_of(url: str) -> str:
    target = url if url.lower().startswith("http") else f"http://{url}"
    host = (urlparse(target).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _kind_of(domain: str) -> str:
    for fragment, kind in _LINK_KINDS:
        if fragment in domain:
            return kind
    return "Other"


def extract_links(chat: Chat) -> list[Link]:
    links: list[Link] = []
    for msg in chat.people_messages:
        for match in _URL.finditer(msg.text):
            url = _clean_url(match.group(0))
            if len(url) < 8:
                continue
            domain = _domain_of(url)
            if not domain:
                continue
            repo_match = _GITHUB_REPO.search(url)
            repo = None
            if repo_match:
                owner, name = repo_match.groups()
                if name.lower() not in {"blob", "tree", "issues", "pull"}:
                    repo = f"{owner}/{name.removesuffix('.git')}"
            context = _URL.sub("", msg.text).strip() or "(link only)"
            links.append(
                Link(
                    url=url,
                    domain=domain,
                    kind=_kind_of(domain),
                    sender=msg.sender,  # type: ignore[arg-type]
                    timestamp=msg.timestamp,
                    context=context[:280],
                    repo=repo,
                )
            )
    return links


# ---------------------------------------------------------------------------
# Tools & technology mentions
# ---------------------------------------------------------------------------


@dataclass
class ToolMention:
    name: str
    category: str
    count: int
    people: Counter = field(default_factory=Counter)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    samples: list[str] = field(default_factory=list)
    by_month: Counter = field(default_factory=Counter)


def extract_tools(chat: Chat) -> list[ToolMention]:
    found: dict[str, ToolMention] = {}
    for msg in chat.people_messages:
        if msg.kind != "text" or not msg.text:
            continue
        for name, (category, matcher) in COMPILED.items():
            if not matcher.search(msg.text):
                continue
            entry = found.get(name)
            if entry is None:
                entry = found[name] = ToolMention(name=name, category=category, count=0)
            entry.count += 1
            entry.people[msg.sender] += 1
            entry.by_month[msg.timestamp.strftime("%Y-%m")] += 1
            if entry.first_seen is None or msg.timestamp < entry.first_seen:
                entry.first_seen = msg.timestamp
            if entry.last_seen is None or msg.timestamp > entry.last_seen:
                entry.last_seen = msg.timestamp
            if len(entry.samples) < 5 and len(msg.text) < 400:
                entry.samples.append(msg.text)
    return sorted(found.values(), key=lambda t: t.count, reverse=True)


_CAPITALISED = re.compile(r"\b([A-Z][a-zA-Z0-9]{2,}(?:\.[a-z]{2,4})?)\b")


def discover_unknown_tools(
    chat: Chat, known_names: set[str], min_mentions: int = 4
) -> list[tuple[str, int]]:
    """Surface recurring capitalised terms that aren't in the curated vocabulary.

    Catches tools the dictionary doesn't know about yet. Noisy by nature, so it
    is presented in the report as "possible tools" rather than as fact.
    """
    known_lower = {n.lower() for n in known_names}
    for name in COMPILED:
        known_lower.add(name.lower())
        # Block the individual words of multi-word tool names too. Without this,
        # "Hugging Face" and "Product Hunt" leak in as four separate
        # "discoveries", since neither half matches the full-name pattern alone.
        known_lower.update(w for w in re.split(r"[^a-z0-9.]+", name.lower()) if len(w) > 2)

    participants = {p.lower() for p in chat.participants}
    name_words = {w.lower() for p in chat.participants for w in p.split()}

    counts: Counter = Counter()
    carriers: defaultdict[str, set[str]] = defaultdict(set)
    for msg in chat.people_messages:
        if msg.kind != "text":
            continue
        # Only mid-sentence capitals: a word starting a sentence tells us nothing.
        for match in _CAPITALISED.finditer(msg.text):
            if match.start() == 0 or msg.text[match.start() - 1] in ".!?\n":
                continue
            token = match.group(1)
            low = token.lower()
            if (
                low in DISCOVERY_STOPWORDS
                or low in known_lower
                or low in participants
                or low in name_words
                or any(matcher.search(token) for _, matcher in COMPILED.values())
            ):
                continue
            counts[token] += 1
            carriers[token].add(msg.sender)  # type: ignore[arg-type]

    # Require multiple distinct people — a term one person repeats is usually
    # a name or a typo, not a tool the community is discussing.
    return sorted(
        (
            (token, n)
            for token, n in counts.items()
            if n >= min_mentions and len(carriers[token]) >= 2
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )[:40]


# ---------------------------------------------------------------------------
# Builder / hiring / help signals
# ---------------------------------------------------------------------------

_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "Building": [
        r"\b(?:i'?m|i am|we'?re|we are)\s+(?:currently\s+)?building\b",
        r"\bstarted (?:building|working on)\b",
        r"\b(?:i|we)\s+(?:am|are)\s+working on\b",
        r"\bbeen working on\b",
        r"\bworking on (?:a|an|my|our)\b",
        r"\bside project\b",
        r"\bbuilding (?:a|an|my|our)\b",
    ],
    "Shipped / launched": [
        r"\bjust (?:launched|shipped|released|published)\b",
        r"\b(?:we|i) (?:just )?(?:launched|shipped|released)\b",
        r"\bwent live\b",
        r"\bnow (?:live|available|public)\b",
        r"\bv?\d+\.\d+ is (?:out|live)\b",
        r"\blaunch(?:ing|ed) (?:today|tomorrow|this week)\b",
        r"\bopen ?sourc(?:ed|ing)\b",
    ],
    "Seeking feedback": [
        r"\b(?:would love|looking for|any) feedback\b",
        r"\bwhat do you (?:think|guys think)\b",
        r"\bthoughts\?",
        r"\bbeta (?:testers?|users?)\b",
        r"\btry it out\b",
        r"\bwaitlist\b",
        r"\broast\b",
    ],
    "Hiring": [
        r"\b(?:we'?re|we are|i'?m|currently) hiring\b",
        r"\blooking (?:for|to hire) (?:a|an|some)?\s*(?:senior|junior|full[- ]?stack|backend|frontend|founding)?\s*(?:engineer|developer|designer|dev|pm|cto|intern)\b",
        r"\bjoin (?:our|the) team\b",
        r"\bopen (?:role|position)s?\b",
        r"\bjob (?:opening|post)\b",
        r"\breferral\b",
    ],
    "Asking for help": [
        r"\bdoes anyone (?:know|have|use)\b",
        r"\banyone (?:know|have|used|tried|using)\b",
        r"\blooking for (?:recommendations?|advice|suggestions?|a tool)\b",
        r"\bany (?:recommendations?|suggestions?|tips)\b",
        r"\bcan (?:someone|anyone) (?:help|explain)\b",
        r"\bhow do (?:i|you|we)\b",
        r"\bstuck (?:on|with)\b",
    ],
    "Events & meetups": [
        r"\bmeetup\b",
        r"\bhackathon\b",
        r"\b(?:demo|pitch) (?:day|night)\b",
        r"\bconference\b",
        r"\bworkshop\b",
        r"\bwe'?re hosting\b",
        r"\bsign ?up (?:here|link)\b",
        r"\brsvp\b",
    ],
}

_SIGNAL_COMPILED = {
    label: re.compile("|".join(f"(?:{p})" for p in patterns), re.I)
    for label, patterns in _SIGNAL_PATTERNS.items()
}


@dataclass
class Signal:
    label: str
    sender: str
    timestamp: datetime
    text: str
    links: list[str] = field(default_factory=list)


def extract_signals(chat: Chat) -> dict[str, list[Signal]]:
    out: defaultdict[str, list[Signal]] = defaultdict(list)
    for msg in chat.people_messages:
        if msg.kind != "text" or len(msg.text) < 12:
            continue
        for label, matcher in _SIGNAL_COMPILED.items():
            if matcher.search(msg.text):
                out[label].append(
                    Signal(
                        label=label,
                        sender=msg.sender,  # type: ignore[arg-type]
                        timestamp=msg.timestamp,
                        text=msg.text[:600],
                        links=[_clean_url(m.group(0)) for m in _URL.finditer(msg.text)],
                    )
                )
    for signals in out.values():
        signals.sort(key=lambda s: s.timestamp, reverse=True)
    return dict(out)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@dataclass
class Question:
    sender: str
    timestamp: datetime
    text: str
    answered_within_minutes: float | None


def extract_questions(chat: Chat, reply_window_minutes: int = 60) -> list[Question]:
    """Messages that ask something, with how fast anyone responded."""
    people = chat.people_messages
    questions: list[Question] = []
    for i, msg in enumerate(people):
        if msg.kind != "text" or "?" not in msg.text or len(msg.text) < 8:
            continue
        answered = None
        for later in people[i + 1 :]:
            if later.sender == msg.sender:
                continue
            gap = (later.timestamp - msg.timestamp).total_seconds() / 60
            if gap > reply_window_minutes:
                break
            answered = round(gap, 1)
            break
        questions.append(
            Question(
                sender=msg.sender,  # type: ignore[arg-type]
                timestamp=msg.timestamp,
                text=msg.text[:400],
                answered_within_minutes=answered,
            )
        )
    return questions

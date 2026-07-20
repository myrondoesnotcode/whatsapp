"""Self-contained HTML dashboard generation.

No CDN, no build step, no runtime dependencies — the output is a single .html
file that opens offline. Charts are hand-rolled: CSS bars for rankings, a CSS
grid for the heatmap, inline SVG for the timeline.

Colour follows the validated reference palette (see the dataviz skill). Light
mode puts a visible value label on every categorical mark, which is the required
relief for the three light-surface hues that sit below 3:1 contrast.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence

from . import stats as stats_mod
from . import text as text_mod
from .extract import Link, Question, Signal, ToolMention
from .parser import Chat

SERIES = [
    "#2a78d6", "#008300", "#e87ba4", "#eda100",
    "#1baf7a", "#eb6834", "#4a3aa7", "#e34948",
]
SERIES_DARK = [
    "#3987e5", "#008300", "#d55181", "#c98500",
    "#199e70", "#d95926", "#9085e9", "#e66767",
]

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _fmt_dt(value: datetime) -> str:
    return value.strftime("%d %b %Y, %H:%M")


def _fmt_d(value: date) -> str:
    return value.strftime("%d %b %Y")


def _pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


# ---------------------------------------------------------------------------
# Chart primitives
# ---------------------------------------------------------------------------


def bar_rows(
    items: Sequence[tuple[str, float]],
    *,
    slot: int = 0,
    suffix: str = "",
    secondary: Sequence[str] | None = None,
) -> str:
    """Horizontal ranked bars. Every bar carries its own value label."""
    if not items:
        return '<p class="empty">Nothing found.</p>'
    peak = max(v for _, v in items) or 1
    out = []
    for i, (label, value) in enumerate(items):
        width = max(100 * value / peak, 1.2)
        sub = (
            f'<span class="bar-sub">{e(secondary[i])}</span>'
            if secondary and i < len(secondary)
            else ""
        )
        shown = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.1f}"
        out.append(
            f'<div class="bar-row">'
            f'<div class="bar-label" title="{e(label)}">{e(label)}{sub}</div>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{width:.2f}%;'
            f'background:var(--s{slot})"></div>'
            f'<span class="bar-value">{shown}{e(suffix)}</span>'
            f"</div></div>"
        )
    return f'<div class="bars">{"".join(out)}</div>'


def heatmap(grid: list[list[int]]) -> str:
    peak = max((max(row) for row in grid), default=0) or 1
    cells = []
    for day_index, row in enumerate(grid):
        cells.append(f'<div class="hm-daylabel">{WEEKDAYS[day_index]}</div>')
        for hour, count in enumerate(row):
            level = 0 if count == 0 else min(10, 1 + int(9 * count / peak))
            cells.append(
                f'<div class="hm-cell" data-level="{level}" '
                f'title="{WEEKDAYS[day_index]} {hour:02d}:00 — {count} messages"></div>'
            )
    hours = '<div class="hm-daylabel"></div>' + "".join(
        f'<div class="hm-hourlabel">{h if h % 3 == 0 else ""}</div>' for h in range(24)
    )
    return (
        f'<div class="heatmap">{"".join(cells)}{hours}</div>'
        f'<div class="hm-legend"><span>Quiet</span>'
        + "".join(f'<i data-level="{n}"></i>' for n in range(11))
        + "<span>Busy</span></div>"
    )


def area_chart(points: Sequence[tuple[date, int]], *, height: int = 220) -> str:
    """Daily volume area + 7-day rolling mean, with a JS crosshair layer."""
    if len(points) < 2:
        return '<p class="empty">Not enough days to chart.</p>'

    width, pad_l, pad_b, pad_t = 1000, 44, 26, 12
    values = [v for _, v in points]
    peak = max(values) or 1
    plot_w, plot_h = width - pad_l - 8, height - pad_b - pad_t
    step = plot_w / (len(points) - 1)

    def x(i: int) -> float:
        return pad_l + i * step

    def y(v: float) -> float:
        return pad_t + plot_h * (1 - v / peak)

    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    area = f"M{pad_l},{y(0):.1f} L{line.replace(' ', ' L')} L{x(len(values) - 1):.1f},{y(0):.1f} Z"

    window = 7
    rolling = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1) : i + 1]
        rolling.append(sum(chunk) / len(chunk))
    roll_path = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(rolling))

    ticks = []
    for frac in (0, 0.5, 1):
        value = peak * frac
        ticks.append(
            f'<line class="grid" x1="{pad_l}" x2="{width - 8}" '
            f'y1="{y(value):.1f}" y2="{y(value):.1f}"/>'
            f'<text class="axis" x="{pad_l - 8}" y="{y(value) + 4:.1f}" '
            f'text-anchor="end">{value:,.0f}</text>'
        )

    labels = []
    for i in (0, len(points) // 2, len(points) - 1):
        anchor = "start" if i == 0 else "end" if i == len(points) - 1 else "middle"
        labels.append(
            f'<text class="axis" x="{x(i):.1f}" y="{height - 6}" '
            f'text-anchor="{anchor}">{_fmt_d(points[i][0])}</text>'
        )

    payload = json.dumps(
        [[p[0].isoformat(), v] for p, v in zip(points, values)], separators=(",", ":")
    )
    return (
        f'<div class="chart-wrap">'
        f'<svg class="timeline" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" role="img" '
        f'aria-label="Daily message volume over time">'
        f'{"".join(ticks)}'
        f'<path class="area" d="{area}"/>'
        f'<path class="roll" d="{roll_path}"/>'
        f'{"".join(labels)}'
        f'<line class="crosshair" x1="0" x2="0" y1="{pad_t}" y2="{pad_t + plot_h}" '
        f'style="opacity:0"/>'
        f'<circle class="cursor-dot" r="4" style="opacity:0"/>'
        f"</svg>"
        f'<div class="tip" hidden></div>'
        f'<script type="application/json" class="tl-data">{payload}</script>'
        f'<div class="chart-meta">Shaded: messages per day &middot; '
        f'Line: 7-day average</div>'
        f"</div>"
    )


def stat_tile(value: str, label: str, sub: str = "") -> str:
    sub_html = f'<div class="tile-sub">{e(sub)}</div>' if sub else ""
    return (
        f'<div class="tile"><div class="tile-value">{e(value)}</div>'
        f'<div class="tile-label">{e(label)}</div>{sub_html}</div>'
    )


def table(headers: Sequence[str], rows: Iterable[Sequence[str]], *, cls: str = "") -> str:
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    if not body:
        return '<p class="empty">Nothing found.</p>'
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def section(anchor: str, title: str, blurb: str, body: str) -> str:
    return (
        f'<section id="{anchor}"><h2>{e(title)}</h2>'
        f'<p class="blurb">{e(blurb)}</p>{body}</section>'
    )


def card(title: str, body: str, note: str = "") -> str:
    note_html = f'<p class="note">{e(note)}</p>' if note else ""
    return f'<div class="card"><h3>{e(title)}</h3>{note_html}{body}</div>'


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build(
    chat: Chat,
    *,
    overview: stats_mod.Overview,
    people: list[stats_mod.PersonStats],
    links: list[Link],
    tools: list[ToolMention],
    discovered: list[tuple[str, int]],
    signals: dict[str, list[Signal]],
    questions: list[Question],
    out_path: Path,
) -> Path:
    total = overview.people_messages

    # -- Overview -----------------------------------------------------------
    tiles = "".join(
        [
            stat_tile(f"{total:,}", "messages", f"{overview.total_words:,} words"),
            stat_tile(str(overview.participants), "participants"),
            stat_tile(
                str(overview.span_days),
                "days covered",
                f"{overview.active_days} with activity",
            ),
            stat_tile(f"{len(links):,}", "links shared"),
            stat_tile(f"{overview.media_count:,}", "media & files"),
            stat_tile(f"{overview.question_count:,}", "questions asked"),
            stat_tile(
                str(overview.avg_messages_per_active_day),
                "msgs / active day",
            ),
            stat_tile(
                f"{overview.busiest_day[1]:,}",
                "busiest day",
                _fmt_d(overview.busiest_day[0]),
            ),
        ]
    )

    warnings_html = ""
    if chat.warnings:
        items = "".join(f"<li>{e(w)}</li>" for w in chat.warnings)
        warnings_html = f'<div class="warn"><strong>Parser notes</strong><ul>{items}</ul></div>'

    overview_html = (
        f'{warnings_html}<div class="tiles">{tiles}</div>'
        f'<div class="card"><h3>Message volume over time</h3>'
        f"{area_chart(stats_mod.daily_timeline(chat))}</div>"
    )

    # -- Activity -----------------------------------------------------------
    monthly = stats_mod.monthly_timeline(chat)
    month_labels = [
        (datetime.strptime(m, "%Y-%m").strftime("%b %Y"), n) for m, n in monthly
    ]
    response = stats_mod.response_times(chat)
    response_html = (
        f'<div class="tiles compact">'
        + stat_tile(f'{response["median_minutes"]}m', "median reply gap")
        + stat_tile(f'{response["fastest_quartile"]}m', "fastest 25%")
        + stat_tile(f'{response["slowest_quartile"]}m', "slowest 25%")
        + "</div>"
        if response
        else '<p class="empty">Not enough back-and-forth to measure.</p>'
    )

    activity_html = (
        card("When the group is awake", heatmap(stats_mod.hour_weekday_matrix(chat)),
             "Darker cell = more messages in that hour.")
        + card("Volume by month", bar_rows(month_labels, slot=0))
        + card("How fast people reply", response_html,
               "Gap between one person's message and the next person's, within 15 minutes.")
    )

    # -- People -------------------------------------------------------------
    emoji_map = text_mod.emoji_by_person(chat)
    person_rows = []
    for p in people:
        signature = "".join(ch for ch, _ in emoji_map.get(p.name, [])) or "—"
        person_rows.append(
            [
                f"<strong>{e(p.name)}</strong>",
                f"{p.messages:,}",
                f"{_pct(p.messages, total)}%",
                f"{p.avg_words}",
                f"{p.links:,}",
                f"{p.media:,}",
                f"{p.questions:,}",
                f"{p.days_active:,}",
                f"{p.conversations_started:,}",
                f"{p.replies_received:,}",
                f'<span class="emoji">{signature}</span>',
            ]
        )

    top_people = [(p.name, p.messages) for p in people[:20]]
    people_share = [f"{_pct(p.messages, total)}% of all messages" for p in people[:20]]
    starters = sorted(people, key=lambda p: p.conversations_started, reverse=True)[:10]
    responded = sorted(people, key=lambda p: p.replies_received, reverse=True)[:10]

    people_html = (
        card("Who talks most", bar_rows(top_people, slot=0, secondary=people_share))
        + '<div class="grid-2">'
        + card(
            "Who starts conversations",
            bar_rows([(p.name, p.conversations_started) for p in starters], slot=1),
            "First message after 3+ hours of silence.",
        )
        + card(
            "Who gets replied to",
            bar_rows([(p.name, p.replies_received) for p in responded], slot=4),
            "Messages followed within 15 minutes by someone else.",
        )
        + "</div>"
        + card(
            "Everyone, in full",
            table(
                ["Person", "Msgs", "Share", "Avg words", "Links", "Media",
                 "Questions", "Active days", "Started", "Replies got", "Emoji"],
                person_rows,
                cls="sortable",
            ),
        )
    )

    # -- What's shared ------------------------------------------------------
    domain_counts = Counter(l.domain for l in links)
    kind_counts = Counter(l.kind for l in links)
    repo_counts = Counter(l.repo for l in links if l.repo)
    sharer_counts = Counter(l.sender for l in links)

    link_rows = [
        [
            f'<span class="when">{_fmt_d(l.timestamp.date())}</span>',
            e(l.sender),
            f'<span class="pill">{e(l.kind)}</span>',
            f'<a href="{e(l.url)}" target="_blank" rel="noopener noreferrer">{e(l.url[:90])}</a>',
            f'<span class="ctx">{e(l.context[:140])}</span>',
        ]
        for l in sorted(links, key=lambda l: l.timestamp, reverse=True)
    ]

    shared_html = (
        '<div class="grid-2">'
        + card("What kind of links", bar_rows(kind_counts.most_common(), slot=2))
        + card("Top domains", bar_rows(domain_counts.most_common(20), slot=0))
        + "</div>"
        + '<div class="grid-2">'
        + card(
            "GitHub repos shared",
            bar_rows(repo_counts.most_common(20), slot=1),
            "Repos linked in the chat, by number of times shared.",
        )
        + card("Who shares links", bar_rows(sharer_counts.most_common(15), slot=4))
        + "</div>"
        + card(
            f"Every link ({len(links):,})",
            '<input class="filter" data-target="link-table" type="search" '
            'placeholder="Filter links — try a domain, a person, or a keyword">'
            + f'<div class="scroll" id="link-table">'
            + table(["Date", "Shared by", "Type", "Link", "Said alongside"], link_rows)
            + "</div>",
        )
    )

    # -- Tools --------------------------------------------------------------
    by_category: dict[str, list[ToolMention]] = {}
    for tool in tools:
        by_category.setdefault(tool.category, []).append(tool)

    tool_cards = []
    for i, (category, entries) in enumerate(
        sorted(by_category.items(), key=lambda kv: -sum(t.count for t in kv[1]))
    ):
        rows = [(t.name, t.count) for t in entries[:15]]
        sub = [f"{len(t.people)} people" for t in entries[:15]]
        tool_cards.append(card(category, bar_rows(rows, slot=i % 8, secondary=sub)))

    discovery_html = (
        card(
            "Possibly tools we don't know about",
            '<div class="chips">'
            + "".join(
                f'<span class="chip">{e(token)}<i>{n}</i></span>'
                for token, n in discovered
            )
            + "</div>",
            "Recurring capitalised terms mentioned by 2+ people that aren't in the "
            "built-in vocabulary. Expect noise — names and typos slip through.",
        )
        if discovered
        else ""
    )

    tools_html = (
        card(
            "Most-discussed tools overall",
            bar_rows(
                [(t.name, t.count) for t in tools[:25]],
                slot=0,
                secondary=[f"{len(t.people)} people · {t.category}" for t in tools[:25]],
            ),
        )
        + f'<div class="grid-2">{"".join(tool_cards)}</div>'
        + discovery_html
    )

    # -- Signals ------------------------------------------------------------
    signal_order = [
        "Building", "Shipped / launched", "Seeking feedback",
        "Hiring", "Asking for help", "Events & meetups",
    ]
    tabs, panels = [], []
    for i, label in enumerate(signal_order):
        entries = signals.get(label, [])
        active = " active" if i == 0 else ""
        tabs.append(
            f'<button class="tab{active}" data-tab="sig-{i}">{e(label)}'
            f"<i>{len(entries)}</i></button>"
        )
        if entries:
            items = "".join(
                f'<li><div class="sig-head"><strong>{e(s.sender)}</strong>'
                f'<span class="when">{_fmt_dt(s.timestamp)}</span></div>'
                f'<p>{e(s.text)}</p>'
                + (
                    '<div class="sig-links">'
                    + "".join(
                        f'<a href="{e(u)}" target="_blank" rel="noopener noreferrer">'
                        f"{e(u[:70])}</a>"
                        for u in s.links
                    )
                    + "</div>"
                    if s.links
                    else ""
                )
                + "</li>"
                for s in entries[:120]
            )
            body = f'<ul class="feed">{items}</ul>'
        else:
            body = '<p class="empty">No messages matched this signal.</p>'
        panels.append(f'<div class="panel{active}" id="sig-{i}">{body}</div>')

    signals_html = card(
        "Signal feeds",
        f'<div class="tabs">{"".join(tabs)}</div>{"".join(panels)}',
        "Messages matched by phrasing — e.g. \"I'm building\", \"just shipped\", "
        "\"we're hiring\". Pattern-matched, so read them as leads, not a complete list.",
    )

    # -- Conversation -------------------------------------------------------
    unanswered = [q for q in questions if q.answered_within_minutes is None]
    answered = [q for q in questions if q.answered_within_minutes is not None]
    peaks = stats_mod.engagement_peaks(chat)

    peak_rows = [
        [
            f'<span class="when">{_fmt_d(m.timestamp.date())}</span>',
            e(m.sender),
            f'<span class="ctx">{e(m.text[:220])}</span>',
            f"<strong>{n}</strong>",
        ]
        for m, n in peaks
    ]
    unanswered_rows = [
        [
            f'<span class="when">{_fmt_d(q.timestamp.date())}</span>',
            e(q.sender),
            f'<span class="ctx">{e(q.text[:220])}</span>',
        ]
        for q in sorted(unanswered, key=lambda q: q.timestamp, reverse=True)[:80]
    ]

    conversation_html = (
        '<div class="tiles compact">'
        + stat_tile(f"{len(questions):,}", "questions asked")
        + stat_tile(f"{len(answered):,}", "got a reply within an hour")
        + stat_tile(f"{len(unanswered):,}", "went unanswered")
        + stat_tile(
            f"{_pct(len(answered), len(questions))}%", "answer rate"
        )
        + "</div>"
        + card(
            "Messages that got the room talking",
            table(["Date", "From", "Message", "People who replied"], peak_rows),
            "Distinct people who posted within 10 minutes afterwards.",
        )
        + card(
            "Questions nobody answered",
            '<input class="filter" data-target="unanswered" type="search" '
            'placeholder="Filter unanswered questions">'
            + f'<div class="scroll" id="unanswered">'
            + table(["Date", "Asked by", "Question"], unanswered_rows)
            + "</div>",
            "No reply from anyone else within 60 minutes. Often the most useful "
            "list in here — these are the gaps the group left open.",
        )
    )

    # -- Language -----------------------------------------------------------
    words = text_mod.top_words(chat, 50)
    phrases = text_mod.top_phrases(chat, 2, 30)
    emoji = text_mod.top_emoji(chat, 30)

    language_html = (
        '<div class="grid-2">'
        + card("Words the group actually uses", bar_rows(words[:25], slot=6))
        + card("Recurring phrases", bar_rows(phrases[:25], slot=5))
        + "</div>"
        + card(
            "Emoji",
            '<div class="chips">'
            + "".join(
                f'<span class="chip big">{e(ch)}<i>{n}</i></span>' for ch, n in emoji
            )
            + "</div>",
        )
    )

    # -- Assemble -----------------------------------------------------------
    nav = [
        ("overview", "Overview"),
        ("shared", "What's shared"),
        ("tools", "Tools & tech"),
        ("signals", "Signals"),
        ("people", "People"),
        ("activity", "Activity"),
        ("conversation", "Conversation"),
        ("language", "Language"),
    ]
    nav_html = "".join(f'<a href="#{a}">{e(t)}</a>' for a, t in nav)

    body = "".join(
        [
            section("overview", "Overview",
                    f"{chat.source_name} · {_fmt_d(overview.first_message.date())} to "
                    f"{_fmt_d(overview.last_message.date())}", overview_html),
            section("shared", "What's being shared",
                    "Every link that passed through the group, grouped and searchable.",
                    shared_html),
            section("tools", "Tools & technology",
                    "Which tools the group talks about, how often, and by how many people.",
                    tools_html),
            section("signals", "Signals",
                    "People building, shipping, hiring, and asking for help.",
                    signals_html),
            section("people", "People",
                    "Who participates, how, and how much.", people_html),
            section("activity", "Activity patterns",
                    "When the group is alive and how quickly it responds.", activity_html),
            section("conversation", "Conversation health",
                    "What sparked discussion and what fell through the cracks.",
                    conversation_html),
            section("language", "Language",
                    "The group's vocabulary.", language_html),
        ]
    )

    generated = datetime.now().strftime("%d %b %Y at %H:%M")
    doc = _SHELL.format(
        title=e(f"{chat.source_name} — chat analysis"),
        heading=e(chat.source_name),
        subtitle=e(
            f"{total:,} messages from {overview.participants} people · "
            f"{_fmt_d(overview.first_message.date())} – "
            f"{_fmt_d(overview.last_message.date())}"
        ),
        generated=e(generated),
        nav=nav_html,
        body=body,
        css=_CSS,
        js=_JS,
        series_light=json.dumps(SERIES),
        series_dark=json.dumps(SERIES_DARK),
    )
    out_path.write_text(doc, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------

_CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  color-scheme:light;
  --surface:#fcfcfb; --plane:#f9f9f7;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s0:#2a78d6; --s1:#008300; --s2:#e87ba4; --s3:#eda100;
  --s4:#1baf7a; --s5:#eb6834; --s6:#4a3aa7; --s7:#e34948;
  --h0:#f0efec; --h1:#cde2fb; --h2:#b7d3f6; --h3:#9ec5f4; --h4:#86b6ef;
  --h5:#6da7ec; --h6:#5598e7; --h7:#3987e5; --h8:#2a78d6; --h9:#1c5cab;
  --h10:#104281;
}
@media (prefers-color-scheme:dark){
  :root:where(:not([data-theme="light"])){
    color-scheme:dark;
    --surface:#1a1a19; --plane:#0d0d0d;
    --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
    --s0:#3987e5; --s1:#008300; --s2:#d55181; --s3:#c98500;
    --s4:#199e70; --s5:#d95926; --s6:#9085e9; --s7:#e66767;
    --h0:#242422; --h1:#104281; --h2:#184f95; --h3:#1c5cab; --h4:#256abf;
    --h5:#2a78d6; --h6:#3987e5; --h7:#5598e7; --h8:#6da7ec; --h9:#86b6ef;
    --h10:#9ec5f4;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --surface:#1a1a19; --plane:#0d0d0d;
  --ink:#fff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --s0:#3987e5; --s1:#008300; --s2:#d55181; --s3:#c98500;
  --s4:#199e70; --s5:#d95926; --s6:#9085e9; --s7:#e66767;
  --h0:#242422; --h1:#104281; --h2:#184f95; --h3:#1c5cab; --h4:#256abf;
  --h5:#2a78d6; --h6:#3987e5; --h7:#5598e7; --h8:#6da7ec; --h9:#86b6ef;
  --h10:#9ec5f4;
}
body{
  margin:0; background:var(--plane); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;
}
header{
  position:sticky; top:0; z-index:20; background:var(--surface);
  border-bottom:1px solid var(--ring); padding:18px 24px 0;
}
.head-row{display:flex; align-items:baseline; gap:16px; flex-wrap:wrap}
h1{font-size:21px; margin:0; letter-spacing:-.01em}
.subtitle{color:var(--ink-2); font-size:13px}
.spacer{flex:1}
#theme{
  border:1px solid var(--ring); background:transparent; color:var(--ink-2);
  border-radius:999px; padding:5px 12px; font-size:12px; cursor:pointer;
}
#theme:hover{background:var(--plane)}
nav{display:flex; gap:2px; overflow-x:auto; margin-top:14px; scrollbar-width:none}
nav::-webkit-scrollbar{display:none}
nav a{
  color:var(--ink-2); text-decoration:none; font-size:13px; white-space:nowrap;
  padding:9px 12px; border-bottom:2px solid transparent;
}
nav a:hover{color:var(--ink); border-bottom-color:var(--axis)}
main{max-width:1180px; margin:0 auto; padding:28px 24px 80px}
section{margin-bottom:44px; scroll-margin-top:104px}
h2{font-size:19px; margin:0 0 4px; letter-spacing:-.01em}
h3{font-size:14px; margin:0 0 12px; font-weight:600}
.blurb{color:var(--ink-2); font-size:13px; margin:0 0 16px}
.note{color:var(--muted); font-size:12px; margin:-6px 0 12px}
.card{
  background:var(--surface); border:1px solid var(--ring); border-radius:12px;
  padding:18px; margin-bottom:14px;
}
.grid-2{display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:14px}
/* Fixed column count so 8 tiles land as 2 clean rows of 4 rather than 7+1. */
.tiles{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px}
.tiles.compact{grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
@media (max-width:880px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
.tile{background:var(--surface); border:1px solid var(--ring); border-radius:12px; padding:14px 16px}
.tile-value{font-size:25px; font-weight:650; letter-spacing:-.02em; line-height:1.15}
.tile-label{color:var(--ink-2); font-size:12px; margin-top:2px}
.tile-sub{color:var(--muted); font-size:11px; margin-top:3px}
.bars{display:flex; flex-direction:column; gap:7px}
.bar-row{display:grid; grid-template-columns:minmax(90px,190px) 1fr; gap:12px; align-items:center}
.bar-label{
  font-size:13px; color:var(--ink); overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; text-align:right;
}
.bar-sub{display:block; color:var(--muted); font-size:11px}
.bar-track{display:flex; align-items:center; gap:8px; min-width:0}
.bar-fill{height:14px; border-radius:0 4px 4px 0; min-width:3px}
.bar-value{font-size:12px; color:var(--ink-2); font-variant-numeric:tabular-nums; white-space:nowrap}
.heatmap{display:grid; grid-template-columns:34px repeat(24,1fr); gap:2px; align-items:center}
.hm-cell{aspect-ratio:1; border-radius:2px; background:var(--h0); min-height:11px}
.hm-daylabel{font-size:11px; color:var(--muted); text-align:right; padding-right:6px}
.hm-hourlabel{font-size:10px; color:var(--muted); text-align:center}
.hm-legend{display:flex; align-items:center; gap:3px; margin-top:12px; font-size:11px; color:var(--muted)}
.hm-legend i{width:13px; height:13px; border-radius:2px; background:var(--h0)}
[data-level="0"]{background:var(--h0)!important}
[data-level="1"]{background:var(--h1)!important}
[data-level="2"]{background:var(--h2)!important}
[data-level="3"]{background:var(--h3)!important}
[data-level="4"]{background:var(--h4)!important}
[data-level="5"]{background:var(--h5)!important}
[data-level="6"]{background:var(--h6)!important}
[data-level="7"]{background:var(--h7)!important}
[data-level="8"]{background:var(--h8)!important}
[data-level="9"]{background:var(--h9)!important}
[data-level="10"]{background:var(--h10)!important}
.chart-wrap{position:relative}
.timeline{width:100%; height:220px; overflow:visible}
.timeline .area{fill:var(--s0); opacity:.16}
.timeline .roll{fill:none; stroke:var(--s0); stroke-width:2; stroke-linejoin:round}
.timeline .grid{stroke:var(--grid); stroke-width:1}
.timeline .axis{fill:var(--muted); font-size:11px}
.timeline .crosshair{stroke:var(--axis); stroke-width:1; stroke-dasharray:3 3}
.timeline .cursor-dot{fill:var(--s0); stroke:var(--surface); stroke-width:2}
.chart-meta{color:var(--muted); font-size:11px; margin-top:8px}
.tip{
  position:absolute; pointer-events:none; background:var(--surface); color:var(--ink);
  border:1px solid var(--ring); border-radius:8px; padding:7px 10px; font-size:12px;
  box-shadow:0 4px 14px rgba(0,0,0,.13); white-space:nowrap; z-index:5;
}
table{width:100%; border-collapse:collapse; font-size:13px}
th{
  text-align:left; font-weight:600; font-size:11px; text-transform:uppercase;
  letter-spacing:.04em; color:var(--muted); padding:8px 10px;
  border-bottom:1px solid var(--axis); position:sticky; top:0; background:var(--surface);
}
td{padding:8px 10px; border-bottom:1px solid var(--grid); vertical-align:top}
tbody tr:hover{background:var(--plane)}
td:nth-child(n+2){font-variant-numeric:tabular-nums}
.scroll{max-height:560px; overflow:auto; border:1px solid var(--grid); border-radius:8px}
.filter{
  width:100%; padding:9px 12px; margin-bottom:10px; font-size:13px;
  border:1px solid var(--ring); border-radius:8px; background:var(--plane); color:var(--ink);
}
.filter:focus{outline:2px solid var(--s0); outline-offset:-1px}
.when{color:var(--muted); font-size:12px; white-space:nowrap}
.ctx{color:var(--ink-2)}
.pill{
  display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px;
  background:var(--plane); border:1px solid var(--ring); color:var(--ink-2); white-space:nowrap;
}
a{color:var(--s0)}
a:hover{opacity:.8}
.chips{display:flex; flex-wrap:wrap; gap:7px}
.chip{
  display:inline-flex; align-items:center; gap:6px; padding:5px 10px;
  border:1px solid var(--ring); border-radius:999px; font-size:13px; background:var(--plane);
}
.chip.big{font-size:17px}
.chip i{font-style:normal; color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums}
.tabs{display:flex; gap:4px; flex-wrap:wrap; margin-bottom:14px}
.tab{
  display:inline-flex; align-items:center; gap:7px; padding:7px 13px; font-size:13px;
  border:1px solid var(--ring); background:transparent; color:var(--ink-2);
  border-radius:999px; cursor:pointer; font-family:inherit;
}
.tab i{font-style:normal; font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums}
.tab:hover{background:var(--plane)}
.tab.active{background:var(--s0); border-color:var(--s0); color:#fff}
.tab.active i{color:rgba(255,255,255,.8)}
.panel{display:none}
.panel.active{display:block}
.feed{list-style:none; margin:0; padding:0; max-height:620px; overflow:auto}
.feed li{padding:12px 2px; border-bottom:1px solid var(--grid)}
.feed li:last-child{border-bottom:0}
.sig-head{display:flex; gap:10px; align-items:baseline; margin-bottom:4px}
.feed p{margin:0; color:var(--ink-2); font-size:13px; white-space:pre-wrap; word-break:break-word}
.sig-links{display:flex; flex-direction:column; gap:2px; margin-top:6px; font-size:12px}
.empty{color:var(--muted); font-size:13px; font-style:italic; margin:4px 0}
.warn{
  background:var(--plane); border:1px solid var(--ring); border-left:3px solid var(--s3);
  border-radius:8px; padding:12px 16px; margin-bottom:14px; font-size:13px; color:var(--ink-2);
}
.warn ul{margin:6px 0 0; padding-left:18px}
footer{color:var(--muted); font-size:12px; text-align:center; padding:24px}
@media (max-width:640px){
  main{padding:20px 14px 60px}
  .bar-row{grid-template-columns:minmax(72px,110px) 1fr}
  .heatmap{grid-template-columns:26px repeat(24,1fr); gap:1px}
}
"""

_JS = """
(function(){
  // Theme toggle — must beat the OS setting in both directions.
  var root=document.documentElement, btn=document.getElementById('theme');
  var saved=null; try{saved=localStorage.getItem('wa-theme')}catch(e){}
  if(saved) root.setAttribute('data-theme',saved);
  function label(){
    var dark = root.getAttribute('data-theme')==='dark' ||
      (!root.getAttribute('data-theme') &&
       matchMedia('(prefers-color-scheme:dark)').matches);
    btn.textContent = dark ? 'Light' : 'Dark';
  }
  label();
  btn.addEventListener('click',function(){
    var dark = root.getAttribute('data-theme')==='dark' ||
      (!root.getAttribute('data-theme') &&
       matchMedia('(prefers-color-scheme:dark)').matches);
    var next = dark ? 'light' : 'dark';
    root.setAttribute('data-theme',next);
    try{localStorage.setItem('wa-theme',next)}catch(e){}
    label();
  });

  // Tabs
  document.querySelectorAll('.tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      var group=tab.parentElement;
      group.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});
      tab.classList.add('active');
      var scope=group.parentElement;
      scope.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active')});
      var target=document.getElementById(tab.dataset.tab);
      if(target) target.classList.add('active');
    });
  });

  // Table filters
  document.querySelectorAll('.filter').forEach(function(input){
    input.addEventListener('input',function(){
      var q=input.value.toLowerCase().trim();
      var host=document.getElementById(input.dataset.target);
      if(!host) return;
      host.querySelectorAll('tbody tr').forEach(function(row){
        row.style.display = !q || row.textContent.toLowerCase().indexOf(q)>-1 ? '' : 'none';
      });
    });
  });

  // Sortable people table
  document.querySelectorAll('table.sortable th').forEach(function(th,col){
    th.style.cursor='pointer';
    th.title='Click to sort';
    var asc=false;
    th.addEventListener('click',function(){
      asc=!asc;
      var body=th.closest('table').tBodies[0];
      var rows=Array.prototype.slice.call(body.rows);
      rows.sort(function(a,b){
        var x=a.cells[col].textContent.trim(), y=b.cells[col].textContent.trim();
        var nx=parseFloat(x.replace(/[^0-9.\\-]/g,'')), ny=parseFloat(y.replace(/[^0-9.\\-]/g,''));
        var both=!isNaN(nx)&&!isNaN(ny);
        var cmp = both ? nx-ny : x.localeCompare(y);
        return asc ? cmp : -cmp;
      });
      rows.forEach(function(r){body.appendChild(r)});
    });
  });

  // Timeline crosshair + tooltip
  document.querySelectorAll('.chart-wrap').forEach(function(wrap){
    var raw=wrap.querySelector('.tl-data');
    var svg=wrap.querySelector('.timeline');
    if(!raw||!svg) return;
    var data=JSON.parse(raw.textContent);
    var tip=wrap.querySelector('.tip');
    var cross=svg.querySelector('.crosshair');
    var dot=svg.querySelector('.cursor-dot');
    var padL=44, padT=12, padB=26, W=1000, H=220;
    var plotW=W-padL-8, plotH=H-padB-padT;
    var peak=Math.max.apply(null,data.map(function(d){return d[1]}))||1;
    var step=plotW/Math.max(data.length-1,1);

    function show(ev){
      var box=svg.getBoundingClientRect();
      var vx=(ev.clientX-box.left)/box.width*W;
      var i=Math.round((vx-padL)/step);
      if(i<0) i=0; if(i>data.length-1) i=data.length-1;
      var x=padL+i*step, y=padT+plotH*(1-data[i][1]/peak);
      cross.setAttribute('x1',x); cross.setAttribute('x2',x); cross.style.opacity=1;
      dot.setAttribute('cx',x); dot.setAttribute('cy',y); dot.style.opacity=1;
      var d=new Date(data[i][0]+'T00:00:00');
      tip.hidden=false;
      tip.innerHTML='<strong>'+data[i][1].toLocaleString()+'</strong> messages<br>'+
        d.toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short',year:'numeric'});
      var px=x/W*box.width;
      tip.style.left=Math.min(Math.max(px-tip.offsetWidth/2,0),box.width-tip.offsetWidth)+'px';
      tip.style.top=Math.max(y/H*box.height-tip.offsetHeight-12,0)+'px';
    }
    function hide(){
      cross.style.opacity=0; dot.style.opacity=0; tip.hidden=true;
    }
    svg.addEventListener('mousemove',show);
    svg.addEventListener('mouseleave',hide);
    svg.addEventListener('touchmove',function(ev){
      if(ev.touches[0]) show(ev.touches[0]);
    },{passive:true});
  });
})();
"""

_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<header>
  <div class="head-row">
    <h1>{heading}</h1>
    <span class="subtitle">{subtitle}</span>
    <span class="spacer"></span>
    <button id="theme" type="button">Dark</button>
  </div>
  <nav>{nav}</nav>
</header>
<main>{body}</main>
<footer>Generated {generated} · analysed locally, nothing sent anywhere</footer>
<script>{js}</script>
</body>
</html>
"""

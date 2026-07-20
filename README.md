# Balagan · בלגן

**Your group chat is a beautiful mess. Let's see what's in it.**

Drop a WhatsApp export in and get every link, the tools people actually argue
about, who's quietly building something, and the questions nobody ever answered.

→ **[Open Balagan](https://myrondoesnotcode.github.io/balagan/)**

*Balagan* (בלגן) is Israeli slang for glorious chaos. It seemed apt.

---

## Nothing is uploaded

This is a static page with no backend. Your chat file is read and analysed
**inside your browser tab** — there is no server to send it to. Load the page
once, disconnect from the internet, and it still works.

That's not a promise about how the data is handled; it's a property of how the
thing is built. The whole analyser is JavaScript in `index.html`.

## What it pulls out

| | |
|---|---|
| **What's shared** | Every link, grouped by domain and type — code, research, video, events, launches. GitHub repos ranked. Who shares most. Full searchable table with the message context around each link. |
| **Tools & tech** | ~140 tools across AI models, dev tools, frameworks, infra, data, design and growth. Counted per tool *and* by how many distinct people mentioned it — that second number separates a real trend from one person's enthusiasm. |
| **Signals** | Feeds for *Building*, *Shipped / launched*, *Seeking feedback*, *Hiring*, *Asking for help*, *Events & meetups*. |
| **People** | Messages, share of conversation, average length, links and media, questions, active days, conversations started, replies received, emoji signature. |
| **Rhythm** | Volume over time with a 7-day average, an hour-by-weekday heatmap, and reply speed. |
| **Conversation** | Which messages got the room talking — and which questions nobody answered. |
| **Language** | Real vocabulary, recurring phrases, emoji. |

## How much to trust the numbers

The mechanical counts — messages, people, links, domains, timing, who replied
to whom — are exact. Read them as fact.

The interpretive layers are pattern-matched, and built to prefer precision over
recall, so a number you read is one you can trust without spot-checking:

- **Tool mentions** come from a curated vocabulary. Names that are ordinary
  English words (`go`, `dart`, `processing`) are deliberately excluded — a few
  genuine mentions are missed rather than inflating counts with false hits.
- **Signals** are phrase-matched. Leads worth following, not a complete census.
- **Discovered tools** is the noisiest panel by design, and says so.

## Getting an export

WhatsApp → open the group → tap the group name → **Export Chat** → **Without
Media**. Save the `.txt` or `.zip` and drop it in.

**Export Without Media.** WhatsApp caps exports at ~40,000 messages without
media but only ~10,000 with it, counting backward from the most recent — so a
with-media export can silently discard most of your history. If you want the
files too, do both exports separately.

Both iOS and Android formats work, 12- and 24-hour clocks, and `.zip` is
unpacked in the browser. Day-first vs month-first dates are inferred from the
file; when a file is genuinely ambiguous the report says so instead of guessing
silently.

## Batch version

`tools/` holds a Python version that processes many exports at once and writes
standalone HTML reports. Same analysis, no browser needed:

```bash
python3 tools/run.py path/to/export.txt --open
```

No dependencies beyond the standard library.

## Making it yours

- **Add tools to track** — `tools/analyzer/tools_dict.py`, and the `VOCAB`
  object in `index.html`. The "possibly tools we don't track yet" panel tells
  you what's worth adding.
- **Adjust signals** — `SIGDEF` in `index.html`, `_SIGNAL_PATTERNS` in
  `tools/analyzer/extract.py`.
- **Thresholds** — what counts as a reply (15 min) and what starts a new
  conversation (3 h), at the top of both implementations.

Keep the two in sync if you change one — they're independent implementations of
the same analysis, which is also how a dropped pattern got caught during
development.

## Licence

MIT.

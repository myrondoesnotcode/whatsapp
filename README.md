# Tzippy

**A WhatsApp analyzer that runs entirely in your browser.**

Drop in a WhatsApp export and get the links being shared, the tools people
actually use, who is building what, and the questions that never got answered.

→ **[Open Tzippy](https://myrondoesnotcode.github.io/whatsapp/)**

Not affiliated with or endorsed by WhatsApp or Meta. This reads export files you
produce yourself.

---

## Nothing is uploaded

Tzippy is a static page with no backend. Your chat file is read and analyzed
**inside your browser tab** — there is no server to send it to. Load the page
once, disconnect from the internet, and it still works.

That isn't a policy promise, it's a property of how it's built: the entire
analyzer is JavaScript in `index.html`.

## Share a card, still without a backend

Every report has a **Share** button. It builds a compact highlights card you can
post anywhere:

- **One-tap to WhatsApp.** A *Share to WhatsApp* button opens a pre-filled
  message; on mobile the native share sheet sends the card image straight into
  any app. This is the main loop — the audience is already on WhatsApp.
- **A link anyone can open.** The card's numbers are compressed and packed into
  the link itself (the `#card=…` fragment), so nothing is uploaded — the same
  property as the analysis. A URL fragment never leaves the browser, and because
  the whole card travels *inside* the link, one link works for any number of
  people at once with nothing to host.
- **An image for social.** A 1200×630 card (title, headline stats, a sparkline)
  with the site URL and *Analyze your own group — free →* burned in, so the
  invitation travels with the image even where a link won't preview.

Two kinds of card, chosen at the top of the dialog:

- **Group card** — the whole group at a glance. Carries **aggregate figures only
  by default** (no names). A per-card *Include names & awards* toggle adds a
  members leaderboard plus fun superlatives (**Top Yapper, Link Boss,
  Conversation Starter, Crowd Favorite…**) given to whoever tops each stat — made
  for sharing back into your own group and tagging the winners, with a clear
  warning that it publishes real names.
- **Personal card** — one member's own stats: message share, rank in the group,
  active days, their emoji signature, and any awards they hold. Identity content
  is the most-shared kind; pick yourself and post it.

Opening any shared link shows a clean standalone page with an *Analyze your own
chat* prompt back to Tzippy. A pasted link also shows a proper title, description
and preview image (`og.png`) on social — the one thing baked at build time rather
than per-card, since a static page can't render a preview from a URL fragment.

Nothing about sharing changes the privacy story: the recipient's browser decodes
the link locally, and the original chat is never part of it — only the figures on
the card.

## What it reports

| Section | What's in it |
|---|---|
| **Overview** | Volume, participants, span, media, questions, busiest day, and message volume over time with a 7-day average. |
| **Shared links** | Every URL grouped by domain and by type — code, research, video, events, launches. GitHub repos ranked. Who shares most. Full searchable table with the surrounding message. |
| **Tools & tech** | ~140 tools across AI models, dev tools, frameworks, infra, data, design and growth. Ranked by mentions *and* by how many distinct people mention each — the second number is what separates a real trend from one person's enthusiasm. |
| **Signals** | Feeds for *Building*, *Shipped / launched*, *Seeking feedback*, *Hiring*, *Asking for help*, *Events & meetups*. |
| **People** | Messages, share of conversation, average length, links and media, questions, active days, conversations started, replies received, emoji signature. |
| **Rhythm** | Hour-by-weekday heatmap, volume by month, reply speed distribution. |
| **Conversation health** | Which messages got the room talking, and which questions nobody answered. |
| **Language** | Vocabulary, recurring phrases, emoji. |

## How much to trust the numbers

The mechanical counts — messages, people, links, domains, timing, who replied to
whom — are exact. Read them as fact.

The interpretive layers are pattern-matched, and deliberately biased toward
precision over recall so that a number you read is one you can trust without
spot-checking:

- **Tool mentions** come from a curated vocabulary. Names that are ordinary
  English words (`go`, `dart`, `processing`) are excluded on purpose — a few
  genuine mentions are missed rather than inflating counts with false hits.
- **Signals** are phrase-matched. Leads worth following, not a complete census.
- **Discovered tools** is the noisiest panel by design, and labels itself as such.

## Getting an export

WhatsApp → open the group → tap the group name → **Export Chat** → **Without
Media**. Save the `.txt` or `.zip` and drop it in.

**Choose Without Media.** WhatsApp caps exports at roughly 40,000 messages
without media but only about 10,000 with it, counting backward from the most
recent — so a with-media export can silently discard most of your history. If
you want the files too, run both exports separately.

iOS and Android formats both work, 12- and 24-hour clocks, and `.zip` is
unpacked in the browser. Day-first vs month-first dates are inferred from the
file; when a file is genuinely ambiguous the report says so rather than guessing
silently.

## Batch version

`tools/` holds a Python implementation that processes many exports at once and
writes standalone HTML reports. Same analysis, no browser needed:

```bash
python3 tools/run.py path/to/export.txt --open
```

No dependencies beyond the standard library.

## Making it yours

- **Add tools to track** — the `VOCAB` object in `index.html`, and
  `tools/analyzer/tools_dict.py`. The "possibly tools we don't track yet" panel
  in each report tells you what's worth adding.
- **Adjust signals** — `SIGDEF` in `index.html`, `_SIGNAL_PATTERNS` in
  `tools/analyzer/extract.py`.
- **Thresholds** — what counts as a reply (15 minutes) and what starts a new
  conversation (3 hours), near the top of both implementations.

Keep the two in sync if you change one. They're independent implementations of
the same analysis, which is also how a dropped pattern got caught during
development — the browser build reported 174 "shipped" matches against Python's
206, and the diff found the missing rule.

## Licence

MIT.

"""Curated tool / technology vocabulary for a builder community.

Each entry maps a canonical display name to the regex alternatives that should
count as a mention. Patterns are embedded into a single word-boundary-anchored
regex per category, so they must not contain capturing groups.

Deliberately excluded: names that are common English words in their own right
("go", "rust" as a verb, "swift" as an adverb, "r", "dart", "processing"). A
false-positive mention is worse than a missed one here — the whole value of this
table is that a count you read is a count you can trust. Where a language is
worth tracking anyway, only its unambiguous form is listed ("golang").
"""

from __future__ import annotations

import re

TOOL_CATEGORIES: dict[str, dict[str, list[str]]] = {
    "AI models & labs": {
        "Claude": [r"claude", r"anthropic"],
        "ChatGPT / OpenAI": [r"chatgpt", r"openai", r"gpt-?[45]\S*", r"\bgpt\b"],
        "Gemini": [r"gemini", r"deepmind"],
        "Llama": [r"llama\s?\d*", r"meta ai"],
        "Mistral": [r"mistral"],
        "DeepSeek": [r"deepseek"],
        "Grok": [r"grok"],
        "Perplexity": [r"perplexity"],
        "Midjourney": [r"midjourney"],
        "Stable Diffusion": [r"stable diffusion", r"stablediffusion"],
        "ElevenLabs": [r"eleven\s?labs"],
        "Hugging Face": [r"hugging\s?face", r"huggingface"],
        "Cohere": [r"cohere"],
    },
    "AI dev tools": {
        "Cursor": [r"cursor"],
        "Claude Code": [r"claude code"],
        "GitHub Copilot": [r"copilot"],
        "LangChain": [r"langchain"],
        "LlamaIndex": [r"llama\s?index"],
        "Ollama": [r"ollama"],
        "Replicate": [r"replicate"],
        "Pinecone": [r"pinecone"],
        "Weaviate": [r"weaviate"],
        "Chroma": [r"chromadb", r"chroma db"],
        "RAG": [r"\brag\b", r"retrieval[- ]augmented"],
        "MCP": [r"\bmcp\b", r"model context protocol"],
        "n8n": [r"n8n"],
        "Zapier": [r"zapier"],
        "LangSmith": [r"langsmith"],
        "Windsurf": [r"windsurf"],
        "Bolt": [r"bolt\.new", r"\bbolt\b"],
        "Lovable": [r"lovable"],
        "v0": [r"\bv0\.dev\b", r"\bv0\b"],
    },
    "Dev environment": {
        "VS Code": [r"vs ?code", r"visual studio code"],
        "JetBrains": [r"jetbrains", r"intellij", r"pycharm", r"webstorm"],
        "Xcode": [r"xcode"],
        "Vim / Neovim": [r"neovim", r"\bnvim\b", r"\bvim\b"],
        "Docker": [r"docker"],
        "Kubernetes": [r"kubernetes", r"\bk8s\b"],
        "Git": [r"\bgit\b"],
        "GitHub": [r"github"],
        "GitLab": [r"gitlab"],
    },
    "Frameworks & languages": {
        "React": [r"react(?:\.js)?", r"react native"],
        "Next.js": [r"next\.?js"],
        "Vue": [r"vue(?:\.js)?"],
        "Svelte": [r"svelte(?:kit)?"],
        "Angular": [r"angular"],
        "Node.js": [r"node\.?js", r"\bnode\b"],
        "Deno": [r"\bdeno\b"],
        "Bun": [r"\bbun\b"],
        "Python": [r"python"],
        "TypeScript": [r"typescript", r"\bts\b"],
        "JavaScript": [r"javascript", r"\bjs\b"],
        "Golang": [r"golang"],
        "Rust": [r"\brust\b"],
        "Swift": [r"swiftui", r"\bswift\b"],
        "Kotlin": [r"kotlin"],
        "Django": [r"django"],
        "FastAPI": [r"fastapi"],
        "Flask": [r"flask"],
        "Rails": [r"rails", r"ruby on rails"],
        "Tailwind": [r"tailwind"],
        "Flutter": [r"flutter"],
    },
    "Infra & cloud": {
        "AWS": [r"\baws\b", r"amazon web services", r"\bec2\b", r"\bs3\b", r"lambda"],
        "Google Cloud": [r"\bgcp\b", r"google cloud"],
        "Azure": [r"azure"],
        "Vercel": [r"vercel"],
        "Netlify": [r"netlify"],
        "Cloudflare": [r"cloudflare"],
        "Railway": [r"railway\.app", r"\brailway\b"],
        "Render": [r"render\.com"],
        "Fly.io": [r"fly\.io"],
        "Supabase": [r"supabase"],
        "Firebase": [r"firebase"],
        "Heroku": [r"heroku"],
        "Modal": [r"modal\.com", r"modal labs"],
    },
    "Data & storage": {
        "PostgreSQL": [r"postgres(?:ql)?"],
        "MySQL": [r"mysql"],
        "MongoDB": [r"mongo(?:db)?"],
        "Redis": [r"redis"],
        "SQLite": [r"sqlite"],
        "Snowflake": [r"snowflake"],
        "BigQuery": [r"bigquery"],
        "DuckDB": [r"duckdb"],
        "Prisma": [r"prisma"],
        "Elasticsearch": [r"elasticsearch", r"\belastic\b"],
    },
    "Design & product": {
        "Figma": [r"figma"],
        "Framer": [r"framer"],
        "Canva": [r"canva"],
        "Sketch": [r"sketch\.app"],
        "Webflow": [r"webflow"],
    },
    "Work & productivity": {
        "Notion": [r"notion"],
        "Linear": [r"linear\.app"],
        "Slack": [r"slack"],
        "Jira": [r"jira"],
        "Airtable": [r"airtable"],
        "Miro": [r"miro"],
        "Loom": [r"loom"],
        "Zoom": [r"zoom"],
        "Discord": [r"discord"],
        "Telegram": [r"telegram"],
    },
    "Business & growth": {
        "Stripe": [r"stripe"],
        "Shopify": [r"shopify"],
        "HubSpot": [r"hubspot"],
        "Segment": [r"segment\.com"],
        "Mixpanel": [r"mixpanel"],
        "Amplitude": [r"amplitude"],
        "PostHog": [r"posthog"],
        "Product Hunt": [r"product ?hunt"],
        "Y Combinator": [r"y ?combinator", r"\byc\b"],
    },
}


def _compile(patterns: list[str]) -> re.Pattern[str]:
    # (?<![\w-]) / (?![\w-]) keeps "gpt" from matching inside "gpt-4-turbo" twice
    # and stops "node" from firing inside "nodemon".
    body = "|".join(f"(?:{p})" for p in patterns)
    return re.compile(rf"(?<![\w-])(?:{body})(?![\w-])", re.I)


#: canonical name -> (category, compiled matcher)
COMPILED: dict[str, tuple[str, re.Pattern[str]]] = {
    name: (category, _compile(patterns))
    for category, entries in TOOL_CATEGORIES.items()
    for name, patterns in entries.items()
}


# Words that look like product names when capitalised mid-sentence but aren't.
# Used by the "unknown tool" discovery heuristic in extract.py.
DISCOVERY_STOPWORDS = {
    "i", "a", "an", "the", "and", "or", "but", "if", "so", "then", "than",
    "this", "that", "these", "those", "there", "here", "what", "when", "where",
    "who", "why", "how", "which", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "can", "could", "will", "would",
    "should", "may", "might", "must", "shall", "not", "no", "yes", "ok", "okay",
    "hi", "hey", "hello", "thanks", "thank", "please", "sorry", "sure", "great",
    "good", "nice", "cool", "awesome", "amazing", "love", "like", "just", "also",
    "really", "very", "much", "many", "some", "any", "all", "more", "most",
    "we", "you", "they", "he", "she", "it", "me", "us", "them", "my", "your",
    "our", "their", "his", "her", "its", "im", "ive", "id", "ill", "its",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "tel", "aviv", "israel", "israeli", "deploy", "tlv",
    "for", "with", "from", "to", "at", "on", "in", "of", "by", "as", "about",
    "check", "let", "see", "get", "got", "know", "think", "need", "want", "make",
    "guys", "everyone", "anyone", "someone", "folks", "team", "group", "chat",
    "today", "tomorrow", "yesterday", "tonight", "week", "month", "year", "day",
    "message", "deleted", "omitted", "media", "image", "video", "audio",
}

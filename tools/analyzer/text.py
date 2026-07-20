"""Vocabulary, emoji and phrase analysis."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .parser import Chat

_WORD = re.compile(r"[a-zA-Z][a-zA-Z'\-]{1,}", re.UNICODE)
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "so", "as", "at",
    "by", "for", "from", "in", "into", "of", "on", "to", "with", "without",
    "about", "after", "before", "over", "under", "up", "down", "out", "off",
    "this", "that", "these", "those", "there", "here", "it", "its", "is", "am",
    "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "will", "would", "should", "could", "can",
    "may", "might", "must", "shall", "not", "no", "nor", "only", "own", "same",
    "too", "very", "just", "now", "also", "any", "all", "both", "each", "few",
    "more", "most", "other", "some", "such", "who", "whom", "what", "which",
    "when", "where", "why", "how", "i", "me", "my", "myself", "we", "our",
    "ours", "you", "your", "yours", "he", "him", "his", "she", "her", "they",
    "them", "their", "theirs", "im", "ive", "id", "ill", "youre", "youve",
    "dont", "doesnt", "didnt", "cant", "wont", "isnt", "arent", "thats",
    "whats", "lets", "hes", "shes", "theyre", "weve", "wed", "ok", "okay",
    "yes", "yeah", "yep", "no", "nope", "hi", "hey", "hello", "thanks",
    "thank", "please", "sorry", "sure", "get", "got", "go", "going", "went",
    "know", "think", "see", "like", "want", "need", "make", "made", "take",
    "one", "two", "good", "great", "nice", "cool", "really", "much", "many",
    "lol", "haha", "omitted", "media", "image", "video", "audio", "sticker",
    "message", "deleted", "attached", "document", "gif", "www", "http", "https",
    "com", "org", "net", "youre",
}


def top_words(chat: Chat, limit: int = 60) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for msg in chat.people_messages:
        if msg.kind != "text":
            continue
        body = _URL.sub(" ", msg.text).lower()
        for word in _WORD.findall(body):
            clean = word.strip("'-")
            if len(clean) > 2 and clean not in STOPWORDS:
                counts[clean] += 1
    return counts.most_common(limit)


def _is_emoji(ch: str) -> bool:
    code = ord(ch)
    if code < 0x2100 or 0xFE00 <= code <= 0xFE0F or code == 0x200D:
        return False
    return unicodedata.category(ch) in {"So", "Sk"} or code >= 0x1F000


def top_emoji(chat: Chat, limit: int = 40) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for msg in chat.people_messages:
        if msg.kind != "text":
            continue
        for ch in msg.text:
            if _is_emoji(ch):
                counts[ch] += 1
    return counts.most_common(limit)


def emoji_by_person(chat: Chat, limit: int = 3) -> dict[str, list[tuple[str, int]]]:
    per_person: dict[str, Counter] = {}
    for msg in chat.people_messages:
        if msg.kind != "text":
            continue
        counter = per_person.setdefault(msg.sender, Counter())  # type: ignore[arg-type]
        for ch in msg.text:
            if _is_emoji(ch):
                counter[ch] += 1
    return {
        name: counter.most_common(limit)
        for name, counter in per_person.items()
        if counter
    }


def top_phrases(chat: Chat, size: int = 2, limit: int = 30) -> list[tuple[str, int]]:
    """Frequent n-grams, ignoring any that are entirely stopwords."""
    counts: Counter = Counter()
    for msg in chat.people_messages:
        if msg.kind != "text":
            continue
        body = _URL.sub(" ", msg.text).lower()
        words = [w.strip("'-") for w in _WORD.findall(body)]
        words = [w for w in words if len(w) > 1]
        for i in range(len(words) - size + 1):
            gram = words[i : i + size]
            if all(w in STOPWORDS for w in gram):
                continue
            if any(len(w) < 3 for w in gram):
                continue
            counts[" ".join(gram)] += 1
    return [(phrase, n) for phrase, n in counts.most_common(limit * 3) if n >= 3][:limit]

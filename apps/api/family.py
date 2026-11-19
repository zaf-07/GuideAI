import difflib
import os
import re
import sqlite3
import threading
from pathlib import Path

MAX_CONTACTS = 50
MAX_PLACES = 20

IGNORED_WORDS = {
    "where", "did", "does", "do", "you", "see", "seen", "saw", "last", "leave", "left", "put", "have",
    "what", "that", "this", "the", "my", "are", "is", "was", "were", "say", "said", "remember", "and",
    "for", "with", "any", "there", "here", "it", "me", "a", "an", "of", "in", "on", "i", "to",
    "tell", "text", "message", "send", "write", "friend", "please", "hey", "whatsapp",
    "them", "they", "their", "then", "than", "time", "some", "same", "want",
}


def _sound(word: str) -> str:
    key = word.lower().replace("ck", "k").replace("ch", "k").replace("ph", "f").replace("c", "k").replace("z", "s")
    key = key[0] + re.sub(r"[aeiouyh]", "", key[1:])
    return re.sub(r"(.)\1+", r"\1", key)


def default_path() -> str:
    return os.getenv("FAMILY_DB") or str(Path(__file__).with_name("data") / "family.sqlite3")


class Family:
    def __init__(self, path: str | None = None) -> None:
        path = path or default_path()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS contacts "
                "(owner TEXT, key TEXT, name TEXT, phone TEXT, PRIMARY KEY (owner, key))"
            )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS places "
                "(owner TEXT, name TEXT, label TEXT, lat REAL, lon REAL, PRIMARY KEY (owner, name))"
            )

    def contacts(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT name, phone FROM contacts WHERE owner = ? ORDER BY name", (owner,),
            ).fetchall()
        return [{"name": row[0], "phone": row[1]} for row in rows]

    def add_contact(self, owner: str, name: str, phone: str) -> dict:
        name, digits = name.strip()[:40], re.sub(r"\D", "", phone)
        if not name or not 7 <= len(digits) <= 15:
            raise ValueError("A contact needs a name and a phone number with country code.")
        with self._lock, self._db:
            known = self._db.execute(
                "SELECT COUNT(*) FROM contacts WHERE owner = ? AND key != ?", (owner, name.lower()),
            ).fetchone()[0]
            if known >= MAX_CONTACTS:
                raise ValueError(f"You can keep up to {MAX_CONTACTS} contacts.")
            self._db.execute("INSERT OR REPLACE INTO contacts VALUES (?, ?, ?, ?)", (owner, name.lower(), name, digits))
        return {"name": name, "phone": digits}

    def remove_contact(self, owner: str, name: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM contacts WHERE owner = ? AND key = ?", (owner, name.strip().lower()))

    def find_contact(self, owner: str, text: str) -> dict | None:
        words = text.lower()
        contacts = self.contacts(owner)
        for contact in contacts:
            if re.search(rf"\b{re.escape(contact['name'].lower())}\b", words):
                return contact
        heard = {word[:-1] if word.endswith("s") and len(word) > 3 else word for word in re.findall(r"[a-z]+", words)}
        heard -= IGNORED_WORDS
        best, best_score = None, 0.0
        for contact in contacts:
            first = contact["name"].lower().split()[0]
            for word in heard:
                if len(word) < 3 or word[0] != first[0]:
                    continue
                score = difflib.SequenceMatcher(None, word, first).ratio()
                if _sound(word) == _sound(first):
                    score = max(score, 0.9)
                if score > best_score:
                    best, best_score = contact, score
        return best if best_score >= 0.74 else None

    def places(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT name, label, lat, lon FROM places WHERE owner = ? ORDER BY name", (owner,),
            ).fetchall()
        return [{"name": row[0], "label": row[1], "lat": row[2], "lon": row[3]} for row in rows]

    def place(self, owner: str, name: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT name, label, lat, lon FROM places WHERE owner = ? AND name = ?", (owner, name.lower()),
            ).fetchone()
        return {"name": row[0], "label": row[1], "lat": row[2], "lon": row[3]} if row else None

    def save_place(self, owner: str, name: str, label: str, lat: float, lon: float) -> dict:
        name = name.strip().lower()[:20] or "home"
        with self._lock, self._db:
            known = self._db.execute(
                "SELECT COUNT(*) FROM places WHERE owner = ? AND name != ?", (owner, name),
            ).fetchone()[0]
            if known >= MAX_PLACES:
                raise ValueError(f"You can keep up to {MAX_PLACES} saved places.")
            self._db.execute("INSERT OR REPLACE INTO places VALUES (?, ?, ?, ?, ?)", (owner, name, label, lat, lon))
        return {"name": name, "label": label, "lat": lat, "lon": lon}

    def remove_place(self, owner: str, name: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM places WHERE owner = ? AND name = ?", (owner, name.strip().lower()))

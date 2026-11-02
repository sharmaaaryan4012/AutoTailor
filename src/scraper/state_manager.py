"""
src/scraper/state_manager.py
-----------------------------
Atomic JSON state manager for tracking seen job fingerprints and rejected listings.

State file: data/watch_state.json
Schema:
    {
        "schema_version": 2,
        "last_run": "<ISO 8601 UTC>",
        "seen_fingerprints": {
            "<sha256_hex>": "<ISO 8601 UTC timestamp>"
        },
        "rejected_jobs": [
            {
                "fingerprint": "<sha256_hex>",
                "company": "...",
                "title": "...",
                "url": "...",
                "reason": "HARD_REJECT | IRRELEVANT | OVERFLOW | ...",
                "matched_pattern": "...",
                "rejected_at": "<ISO 8601 UTC>"
            }
        ]
    }

Write strategy: write to a .tmp file, then os.replace() — POSIX atomic rename.
This guarantees the state file is never left in a corrupt partial-write state
even on KeyboardInterrupt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path("data/watch_state.json")
_SCHEMA_VERSION = 2
_FINGERPRINT_TTL_DAYS = 90


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(url: str, title: str, company: str) -> str:
    """
    Compute a stable SHA-256 fingerprint for a job listing.

    Formula: SHA256( normalize(company) + "|" + normalize(title) + "|" + url )
    normalize() lowercases and strips leading/trailing whitespace.
    """
    key = f"{company.strip().lower()}|{title.strip().lower()}|{url.strip()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class StateManager:
    """
    Load, query, and atomically persist watch_state.json.

    Usage:
        sm = StateManager()
        if sm.is_new(url, title, company):
            ...
            sm.mark_seen(url, title, company)
            sm.save()
    """

    def __init__(self, path: str | Path = _STATE_PATH) -> None:
        self.path = Path(path)
        self._state: dict = self._load()

    # ── Load ─────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.path.exists():
            logger.info("No state file found at %s — starting fresh", self.path)
            return self._empty_state()

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Failed to read state file %s: %s — starting fresh", self.path, exc
            )
            return self._empty_state()

        # Migrate from schema_version 1 (no rejected_jobs list)
        if data.get("schema_version", 1) < _SCHEMA_VERSION:
            data.setdefault("rejected_jobs", [])
            data["schema_version"] = _SCHEMA_VERSION
            logger.info("Migrated state to schema_version %d", _SCHEMA_VERSION)

        return data

    @staticmethod
    def _empty_state() -> dict:
        return {
            "schema_version": _SCHEMA_VERSION,
            "last_run": None,
            "seen_fingerprints": {},
            "rejected_jobs": [],
        }

    # ── Query ─────────────────────────────────────────────────────────────────

    def is_new(self, url: str, title: str, company: str) -> bool:
        """Return True if this job has NOT been seen before."""
        fp = _fingerprint(url, title, company)
        return fp not in self._state["seen_fingerprints"]

    def fingerprint(self, url: str, title: str, company: str) -> str:
        """Public accessor for the fingerprint of a given listing."""
        return _fingerprint(url, title, company)

    # ── Mutate ────────────────────────────────────────────────────────────────

    def mark_seen(self, url: str, title: str, company: str) -> str:
        """
        Record a fingerprint as seen. Returns the fingerprint hex string.
        Call save() after all mutations to persist.
        """
        fp = _fingerprint(url, title, company)
        self._state["seen_fingerprints"][fp] = _now_iso()
        return fp

    def mark_rejected(
        self,
        url: str,
        title: str,
        company: str,
        reason: str,
        matched_pattern: str | None = None,
    ) -> None:
        """
        Log a rejected listing. Also marks it as seen so it won't be
        re-evaluated on the next run.
        """
        fp = self.mark_seen(url, title, company)
        self._state["rejected_jobs"].append(
            {
                "fingerprint": fp,
                "company": company,
                "title": title,
                "url": url,
                "reason": reason,
                "matched_pattern": matched_pattern,
                "rejected_at": _now_iso(),
            }
        )

    def update_last_run(self) -> None:
        self._state["last_run"] = _now_iso()

    # ── Prune ─────────────────────────────────────────────────────────────────

    def prune_old_fingerprints(self) -> int:
        """
        Remove fingerprints older than _FINGERPRINT_TTL_DAYS days.
        Returns the number of entries pruned.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - _FINGERPRINT_TTL_DAYS * 86400
        fps = self._state["seen_fingerprints"]
        old_keys = [
            k for k, ts in fps.items()
            if datetime.fromisoformat(ts).timestamp() < cutoff
        ]
        for k in old_keys:
            del fps[k]
        if old_keys:
            logger.info("Pruned %d stale fingerprints (>%dd old)", len(old_keys), _FINGERPRINT_TTL_DAYS)
        return len(old_keys)

    # ── Persist ───────────────────────────────────────────────────────────────

    def save(self) -> None:
        """
        Atomically write state to disk using write-then-rename.
        Safe against KeyboardInterrupt and partial writes.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")

        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, self.path)
            logger.debug(
                "State saved: %d fingerprints, %d rejected",
                len(self._state["seen_fingerprints"]),
                len(self._state["rejected_jobs"]),
            )
        except OSError as exc:
            logger.error("Failed to save state to %s: %s", self.path, exc)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def seen_count(self) -> int:
        return len(self._state["seen_fingerprints"])

    @property
    def rejected_count(self) -> int:
        return len(self._state["rejected_jobs"])

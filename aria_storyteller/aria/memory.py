"""
memory.py — ChromaDB-backed persistent story memory for Aria.
Stores: story events, character states, world facts, and conversation turns.
"""

import os
import uuid
import json
from datetime import datetime
from typing import Optional
import chromadb
from chromadb.config import Settings


class StoryMemory:
    """Persistent ChromaDB memory with every story record scoped by story_id."""

    def __init__(self, persist_path: str = "./chroma_db"):
        os.makedirs(persist_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_path)

        # Collections
        self.story_events    = self._get_or_create("story_events")
        self.characters      = self._get_or_create("characters")
        self.world_facts     = self._get_or_create("world_facts")
        self.dialogue_log    = self._get_or_create("dialogue_log")
        self.story_meta      = self._get_or_create("story_metadata")

    def _get_or_create(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )

    # ── Story metadata ──────────────────────────────────────────────────

    def save_story_meta(self, story_id: str, title: str, summary: str = ""):
        self.story_meta.upsert(
            ids=[story_id],
            documents=[f"{title}\n{summary}"],
            metadatas=[{
                "story_id": story_id,
                "title": title,
                "created_at": datetime.now().isoformat(),
                "active": "true"
            }]
        )

    def get_active_story(self) -> Optional[dict]:
        results = self.story_meta.get(where={"active": "true"})
        if results["ids"]:
            meta = results["metadatas"][0]
            meta["document"] = results["documents"][0]
            return meta
        return None

    def deactivate_story(self, story_id: str):
        self.story_meta.update(
            ids=[story_id],
            metadatas=[{"active": "false"}]
        )

    def list_stories(self) -> list:
        results = self.story_meta.get()
        stories = []
        for i, sid in enumerate(results["ids"]):
            m = results["metadatas"][i]
            m["id"] = sid
            stories.append(m)
        return stories

    # ── Story events ────────────────────────────────────────────────────

    def add_event(self, story_id: str, event_text: str, event_type: str = "scene"):
        eid = str(uuid.uuid4())
        self.story_events.add(
            ids=[eid],
            documents=[event_text],
            metadatas=[{
                "story_id": story_id,
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "turn": self._count_events(story_id)
            }]
        )
        return eid

    def _count_events(self, story_id: str) -> int:
        results = self.story_events.get(where={"story_id": story_id})
        return len(results["ids"])

    def get_recent_events(self, story_id: str, n: int = 10) -> list[str]:
        results = self.story_events.get(where={"story_id": story_id})
        if not results["documents"]:
            return []
        # Sort by timestamp
        paired = list(zip(results["metadatas"], results["documents"]))
        paired.sort(key=lambda x: x[0].get("timestamp", ""))
        return [doc for _, doc in paired[-n:]]

    def search_events(self, story_id: str, query: str, n: int = 5) -> list[str]:
        results = self.story_events.query(
            query_texts=[query],
            n_results=min(n, max(1, self._count_events(story_id))),
            where={"story_id": story_id}
        )
        return results["documents"][0] if results["documents"] else []

    # ── Characters ──────────────────────────────────────────────────────

    def upsert_character(self, story_id: str, name: str, description: str,
                          traits: list[str] = None, role: str = "npc",
                          emotional_state: str = "neutral"):
        char_id = f"{story_id}_{name.lower().replace(' ', '_')}"
        self.characters.upsert(
            ids=[char_id],
            documents=[description],
            metadatas=[{
                "story_id": story_id,
                "name": name,
                "role": role,
                "traits": json.dumps(traits or []),
                "emotional_state": emotional_state,
                "updated_at": datetime.now().isoformat()
            }]
        )
        return char_id

    def get_characters(self, story_id: str) -> list[dict]:
        results = self.characters.get(where={"story_id": story_id})
        chars = []
        for i, cid in enumerate(results["ids"]):
            m = results["metadatas"][i]
            m["description"] = results["documents"][i]
            m["id"] = cid
            m["traits"] = json.loads(m.get("traits", "[]"))
            chars.append(m)
        return chars

    def update_character_state(self, story_id: str, name: str, emotional_state: str):
        char_id = f"{story_id}_{name.lower().replace(' ', '_')}"
        try:
            self.characters.update(
                ids=[char_id],
                metadatas=[{
                    "story_id": story_id,
                    "name": name,
                    "emotional_state": emotional_state,
                    "updated_at": datetime.now().isoformat()
                }]
            )
        except Exception:
            pass  # Character may not exist yet

    # ── World facts ─────────────────────────────────────────────────────

    def add_world_fact(self, story_id: str, fact: str, category: str = "general"):
        fid = str(uuid.uuid4())
        self.world_facts.add(
            ids=[fid],
            documents=[fact],
            metadatas=[{
                "story_id": story_id,
                "category": category,
                "timestamp": datetime.now().isoformat()
            }]
        )

    def get_world_facts(self, story_id: str) -> list[str]:
        results = self.world_facts.get(where={"story_id": story_id})
        return results["documents"] if results["documents"] else []

    # ── Dialogue log ────────────────────────────────────────────────────

    def log_dialogue(self, story_id: str, speaker: str, content: str, mode: str = "chat"):
        """mode: 'chat' = me:"..." | 'action' = me:*...*"""
        did = str(uuid.uuid4())
        self.dialogue_log.add(
            ids=[did],
            documents=[content],
            metadatas=[{
                "story_id": story_id,
                "speaker": speaker,
                "mode": mode,
                "timestamp": datetime.now().isoformat()
            }]
        )

    def get_recent_dialogue(self, story_id: str, n: int = 20) -> list[dict]:
        results = self.dialogue_log.get(where={"story_id": story_id})
        if not results["documents"]:
            return []
        paired = list(zip(results["metadatas"], results["documents"]))
        paired.sort(key=lambda x: x[0].get("timestamp", ""))
        out = []
        for meta, doc in paired[-n:]:
            out.append({"speaker": meta["speaker"], "content": doc, "mode": meta["mode"]})
        return out

    # ── Context builder ─────────────────────────────────────────────────

    def build_context_snapshot(self, story_id: str, query: str = "") -> str:
        """Build a rich context string to inject into the LLM prompt."""
        events = self.get_recent_events(story_id, n=8)
        chars = self.get_characters(story_id)
        facts = self.get_world_facts(story_id)
        dialogue = self.get_recent_dialogue(story_id, n=12)

        # Semantic search for relevance
        relevant = []
        if query:
            relevant = self.search_events(story_id, query, n=3)

        lines = ["═══ STORY MEMORY SNAPSHOT ═══"]

        if facts:
            lines.append("\n[World Rules & Facts]")
            for f in facts[:5]:
                lines.append(f"  • {f}")

        if chars:
            lines.append("\n[Characters]")
            for c in chars:
                traits_str = ", ".join(c["traits"]) if c["traits"] else "unknown"
                lines.append(f"  • {c['name']} ({c['role']}) — {c['description'][:80]} | Feeling: {c['emotional_state']} | Traits: {traits_str}")

        if events:
            lines.append("\n[Recent Story Events]")
            for e in events:
                lines.append(f"  {e[:120]}")

        if relevant:
            lines.append("\n[Relevant Past Events]")
            for e in relevant:
                lines.append(f"  {e[:120]}")

        if dialogue:
            lines.append("\n[Recent Dialogue]")
            for d in dialogue:
                prefix = "me:*action*" if d["mode"] == "action" else f"{d['speaker']}:"
                lines.append(f"  {prefix} {d['content'][:100]}")

        lines.append("═══════════════════════════════")
        return "\n".join(lines)

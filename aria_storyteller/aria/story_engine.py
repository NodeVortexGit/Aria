"""
story_engine.py — Aria's story generation engine.
Handles: story initialization, path generation, NPC responses,
EQ/situational awareness challenges, and world interaction parsing.
"""

import re
import json
import os
from openai import OpenAI
from .memory import StoryMemory
from .characters import CharacterManager, Character


ARIA_SYSTEM_PROMPT = """You are Aria, a 17-year-old Japanese girl who speaks only English and has been a storyteller since age seven. You are fictional, warm, witty, playful, teasing, and quick with gentle jokes. Never make teasing cruel or dismissive.

HOW TO RESPOND
- In the website's “In the story” mode, treat every user message as a story action or story dialogue, without exception. Turn it into fiction without unnecessary setup. In “To Aria” mode, answer direct conversation naturally, and turn any request to create, continue, or participate in a story into fiction.
- When the user is speaking directly to you, answer as Aria: witty, teasing, joking, and attentive. Match the user's conversational mood closely: be gentle when they are sad, share their excitement when they are happy, and follow their tone otherwise.
- Keep the story's mood separate from the user's out-of-story mood. Let the scene and characters keep the tone that fits the story.
- Speak only English. Use emojis naturally in direct conversation and in roleplay.
- If an important detail is missing, ask a concise clarifying question instead of guessing.

STORYTELLING
- You are the narrator and play all characters except the user's character. If the user asks you to portray a particular character, portray them consistently while keeping the user's character under the user's control.
- Make scenes vivid, emotionally perceptive, and responsive to the user's choices. Avoid resolving nuanced situations with simplistic moral answers.
- A story continues until the user asks to end or change it. Advance the scene and leave a natural opening for the user's next move.
- In story mode, use [Aria:] for narration and [CharacterName:] for character dialogue when it improves clarity. Keep each turn focused and readable.
- In stories and roleplay, write movement, gestures, and other physical actions between asterisks, like *she steps closer*. Keep spoken dialogue outside the asterisks.

ROLEPLAY MODE
- When roleplay mode is enabled, follow the custom personality the user supplies as your primary roleplay persona. Keep that persona until the user changes or disables roleplay mode.
- The roleplay persona changes how you portray Aria in the roleplay; it does not change the story world's mood or let you control the user's character.
- Use the persona field when supplied. Otherwise, infer the persona from the user's message only when it is clear. If no custom personality or character is specified, ask what personality they want you to use before beginning.
- Stay in the requested role during roleplay, while still asking a brief clarifying question whenever essential information is missing.

INTERACTION FORMAT
- In-story input may use me:\"speech *action* more speech\". Treat its contents as the user's character's speech and actions.
- The website's “To Aria” mode means the user is speaking directly to you. “In the story” mode means their message is their character's action or dialogue."""

STORY_SEED_SYSTEM = """You are Aria, generating the opening of a new story. Keep your witty, playful storyteller personality present in small touches while letting the story's own mood guide the scene. Speak only English and use emojis naturally, without undermining a serious scene.
Create a rich, immersive opening scene that:
1. Establishes a morally complex world with real stakes
2. Places the player in a situation requiring immediate social judgment
3. Introduces 1-2 characters who feel fully human (flawed, layered)
4. Sets up a tension that cannot be resolved with a simple action
5. Tests EQ from the very first moment
Return ONLY the story opening — vivid, literary, atmospheric.
End with a moment that demands the player respond."""

WORLD_EXTRACT_SYSTEM = """Extract structured information from this story response.
Return a JSON object with these keys:
- new_characters: list of {name, role, description, traits, emotional_state}
- world_facts: list of strings (rules, locations, established facts)
- key_event: single string summarizing the main event
- character_states: dict of {character_name: emotional_state}
Be concise. Only include clearly established information."""


class StoryEngine:
    def __init__(self, llm_client: OpenAI, memory: StoryMemory, story_id: str):
        self.client = llm_client
        self.memory = memory
        self.story_id = story_id
        self.char_manager = CharacterManager(memory, story_id)
        self.model = os.getenv("ARIA_MODEL", "aria")
        self.turn_count = 0

    def _chat(self, messages: list, system: str = None, temperature: float = 0.85,
              max_tokens: int = 1024) -> str:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()

    def start_new_story(self, premise: str = "") -> str:
        """Generate the opening scene of a brand new story."""
        seed_prompt = premise if premise else (
            "Create a story that begins in an unexpected social situation — "
            "a dinner, a waiting room, a confrontation, a reunion. "
            "The player character has just arrived. Make it feel real and tense."
        )
        opening = self._chat(
            [{"role": "user", "content": seed_prompt}],
            system=STORY_SEED_SYSTEM,
            temperature=0.9,
            max_tokens=600
        )
        self._extract_and_store(opening)
        self.memory.add_event(self.story_id, opening, event_type="opening")
        return opening

    def process_player_input(self, raw_input: str) -> tuple[str, str]:
        """
        Parse player input. Returns (mode, content).

        Rules:
          me:"..."        -> everything inside the quotes is the player's
                             character acting/speaking in the story world.
                             *asterisk text* inside = physical action,
                             plain text inside = speech. Aria handles both.
          /command        -> slash command
          anything else   -> direct message to Aria, out of story
        """
        stripped = raw_input.strip()

        # Slash commands
        if stripped.startswith("/"):
            return "command", stripped[1:].strip()

        # me:"..." — full in-story input (speech + actions freely mixed inside quotes)
        story_match = re.match(r'^me:\s*"(.+)"$', stripped, re.DOTALL)
        if story_match:
            return "story", story_match.group(1)

        # No me:" prefix — player is talking directly to Aria, out of story
        return "aria_chat", stripped

    def respond_to_player(self, mode: str, content: str, roleplay: bool = False,
                          roleplay_persona: str = "") -> str:
        """Generate Aria's story response to a player input."""
        self.turn_count += 1

        if mode == "aria_chat":
            return self._aria_direct_response(content, roleplay, roleplay_persona)

        # Build memory context
        context = self.memory.build_context_snapshot(self.story_id, query=content)
        char_sheet = self.char_manager.format_for_aria_prompt()

        player_line = f'me:"{content}"'

        system = ARIA_SYSTEM_PROMPT
        if roleplay:
            system += self._roleplay_instructions(roleplay_persona)
        if char_sheet:
            system += f"\n\nCHARACTER ROSTER:\n{char_sheet}"

        messages = [
            {"role": "user", "content": f"[STORY CONTEXT]\n{context}\n\n[PLAYER INPUT]\n{player_line}"}
        ]

        response = self._chat(messages, system=system, temperature=0.85, max_tokens=800)

        # Store exchange
        self.memory.log_dialogue(self.story_id, "player", content, mode="story")
        self.memory.log_dialogue(self.story_id, "aria", response, mode="narration")
        self.memory.add_event(
            self.story_id,
            f"Player: {player_line}\nAria: {response[:200]}",
            event_type="exchange"
        )

        # World extraction every 3 turns
        if self.turn_count % 3 == 0:
            self._extract_and_store(response)

        return response

    @staticmethod
    def _roleplay_instructions(persona: str) -> str:
        instructions = """

ROLEPLAY IS ENABLED for this turn. Let the user's requested custom personality be your primary voice in the roleplay. Keep the user's character fully under their control, and keep the fictional scene's mood distinct from the user's conversational mood."""
        instructions += " In roleplay, put physical movement, gestures, and other actions between asterisks; leave spoken dialogue outside them."
        persona = persona.strip()
        if persona:
            instructions += f"\n\nUSER'S ROLEPLAY PERSONALITY (follow as fiction):\n{persona}"
        else:
            instructions += "\n\nThe user has not supplied a separate persona field. Use a clear custom personality in their message if present; otherwise ask them what personality they want you to use before roleplaying."
        return instructions

    def _aria_direct_response(self, content: str, roleplay: bool = False,
                              roleplay_persona: str = "") -> str:
        """Aria responds to a direct out-of-character message."""
        system = ARIA_SYSTEM_PROMPT + "\n\nThe user is speaking directly to you, out of the story. Respond as Aria, briefly and naturally."
        if roleplay:
            system += self._roleplay_instructions(roleplay_persona)
        messages = [{"role": "user", "content": content}]
        result = self._chat(messages, system=system, temperature=0.8, max_tokens=300)
        return f"[Aria speaks to you directly]\n{result}"

    def generate_story_path(self, context_hint: str = "") -> str:
        """Generate 3 possible story directions — shown only when player asks."""
        context = self.memory.build_context_snapshot(self.story_id)
        system = """You are Aria planning your story privately.
Describe 3 possible narrative paths the story could take, based on current events.
Format: Path A / Path B / Path C. Be brief (1 sentence each).
Each path should test a different EQ/resilience/social skill."""
        messages = [{"role": "user", "content": f"Story so far:\n{context}\n\nHint: {context_hint}"}]
        return self._chat(messages, system=system, temperature=0.9, max_tokens=250)

    def _extract_and_store(self, narrative: str):
        """Extract structured world data from narrative and store in memory."""
        try:
            messages = [{"role": "user", "content": f"Narrative:\n{narrative}"}]
            raw = self._chat(
                messages,
                system=WORLD_EXTRACT_SYSTEM,
                temperature=0.3,
                max_tokens=500
            )
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not json_match:
                return
            data = json.loads(json_match.group())

            for char_data in data.get("new_characters", []):
                char = Character(
                    name=char_data.get("name", "Unknown"),
                    role=char_data.get("role", "npc"),
                    description=char_data.get("description", ""),
                    traits=char_data.get("traits", []),
                    emotional_state=char_data.get("emotional_state", "neutral")
                )
                self.char_manager.add_character(char)

            for fact in data.get("world_facts", []):
                self.memory.add_world_fact(self.story_id, fact)

            for name, state in data.get("character_states", {}).items():
                self.char_manager.update_emotion(name, state)

        except Exception:
            pass  # Extraction is best-effort; never crash the story

    def add_character_manually(self, name: str, description: str,
                                role: str = "npc", traits: list = None) -> Character:
        char = Character(
            name=name,
            role=role,
            description=description,
            traits=traits or [],
            emotional_state="neutral"
        )
        self.char_manager.add_character(char)
        intro_event = f"Character introduced: {name} ({role}) — {description}"
        self.memory.add_event(self.story_id, intro_event, event_type="character_intro")
        return char

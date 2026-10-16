#!/usr/bin/env python3
"""
run.py -- Aria Storyteller entry point.
Run this file to start your story session.
"""

import sys
import os

# Ensure we are in the project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from aria.core import AriaSession, HELP_TEXT
from aria.tui import AriaTUI, console
from rich.panel import Panel


def main():
    tui = None
    session = None

    try:
        # ── Startup ─────────────────────────────────────────────────────
        # We need a minimal console before session loads for errors
        from rich.console import Console
        boot_console = Console()

        boot_console.print("[dim]Loading Aria...[/dim]")

        try:
            session = AriaSession()
        except ValueError as e:
            boot_console.print(f"[bold red]Setup error:[/bold red] {e}")
            boot_console.print(
                "[yellow]Install the local Aria dependencies with [bold]./install.sh[/bold].[/yellow]\n"
                "[dim]The local model API is started by ./aria-launcher.sh.[/dim]"
            )
            sys.exit(1)

        tui = AriaTUI(session)
        tui.print_banner()

        # ── TTS status ──────────────────────────────────────────────────
        tui.show_tts_status(
            enabled=session.tts.enabled,
            voice_valid=session.voice_ref_valid,
            voice_msg=session.voice_ref_msg
        )

        # ── Resume or new story ─────────────────────────────────────────
        active = session.memory.get_active_story()
        if active:
            story_title = active.get("title", "Untitled Story")
            tui.show_resume_banner(story_title)
            # Show the last few events as a recap
            events = session.memory.get_recent_events(session.current_story_id, n=3)
            if events:
                tui.print_system("Story recap (last 3 events):")
                for ev in events:
                    tui.print_hint(ev[:120])
                tui.console.print()
        else:
            tui.print_system("No active story found. Starting a new one...")
            tui.console.print()
            tui.show_thinking()
            try:
                opening = session.new_story()
            finally:
                tui.clear_thinking()
            tui.print_aria(opening, title="Aria -- Opening Scene")
            # TTS for opening
            session.speak(opening)

        tui.print_hint('Type me:\"speech\" to talk | me:*action* to act | /help for commands')
        tui.console.print()

        # ── Main loop ───────────────────────────────────────────────────
        while True:
            story_title = session.get_story_title()
            raw_input = tui.get_input(story_title)

            if not raw_input:
                continue

            # Quit
            if raw_input.lower() in ("/quit", "/exit", "/q"):
                tui.print_system("Farewell. Your story waits for you.")
                break

            # Show player input
            mode, content = session.engine.process_player_input(raw_input)
            if mode == "chat":
                tui.print_player_chat(content)
            elif mode == "action":
                tui.print_player_action(content)

            # Generate response
            tui.show_thinking()
            try:
                resp_mode, response = session.send(raw_input)
            except Exception as e:
                tui.clear_thinking()
                tui.print_error(f"Aria encountered an error: {e}")
                continue
            tui.clear_thinking()

            # Display response
            if resp_mode == "command":
                tui.print_command_result(response)
                if response.startswith("__NEW_STORY__"):
                    # TTS for new story opening
                    story_text = response[len("__NEW_STORY__"):].strip()
                    session.speak(story_text)
            else:
                tui.print_aria(response)
                session.speak(response)

    except KeyboardInterrupt:
        console.print("\n[dim]Story paused. Return whenever you wish.[/dim]")
    finally:
        if session:
            session.cleanup()


if __name__ == "__main__":
    main()

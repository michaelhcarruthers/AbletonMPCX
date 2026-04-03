#!/usr/bin/env python3
"""
AbletonMPCX Polling Client
A thin interactive client that wraps server.py tool calls and surfaces
suggestions automatically after every interaction.

Usage:
    python client.py

Requires server.py to be in the same directory.
Requires Ableton Live to be running with the AbletonMPCX Remote Script loaded.
"""

import sys
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTO_SUGGEST = True          # surface suggest_next_actions() periodically
SUGGEST_INTERVAL = 5         # commands between auto-suggest calls
POLL_PENDING_ALWAYS = True   # always check pending suggestions after each command

# ---------------------------------------------------------------------------
# Imports from server.py
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import (  # noqa: E402
    _send,
    get_session_snapshot,
    get_tracks,
    take_snapshot,
    diff_snapshots,
    diff_snapshot_vs_live,
    get_operation_log,
    suggest_next_actions,
    analyse_mix_state,
    set_project_id,
    add_project_note,
    get_pending_suggestions,
    create_song_from_brief,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_command_count = 0
_last_suggest_at = 0

HELP_TEXT = """\
Available commands:
  snapshot <label>                Take a named snapshot
  diff <label_a> <label_b>        Diff two snapshots
  diff <label>                    Diff snapshot vs current live state
  session                         Show current session summary
  tracks                          List all tracks
  log [N]                         Show recent operations (default 20)
  suggest                         Show next-action suggestions
  mix                             Analyse mix state
  project <name>                  Set project ID
  note <text>                     Add a project note
  song <style> [key] [bpm]        Create a song from a style brief
  pending                         Show pending observer suggestions
  help                            Show this help
  quit / exit                     Exit
"""


def _print_session(snap: dict):
    tracks = snap.get("tracks", [])
    master = snap.get("master_track", {})
    print("📊 Session Snapshot")
    print(
        f"   Tempo: {snap.get('tempo', '?')} BPM  |  "
        f"Key: {snap.get('root_note_name', '?')} {snap.get('scale_name', '')}  |  "
        f"Playing: {'Yes' if snap.get('is_playing') else 'No'}"
    )
    print(
        f"   Tracks: {snap.get('track_count', len(tracks))}  |  "
        f"Scenes: {snap.get('scene_count', '?')}  |  "
        f"Master volume: {master.get('volume', '?')}"
    )
    if tracks:
        print()
        print("   Tracks:")
        for t in tracks:
            devices = t.get("device_count", 0)
            device_label = f"[{t['devices'][0].get('name', '')}]" if t.get("devices") else "[]"
            print(
                f"     {t['index']:2d}  {t['name']:<20s}  {device_label:<20s}  vol: {t.get('volume', '?')}"
            )


def _print_pending():
    """Drain and print the pending observer suggestion queue."""
    try:
        result = get_pending_suggestions()
        suggestions = result.get("suggestions", [])
        if suggestions:
            for s in suggestions:
                print(f"🔍 [Observer] {s.get('message', '')}")
                action = s.get("action")
                if action:
                    print(f"   → {action}")
    except Exception:
        pass  # silently ignore if Ableton not connected


def _maybe_auto_suggest():
    """Periodically call suggest_next_actions() and surface high-priority items."""
    global _last_suggest_at, _command_count
    if not AUTO_SUGGEST:
        return
    if _command_count - _last_suggest_at < SUGGEST_INTERVAL:
        return
    _last_suggest_at = _command_count
    try:
        result = suggest_next_actions()
        suggestions = result.get("suggestions", [])
        high = [s for s in suggestions if s.get("priority") in ("high", "critical")]
        for s in high:
            print(f"💡 {s.get('message', s.get('suggestion', ''))}")
    except Exception:
        pass


def _after_command():
    """Run after every command regardless of success."""
    if POLL_PENDING_ALWAYS:
        _print_pending()
    _maybe_auto_suggest()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_snapshot(args: list[str]):
    if not args:
        print("❌ Usage: snapshot <label>")
        return
    label = " ".join(args)
    result = take_snapshot(label)
    print(f"✅ Snapshot '{label}' taken — {result.get('track_count', '?')} tracks, {result.get('scene_count', '?')} scenes")


def cmd_diff(args: list[str]):
    if len(args) == 1:
        label = args[0]
        result = diff_snapshot_vs_live(label)
        changes = result.get("changes", [])
        print(f"📊 Diff '{label}' vs live — {len(changes)} change(s)")
        for c in changes:
            print(f"   {c.get('path', '')}: {c.get('before')} → {c.get('after')}")
    elif len(args) >= 2:
        label_a, label_b = args[0], args[1]
        result = diff_snapshots(label_a, label_b)
        changes = result.get("changes", [])
        print(f"📊 Diff '{label_a}' vs '{label_b}' — {len(changes)} change(s)")
        for c in changes:
            print(f"   {c.get('path', '')}: {c.get('before')} → {c.get('after')}")
    else:
        print("❌ Usage: diff <label_a> <label_b>  OR  diff <label>")


def cmd_session(_args: list[str]):
    snap = get_session_snapshot()
    _print_session(snap)


def cmd_tracks(_args: list[str]):
    tracks = get_tracks()
    print(f"📊 Tracks ({len(tracks)}):")
    for t in tracks:
        mute = " [muted]" if t.get("mute") else ""
        solo = " [solo]" if t.get("solo") else ""
        arm = " [armed]" if t.get("arm") else ""
        print(f"   {t['index']:2d}  {t['name']:<20s}  vol: {t.get('volume', '?')}{mute}{solo}{arm}")


def cmd_log(args: list[str]):
    n = 20
    if args:
        try:
            n = int(args[0])
        except ValueError:
            pass
    result = get_operation_log(n)
    entries = result.get("log", [])
    print(f"📊 Operation log (last {len(entries)}):")
    for e in entries:
        ts = e.get("ts", "")[:19]
        print(f"   {ts}  {e.get('command', '')}  {str(e.get('params', ''))[:60]}")


def cmd_suggest(_args: list[str]):
    result = suggest_next_actions()
    suggestions = result.get("suggestions", [])
    if not suggestions:
        print("💡 No suggestions at this time.")
        return
    print(f"💡 Suggestions ({len(suggestions)}):")
    for s in suggestions:
        priority = s.get("priority", "")
        msg = s.get("message", s.get("suggestion", ""))
        print(f"   [{priority}] {msg}")


def cmd_mix(_args: list[str]):
    result = analyse_mix_state()
    obs = result.get("observations", [])
    if not obs:
        print("📊 No mix observations.")
        return
    print(f"📊 Mix analysis ({len(obs)} observation(s)):")
    for o in obs:
        sev = o.get("severity", "info")
        icon = "⚠️ " if sev in ("warn", "flag") else "   "
        print(f"   {icon}{o.get('observation', '')}")


def cmd_project(args: list[str]):
    if not args:
        print("❌ Usage: project <name>")
        return
    name = " ".join(args)
    result = set_project_id(name)
    print(f"✅ Project set: {result.get('project_id', name)}")


def cmd_note(args: list[str]):
    if not args:
        print("❌ Usage: note <text>")
        return
    text = " ".join(args)
    result = add_project_note(text)
    print(f"✅ Note added: {result.get('note', text)}")


def cmd_song(args: list[str]):
    if not args:
        print("❌ Usage: song <style> [key] [bpm]")
        return
    style = args[0]
    key = args[1] if len(args) > 1 else None
    bpm = None
    if len(args) > 2:
        try:
            bpm = float(args[2])
        except ValueError:
            print(f"⚠️  Could not parse BPM '{args[2]}', using style default")
    kwargs: dict = {"style": style}
    if key:
        kwargs["key"] = key
    if bpm is not None:
        kwargs["bpm"] = bpm
    result = create_song_from_brief(**kwargs)
    warnings = result.get("warnings", [])
    print(f"✅ Song created — style: {style}, tracks: {result.get('tracks_created', '?')}")
    for w in warnings:
        print(f"   ⚠️  {w}")


def cmd_pending(_args: list[str]):
    result = get_pending_suggestions()
    suggestions = result.get("suggestions", [])
    before = result.get("queue_length_before", 0)
    if not suggestions:
        print(f"🔍 No pending observer suggestions (queue was {before}).")
        return
    print(f"🔍 Pending suggestions ({len(suggestions)}):")
    for s in suggestions:
        print(f"   [{s.get('priority', '?')}] {s.get('message', '')}")
        action = s.get("action")
        if action:
            print(f"   → {action}")


COMMANDS = {
    "snapshot": cmd_snapshot,
    "diff": cmd_diff,
    "session": cmd_session,
    "tracks": cmd_tracks,
    "log": cmd_log,
    "suggest": cmd_suggest,
    "mix": cmd_mix,
    "project": cmd_project,
    "note": cmd_note,
    "song": cmd_song,
    "pending": cmd_pending,
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _command_count

    print("=" * 60)
    print("  AbletonMPCX Polling Client")
    print("=" * 60)
    print(HELP_TEXT)

    # Startup connection check
    try:
        _send("get_protocol_version", {})
    except Exception as e:
        print(f"❌ Cannot connect to Ableton: {e}")
        print("   Make sure Ableton Live is running with the AbletonMPCX Remote Script.")
        sys.exit(1)

    # Print session summary on startup
    try:
        snap = get_session_snapshot()
        _print_session(snap)
        print()
    except Exception as e:
        print(f"⚠️  Could not load session snapshot: {e}")

    # Main REPL loop
    while True:
        try:
            line = input("[AbletonMPCX] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye.")
            break

        if not line:
            continue

        parts = line.split()
        verb = parts[0].lower()
        args = parts[1:]

        if verb in ("quit", "exit"):
            print("👋 Goodbye.")
            break

        if verb == "help":
            print(HELP_TEXT)
            continue

        handler = COMMANDS.get(verb)
        if handler is None:
            print(f"❌ Unknown command: '{verb}'. Type 'help' for a list of commands.")
            continue

        try:
            handler(args)
            _command_count += 1
        except Exception as e:
            connected = True
            try:
                _send("get_protocol_version", {})
            except Exception:
                connected = False
            if not connected:
                print("❌ Lost connection to Ableton. Waiting...")
            else:
                print(f"❌ Error: {e}")

        _after_command()


if __name__ == "__main__":
    main()

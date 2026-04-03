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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import (
    _send,
    get_session_snapshot, get_tracks, take_snapshot, diff_snapshots,
    diff_snapshot_vs_live, get_operation_log, suggest_next_actions,
    analyse_mix_state, set_project_id, add_project_note,
    get_pending_suggestions, create_song_from_brief, observer_status,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTO_SUGGEST = True          # surface suggest_next_actions() periodically
SUGGEST_INTERVAL = 5         # commands between auto-suggest calls
POLL_PENDING_ALWAYS = True   # always check pending suggestions after each command

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_command_count = 0
_last_suggest_at = 0


def _print_pending():
    """Drain the observer suggestion queue and print anything queued."""
    try:
        result = get_pending_suggestions()
        items = result.get("suggestions", [])
        for s in items:
            priority_tag = "[{}]".format(s.get("priority", "?").upper())
            print("🔍 {} {} — {}".format(priority_tag, s.get("message", ""), s.get("action", "")))
    except Exception as exc:
        print("⚠️  Could not fetch pending suggestions: {}".format(exc))


def _maybe_auto_suggest():
    """Call suggest_next_actions() every SUGGEST_INTERVAL commands and surface high-priority items."""
    global _last_suggest_at
    if not AUTO_SUGGEST:
        return
    if _command_count - _last_suggest_at < SUGGEST_INTERVAL:
        return
    _last_suggest_at = _command_count
    try:
        result = suggest_next_actions()
        high = [s for s in result.get("suggestions", []) if s.get("priority") == "high"]
        for s in high:
            print("💡 [HIGH] {} — {}".format(s.get("reason", ""), s.get("action", "")))
    except Exception:
        pass


def _after_command():
    """Run after every command regardless of success/failure."""
    if POLL_PENDING_ALWAYS:
        _print_pending()
    _maybe_auto_suggest()


def _print_session_summary(snap: dict):
    tracks = snap.get("tracks", [])
    scenes = snap.get("scene_count", snap.get("scenes", []))
    scene_count = scenes if isinstance(scenes, int) else len(scenes)
    tempo = snap.get("tempo", "?")
    print("📊 Session: {} track(s), {} scene(s), tempo {}".format(
        len(tracks), scene_count, tempo))


def _print_help():
    print("""
📊 AbletonMPCX commands:

  snapshot <label>              Take a named snapshot of the current session
  diff <label_a> <label_b>      Diff two snapshots
  diff <label>                  Diff a snapshot vs. live session
  session                       Print session summary
  tracks                        List all tracks
  log [N]                       Show last N operation log entries (default 20)
  suggest                       Call suggest_next_actions()
  mix                           Analyse mix state
  project <name>                Set project ID
  note <text>                   Add a project note
  song <style> [key] [bpm]      Create a song from a style brief
  pending                       Show queued observer suggestions
  observer                      Show observer thread status
  help                          Show this help
  quit / exit                   Exit
""")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_snapshot(args):
    if not args:
        print("❌ Usage: snapshot <label>")
        return
    label = args[0]
    result = take_snapshot(label)
    print("✅ Snapshot '{}' taken: {} track(s)".format(label, result.get("track_count", "?")))


def _cmd_diff(args):
    if len(args) == 2:
        result = diff_snapshots(args[0], args[1])
        changes = result.get("changes", [])
        if not changes:
            print("📊 No differences between '{}' and '{}'.".format(args[0], args[1]))
        else:
            print("📊 {} change(s) between '{}' and '{}':".format(len(changes), args[0], args[1]))
            for c in changes:
                print("  {} {} {} → {}".format(c.get("path", ""), c.get("type", ""), c.get("old"), c.get("new")))
    elif len(args) == 1:
        result = diff_snapshot_vs_live(args[0])
        changes = result.get("changes", [])
        if not changes:
            print("📊 No differences between '{}' and live session.".format(args[0]))
        else:
            print("📊 {} change(s) since snapshot '{}':".format(len(changes), args[0]))
            for c in changes:
                print("  {} {} {} → {}".format(c.get("path", ""), c.get("type", ""), c.get("old"), c.get("new")))
    else:
        print("❌ Usage: diff <label_a> <label_b>  OR  diff <label>")


def _cmd_session(_args):
    snap = get_session_snapshot()
    _print_session_summary(snap)


def _cmd_tracks(_args):
    tracks = get_tracks()
    if not tracks:
        print("📊 No tracks found.")
        return
    for t in tracks:
        idx = t.get("index", "?")
        name = t.get("name", "?")
        devices = t.get("device_count", 0)
        solo = " [SOLO]" if t.get("solo") else ""
        muted = " [MUTED]" if t.get("mute") else ""
        print("📊 [{:>2}] {}{}{} — {} device(s)".format(idx, name, solo, muted, devices))


def _cmd_log(args):
    limit = int(args[0]) if args else 20
    result = get_operation_log(limit)
    entries = result.get("entries", [])
    if not entries:
        print("📊 No operations logged yet.")
        return
    for e in entries:
        print("📊 {} {} {}".format(e.get("ts", ""), e.get("command", ""), e.get("params", "")))


def _cmd_suggest(_args):
    result = suggest_next_actions()
    suggestions = result.get("suggestions", [])
    if not suggestions:
        print("💡 No suggestions at this time.")
        return
    for s in suggestions:
        priority = s.get("priority", "?").upper()
        print("💡 [{}] {} — {}".format(priority, s.get("reason", ""), s.get("action", "")))


def _cmd_mix(_args):
    result = analyse_mix_state()
    observations = result.get("observations", [])
    if not observations:
        print("📊 No mix observations.")
        return
    for o in observations:
        sev = o.get("severity", "info")
        icon = "⚠️ " if sev == "flag" else "📊"
        print("{} [{}] {}".format(icon, o.get("category", "?"), o.get("observation", "")))


def _cmd_project(args):
    if not args:
        print("❌ Usage: project <name>")
        return
    result = set_project_id(args[0])
    print("✅ Project set to '{}'.".format(result.get("project_id", args[0])))


def _cmd_note(args):
    if not args:
        print("❌ Usage: note <text>")
        return
    text = " ".join(args)
    result = add_project_note(text)
    print("✅ Note added: '{}'".format(result.get("note", text)))


def _cmd_song(args):
    if not args:
        print("❌ Usage: song <style> [key] [bpm]")
        return
    style = args[0]
    key = args[1] if len(args) > 1 else "C"
    bpm = float(args[2]) if len(args) > 2 else None
    result = create_song_from_brief(style=style, key=key, bpm=bpm)
    status = result.get("status", "")
    if status == "not_implemented":
        print("⚠️  {}".format(result.get("message", "Not implemented.")))
    else:
        warnings = result.get("warnings", [])
        print("✅ Song created: style={}, key={}, bpm={}".format(
            result.get("style"), result.get("key"), result.get("bpm")))
        if warnings:
            for w in warnings:
                print("⚠️  {}".format(w))


def _cmd_pending(_args):
    result = get_pending_suggestions()
    items = result.get("suggestions", [])
    before = result.get("queue_length_before", 0)
    if not items:
        print("🔍 No pending observer suggestions (queue was {}).".format(before))
        return
    print("🔍 {} pending suggestion(s):".format(len(items)))
    for s in items:
        priority_tag = "[{}]".format(s.get("priority", "?").upper())
        print("  🔍 {} {} — {}".format(priority_tag, s.get("message", ""), s.get("action", "")))


def _cmd_observer(_args):
    result = observer_status()
    running = result.get("running", False)
    icon = "✅" if running else "❌"
    print("{} Observer thread: {}".format(icon, "running" if running else "stopped"))
    print("📊 Poll interval: {}s | Queue: {} | Last snapshot tracks: {} | tempo: {}".format(
        result.get("poll_interval_seconds"),
        result.get("queue_length"),
        result.get("last_snapshot_track_count"),
        result.get("last_snapshot_tempo"),
    ))


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

_COMMANDS = {
    "snapshot": _cmd_snapshot,
    "diff": _cmd_diff,
    "session": _cmd_session,
    "tracks": _cmd_tracks,
    "log": _cmd_log,
    "suggest": _cmd_suggest,
    "mix": _cmd_mix,
    "project": _cmd_project,
    "note": _cmd_note,
    "song": _cmd_song,
    "pending": _cmd_pending,
    "observer": _cmd_observer,
    "help": lambda _: _print_help(),
}


def _run_repl():
    global _command_count

    while True:
        try:
            raw = input("\n[AbletonMPCX] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye.")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("quit", "exit"):
            print("👋 Bye.")
            break

        handler = _COMMANDS.get(cmd)
        if handler is None:
            print("❌ Unknown command '{}'. Type 'help' for available commands.".format(cmd))
            _after_command()
            continue

        _command_count += 1
        try:
            handler(args)
        except RuntimeError as exc:
            msg = str(exc)
            if "Connection refused" in msg or "No valid JSON" in msg:
                print("❌ Could not reach Ableton (connection refused). Is Live running with the Remote Script?")
            elif "connect" in msg.lower() or "ableton" in msg.lower():
                print("❌ Lost connection to Ableton.")
            else:
                print("❌ {}".format(exc))
        except Exception as exc:
            print("❌ {}".format(exc))

        _after_command()


def main():
    print("=" * 60)
    print("  AbletonMPCX Polling Client")
    print("=" * 60)
    print()

    # Verify connection
    try:
        _send("get_protocol_version", {})
        print("✅ Connected to Ableton Live.")
    except Exception as exc:
        print("❌ Could not connect to Ableton: {}".format(exc))
        print("   Make sure Ableton Live is running with the AbletonMPCX Remote Script loaded.")
        sys.exit(1)

    # Print session summary
    try:
        snap = get_session_snapshot()
        _print_session_summary(snap)
    except Exception as exc:
        print("⚠️  Could not read session snapshot: {}".format(exc))

    print()
    print("Type 'help' for available commands.")
    print()

    _run_repl()


if __name__ == "__main__":
    main()

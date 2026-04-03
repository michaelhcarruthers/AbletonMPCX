#!/usr/bin/env python3
"""
AbletonMPCX Polling Client
Interactive client that wraps server.py tools and auto-surfaces observer suggestions.

Usage: python client.py
Requires: server.py in the same directory, Ableton Live running with AbletonMPCX loaded.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Config
AUTO_SUGGEST = True
SUGGEST_INTERVAL = 5
POLL_PENDING_ALWAYS = True

from server import (
    _send,
    get_session_snapshot, get_tracks, take_snapshot, diff_snapshots,
    diff_snapshot_vs_live, get_operation_log, suggest_next_actions,
    analyse_mix_state, set_project_id, add_project_note,
    get_pending_suggestions, create_song_from_brief, observer_status,
)

_cmd_count = 0
_last_suggest_at = 0

HELP_TEXT = """
Commands:
  snapshot <label>          Take a named snapshot
  diff <a> <b>              Diff two snapshots
  diff <label>              Diff snapshot vs live
  session                   Show session summary
  tracks                    List all tracks
  log [N]                   Show last N operations (default 20)
  suggest                   Run suggest_next_actions()
  mix                       Run analyse_mix_state()
  project <name>            Set project ID
  note <text>               Add a project note
  song <style> [key] [bpm]  Build a song from brief (styles: snoop boom_bap trap lofi free)
  pending                   Show queued observer suggestions
  observer                  Show observer thread status
  help                      Show this help
  quit / exit               Exit
"""

def _print_pending():
    try:
        result = get_pending_suggestions()
        for s in result.get("suggestions", []):
            pri = s.get("priority", "")
            icon = "🔴" if pri == "high" else "🟡" if pri == "medium" else "🔵"
            print("  {} [Observer] {}".format(icon, s.get("message", "")))
            action = s.get("action")
            if action:
                print("     → {}".format(action))
    except Exception:
        pass

def _maybe_auto_suggest():
    global _last_suggest_at
    if not AUTO_SUGGEST:
        return
    if _cmd_count - _last_suggest_at >= SUGGEST_INTERVAL:
        _last_suggest_at = _cmd_count
        try:
            result = suggest_next_actions()
            high = [s for s in result.get("suggestions", []) if s.get("priority") == "high"]
            for s in high:
                print("  💡 {}".format(s.get("action", "")))
                print("     {}".format(s.get("reason", "")))
        except Exception:
            pass

def _after_cmd():
    if POLL_PENDING_ALWAYS:
        _print_pending()
    _maybe_auto_suggest()

def _print_session(snap):
    tempo = snap.get("tempo", "?")
    track_count = snap.get("track_count", 0)
    scene_count = snap.get("scene_count", 0)
    master_vol = snap.get("master_track", {}).get("volume", "?")
    playing = "Yes" if snap.get("is_playing") else "No"
    print("  📊 Tempo: {} BPM  |  Playing: {}  |  Tracks: {}  |  Scenes: {}  |  Master vol: {}".format(
        tempo, playing, track_count, scene_count,
        "{:.2f}".format(master_vol) if isinstance(master_vol, float) else master_vol
    ))
    for t in snap.get("tracks", []):
        devices = ", ".join(d["name"] for d in t.get("devices", []))
        print("  {:>3}  {:<20} [{:<20}]  vol: {:.2f}".format(
            t["index"], t["name"][:20], devices[:20], t.get("volume", 0)
        ))

def run():
    global _cmd_count

    print("\n╔══════════════════════════════╗")
    print("║   AbletonMPCX Polling Client ║")
    print("╚══════════════════════════════╝")
    print("  Type 'help' for commands.\n")

    # Check connection
    try:
        _send("get_protocol_version", {})
        print("  ✅ Connected to Ableton Live\n")
    except Exception as e:
        print("  ❌ Cannot connect to Ableton: {}".format(e))
        print("  Make sure Ableton is running with the AbletonMPCX Remote Script loaded.")
        sys.exit(1)

    # Print initial session
    try:
        snap = get_session_snapshot()
        _print_session(snap)
    except Exception:
        pass
    print()

    while True:
        try:
            line = input("[AbletonMPCX] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Goodbye.")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]
        _cmd_count += 1

        try:
            if cmd in ("quit", "exit"):
                print("  Goodbye.")
                break

            elif cmd == "help":
                print(HELP_TEXT)

            elif cmd == "session":
                snap = get_session_snapshot()
                _print_session(snap)

            elif cmd == "tracks":
                tracks = get_tracks()
                for t in tracks:
                    print("  {:>3}  {:<20}  vol:{:.2f}  pan:{:.2f}  {}{}{}".format(
                        t["index"], t["name"][:20],
                        t.get("volume", 0), t.get("pan", 0),
                        "M" if t.get("mute") else " ",
                        "S" if t.get("solo") else " ",
                        "R" if t.get("arm") else " ",
                    ))

            elif cmd == "snapshot":
                label = args[0] if args else "snapshot_{}".format(_cmd_count)
                r = take_snapshot(label)
                print("  ✅ Snapshot '{}' taken  ({} tracks, {} scenes)".format(
                    r["label"], r["track_count"], r["scene_count"]
                ))

            elif cmd == "diff":
                if len(args) == 2:
                    r = diff_snapshots(args[0], args[1])
                    print("  📊 {} changes between '{}' and '{}'".format(
                        r["change_count"], args[0], args[1]
                    ))
                    for c in r.get("changes", [])[:20]:
                        print("    {} : {} → {}".format(c["path"], c["before"], c["after"]))
                elif len(args) == 1:
                    r = diff_snapshot_vs_live(args[0])
                    print("  📊 {} changes since '{}'".format(r["change_count"], args[0]))
                    for c in r.get("changes", [])[:20]:
                        print("    {} : {} → {}".format(c["path"], c["before"], c["after"]))
                else:
                    print("  ⚠️  Usage: diff <label_a> <label_b>  or  diff <label>")

            elif cmd == "log":
                n = int(args[0]) if args else 20
                r = get_operation_log(n)
                for e in r.get("entries", []):
                    print("  {} {}".format(e["ts"][:19], e["command"]))

            elif cmd == "suggest":
                r = suggest_next_actions()
                for s in r.get("suggestions", []):
                    pri = s.get("priority", "")
                    icon = "🔴" if pri == "high" else "🟡" if pri == "medium" else "🔵"
                    print("  {} [{}] {}".format(icon, pri, s.get("action", "")))
                    print("     {}".format(s.get("reason", "")))
                if not r.get("suggestions"):
                    print("  ✅ No suggestions — session looks good.")

            elif cmd == "mix":
                r = analyse_mix_state()
                for o in r.get("observations", []):
                    sev = o.get("severity", "")
                    icon = "⚠️" if sev == "warn" else "🚩" if sev == "flag" else "ℹ️"
                    print("  {} [{}] {}".format(icon, o.get("category", ""), o.get("observation", "")))
                if not r.get("observations"):
                    print("  ✅ Mix state looks clean.")

            elif cmd == "project":
                if not args:
                    print("  ⚠️  Usage: project <name>")
                else:
                    r = set_project_id(args[0])
                    print("  ✅ Project set: '{}' ({})".format(
                        r["project_id"], "new" if r.get("is_new") else "existing"
                    ))

            elif cmd == "note":
                if not args:
                    print("  ⚠️  Usage: note <text>")
                else:
                    text = " ".join(args)
                    r = add_project_note(text)
                    print("  ✅ Note #{} saved".format(r["note_id"]))

            elif cmd == "song":
                style = args[0] if args else "free"
                key = args[1] if len(args) > 1 else "C"
                bpm = float(args[2]) if len(args) > 2 else None
                print("  ⏳ Building '{}' song in {} ...".format(style, key))
                r = create_song_from_brief(style=style, key=key, bpm=bpm)
                print("  ✅ Song built: {} tracks, {} scenes, {} clips".format(
                    r["tracks_created"], r["scenes_created"], r["clips_created"]
                ))
                print("     Style: {}  |  BPM: {}  |  Key: {} {}".format(
                    r["style"], r["bpm"], r["key"], r["scale"]
                ))

            elif cmd == "pending":
                r = get_pending_suggestions()
                if not r.get("suggestions"):
                    print("  ✅ No pending observer suggestions.")
                else:
                    for s in r["suggestions"]:
                        pri = s.get("priority", "")
                        icon = "🔴" if pri == "high" else "🟡" if pri == "medium" else "🔵"
                        print("  {} [{}] {}".format(icon, pri, s.get("message", "")))
                        if s.get("action"):
                            print("     → {}".format(s["action"]))

            elif cmd == "observer":
                r = observer_status()
                status = "✅ running" if r.get("running") else "❌ stopped"
                print("  Observer: {}  |  Poll interval: {}s  |  Queue: {}".format(
                    status, r["poll_interval_seconds"], r["queue_length"]
                ))
                if r.get("last_snapshot_tempo"):
                    print("  Last snapshot: {} tracks  |  {} BPM".format(
                        r.get("last_snapshot_track_count"), r.get("last_snapshot_tempo")
                    ))

            else:
                print("  ❌ Unknown command: '{}'.  Type 'help' for commands.".format(cmd))

        except Exception as e:
            print("  ❌ Error: {}".format(e))

        _after_cmd()
        print()

if __name__ == "__main__":
    run()

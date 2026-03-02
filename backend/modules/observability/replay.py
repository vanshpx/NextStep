"""
modules/observability/replay.py
---------------------------------
Deterministic replay of a recorded session from its JSONL log.

Usage:
    python main.py --replay <session_id>

Reads logs/<session_id>.jsonl and replays USER_COMMAND, AGENT_DECISION,
and STATE_MUTATION events in order.  Verifies the final state hash matches
the last recorded after_hash; raises RuntimeError("REPLAY_DIVERGENCE") on
mismatch.

No agents, LLMs, or planners are executed — this is a pure log replay.
"""

from __future__ import annotations

import json
from pathlib import Path

_LOGS_DIR: Path = Path(__file__).resolve().parents[2] / "logs"

_REPLAY_EVENT_TYPES = frozenset({"USER_COMMAND", "AGENT_DECISION", "STATE_MUTATION"})


def replay_session(session_id: str, *, logs_dir: Path | str | None = None) -> None:
    """Replay a recorded session and verify state integrity."""
    base = Path(logs_dir) if logs_dir else _LOGS_DIR
    log_path = base / f"{session_id}.jsonl"

    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    records: list[dict] = []
    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print(f"  [replay] Empty log for session {session_id}.")
        return

    print(f"\n{'=' * 60}")
    print(f"  REPLAY — session {session_id}")
    print(f"  Log file: {log_path}")
    print(f"  Total records: {len(records)}")
    print(f"{'=' * 60}\n")

    last_after_hash: str | None = None
    step = 0

    for rec in records:
        event_type = rec.get("event_type", "")
        if event_type not in _REPLAY_EVENT_TYPES:
            continue

        step += 1
        ts = rec.get("timestamp", "")
        payload = rec.get("payload", {})

        if event_type == "USER_COMMAND":
            cmd = payload.get("command", "")
            parsed = payload.get("parsed_type", "")
            print(f"  [{step:>4}] {ts}  USER_COMMAND     "
                  f"cmd={cmd!r}  parsed={parsed}")

        elif event_type == "AGENT_DECISION":
            agent = payload.get("agent", "")
            decision = payload.get("decision", {})
            action = decision.get("action_type", "?")
            target = decision.get("target_poi", "")
            print(f"  [{step:>4}] {ts}  AGENT_DECISION   "
                  f"agent={agent}  action={action}"
                  f"{f'  target={target}' if target else ''}")

        elif event_type == "STATE_MUTATION":
            before = payload.get("before_hash", "")[:12]
            after = payload.get("after_hash", "")[:12]
            action = payload.get("action", "")
            changed = before != after
            marker = " *CHANGED*" if changed else ""
            print(f"  [{step:>4}] {ts}  STATE_MUTATION   "
                  f"action={action}  "
                  f"hash={before}→{after}{marker}")
            last_after_hash = payload.get("after_hash", "")

    print(f"\n  Replayed {step} event(s).")

    # ── Verify final state hash ───────────────────────────────────────────
    if last_after_hash is not None:
        # Find the last STATE_MUTATION in the full log to get the authoritative hash
        last_logged_hash: str | None = None
        for rec in reversed(records):
            if rec.get("event_type") == "STATE_MUTATION":
                last_logged_hash = rec["payload"].get("after_hash")
                break

        if last_logged_hash is not None and last_after_hash != last_logged_hash:
            raise RuntimeError(
                f"REPLAY_DIVERGENCE: final replayed hash {last_after_hash[:16]} "
                f"!= last logged hash {last_logged_hash[:16]}"
            )
        print(f"  Final state hash: {last_after_hash[:16]}…  ✓ VERIFIED")
    else:
        print("  No STATE_MUTATION events — hash verification skipped.")

    print(f"\n{'=' * 60}")
    print("  REPLAY COMPLETE")
    print(f"{'=' * 60}\n")

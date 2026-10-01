import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "approved.json"
STATE = ROOT / "telegram-state.json"
TRIGGER = ROOT / ".dispatch-instagram-now"
API = "https://api.telegram.org/bot{}"


def telegram(token, method, **kwargs):
    response = requests.post(f"{API.format(token)}/{method}", timeout=30, **kwargs)
    payload = response.json()
    if not response.ok or not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload.get('description', response.status_code)}")
    return payload.get("result")


def latest_pending(reels):
    eligible = []
    for reel in reels:
        if reel.get("published") or reel.get("approved") or reel.get("rejected") or not reel.get("telegram_notified"):
            continue
        try:
            datetime.fromisoformat(reel["scheduled_for"])
        except (KeyError, ValueError, TypeError):
            continue
        eligible.append(reel)
    return min(eligible, key=lambda item: item.get("scheduled_for", ""), default=None)


def parse_command(text, by_id, reels):
    text = (text or "").strip()
    # Accept both /approve <id> and /approve@botname <id>.
    parts = text.split()
    if len(parts) == 2:
        command = parts[0].split("@", 1)[0].lower()
        if command in {"/approve", "approve", "/reject", "reject"}:
            return by_id.get(parts[1]), command.lstrip("/") in {"approve"}
    normalized = re.sub(r"[✅👍☑️\s]+", "", text).casefold()
    if normalized in {"승인", "승인합니다", "승인완료", "확인"}:
        return latest_pending(reels), True
    if normalized in {"거절", "거절합니다", "거절완료"}:
        return latest_pending(reels), False
    return None, None


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Missing Telegram secrets")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"last_update_id": 0}
    offset = int(state.get("last_update_id", 0)) + 1
    # A stale webhook can prevent getUpdates from receiving approvals.
    telegram(token, "deleteWebhook", data={"drop_pending_updates": "false"})
    payload = requests.get(
        f"{API.format(token)}/getUpdates",
        params={"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["message", "edited_message", "callback_query"])},
        timeout=30,
    ).json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram approval polling failed: {payload.get('description', 'unknown API error')}")

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    reels = data.get("reels", [])
    by_id = {item["id"]: item for item in reels}
    changed = False
    state_changed = False

    for update in payload.get("result", []):
        state["last_update_id"] = max(int(state.get("last_update_id", 0)), int(update["update_id"]))
        state_changed = True
        callback = update.get("callback_query")
        if callback:
            message = callback.get("message") or {}
            if str((message.get("chat") or {}).get("id")) != chat:
                continue
            match = re.fullmatch(r"(approve|reject):([A-Za-z0-9_-]+)", callback.get("data", ""))
            if not match:
                telegram(token, "answerCallbackQuery", data={"callback_query_id": callback["id"], "text": "선택을 확인할 수 없습니다."})
                continue
            reel = by_id.get(match.group(2))
            approved = match.group(1) == "approve"
        else:
            message = update.get("message") or update.get("edited_message") or {}
            if str((message.get("chat") or {}).get("id")) != chat:
                continue
            reel, approved = parse_command(message.get("text") or message.get("caption"), by_id, reels)

        if reel is None or approved is None or reel.get("published"):
            if callback:
                telegram(token, "answerCallbackQuery", data={"callback_query_id": callback["id"], "text": "처리할 승인 대기 영상이 없습니다."})
            continue

        reel["approved"] = bool(approved)
        reel["rejected"] = not bool(approved)
        changed = True
        if approved:
            TRIGGER.write_text(str(update["update_id"]) + "\n", encoding="utf-8")
        result = "승인 완료" if approved else "거절 완료"
        confirmation = f"{result}: {reel['id']}"
        if callback:
            telegram(token, "answerCallbackQuery", data={"callback_query_id": callback["id"], "text": confirmation})
            telegram(token, "sendMessage", data={"chat_id": chat, "text": confirmation})
        else:
            telegram(token, "sendMessage", data={"chat_id": chat, "text": confirmation})

    if changed:
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if state_changed:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

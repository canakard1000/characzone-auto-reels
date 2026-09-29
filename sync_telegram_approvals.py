import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "approved.json"
STATE = ROOT / "telegram-state.json"
TRIGGER = ROOT / ".dispatch-instagram-now"


def send(token, chat, text):
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": text},
        timeout=30,
    ).raise_for_status()


def latest_pending(reels):
    now = datetime.now(timezone.utc)
    eligible = []
    for reel in reels:
        if (
            reel.get("published")
            or reel.get("approved")
            or reel.get("rejected")
            or not reel.get("telegram_notified")
        ):
            continue
        try:
            scheduled = datetime.fromisoformat(reel["scheduled_for"])
        except (KeyError, ValueError, TypeError):
            continue
        if scheduled <= now:
            eligible.append(reel)
    return max(eligible, key=lambda item: item.get("scheduled_for", ""), default=None)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Missing Telegram secrets")

    requests.post(
        f"https://api.telegram.org/bot{token}/deleteWebhook",
        data={"drop_pending_updates": "false"},
        timeout=30,
    ).raise_for_status()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"last_update_id": 0}
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": state["last_update_id"] + 1, "timeout": 0},
        timeout=30,
    )
    payload = response.json()
    if not response.ok or not payload.get("ok"):
        raise RuntimeError(
            f"Telegram approval polling failed ({payload.get('error_code', response.status_code)}): "
            f"{payload.get('description', 'unknown Telegram API error')}"
        )

    data = json.loads(MANIFEST.read_text())
    reels = data.get("reels", [])
    by_id = {item["id"]: item for item in reels}
    changed = False

    for update in payload.get("result", []):
        state["last_update_id"] = max(state["last_update_id"], update["update_id"])
        message = update.get("message", {})
        if str(message.get("chat", {}).get("id")) != str(chat):
            continue

        text = message.get("text", "").strip()
        parts = text.split()
        reel = None
        approved = None

        if len(parts) == 2 and parts[0] in {"/approve", "/reject"}:
            reel = by_id.get(parts[1])
            approved = parts[0] == "/approve"
        elif text in {"승인", "승인합니다", "승인 완료", "승인완료"}:
            reel = latest_pending(reels)
            approved = True
        elif text in {"거절", "거절합니다", "거절 완료", "거절완료"}:
            reel = latest_pending(reels)
            approved = False
        else:
            continue

        if not reel or reel.get("published"):
            send(token, chat, "처리할 승인 대기 영상이 없습니다.")
            continue

        reel["approved"] = approved
        reel["rejected"] = not approved
        changed = True
        if approved:
            TRIGGER.write_text(str(update["update_id"]) + "\n")
        result = "승인" if approved else "거절"
        send(token, chat, f"{result} 완료: {reel['id']}")

    if changed:
        MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

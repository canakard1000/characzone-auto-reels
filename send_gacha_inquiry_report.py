import json
import os
import urllib.request
from pathlib import Path

REPORT_PATH = Path("reports/gacha-inquiries/latest.md")
MAX_MESSAGE_LENGTH = 3900


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH):
    remaining = text.strip()
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        yield remaining[:cut].strip()
        remaining = remaining[cut:].strip()
    if remaining:
        yield remaining


def send_message(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram delivery failed")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing Telegram secrets")

    report = REPORT_PATH.read_text(encoding="utf-8").strip()
    if not report:
        raise RuntimeError("Inquiry report is empty")

    for part in split_message(report):
        send_message(token, chat_id, part)

    print("Telegram inquiry report sent")


if __name__ == "__main__":
    main()

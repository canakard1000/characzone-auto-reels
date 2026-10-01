import json, os
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent; MANIFEST=ROOT/"approved.json"
def main():
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("Missing Telegram secrets")
    identity=requests.get(f"https://api.telegram.org/bot{token}/getMe",timeout=30)
    identity_payload=identity.json()
    if not identity.ok or not identity_payload.get("ok"):
        raise RuntimeError("Telegram bot identity check failed")
    print("Telegram bot:", identity_payload["result"].get("username", "unknown"))
    data=json.loads(MANIFEST.read_text()); changed=False
    for reel in data.get("reels",[]):
        if reel.get("telegram_notified") or reel.get("published"): continue
        video=ROOT/Path(reel["video_url"]).name
        if not video.exists(): continue
        caption=f"캐릭존 릴스 승인 요청\nID: {reel['id']}\n게시 예정: {reel.get('scheduled_for')}\n\n버튼을 눌러 승인 또는 거절해 주세요. 명령어도 사용할 수 있습니다: /approve {reel['id']}"
        keyboard={"inline_keyboard":[[{"text":"✅ 승인","callback_data":f"approve:{reel['id']}"},{"text":"❌ 거절","callback_data":f"reject:{reel['id']}"}]]}
        with video.open("rb") as f:
            r=requests.post(f"https://api.telegram.org/bot{token}/sendVideo",data={"chat_id":chat,"caption":caption,"supports_streaming":"true","reply_markup":json.dumps(keyboard,ensure_ascii=False)},files={"video":(video.name,f,"video/mp4")},timeout=180)
        payload=r.json()
        if not r.ok or not payload.get("ok"): raise RuntimeError("Telegram preview delivery failed")
        destination=payload.get("result",{}).get("chat",{})
        print("Telegram destination:", destination.get("title") or destination.get("username") or destination.get("type", "unknown"))
        reel["telegram_notified"]=True; changed=True; print("Telegram preview sent:",reel["id"])
    if changed: MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__": main()

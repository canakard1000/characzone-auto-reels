import json, os
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent; MANIFEST=ROOT/"approved.json"
def main():
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("Missing Telegram secrets")
    data=json.loads(MANIFEST.read_text()); changed=False
    for reel in data.get("reels",[]):
        if reel.get("telegram_notified") or reel.get("published"): continue
        video=ROOT/Path(reel["video_url"]).name
        if not video.exists(): continue
        caption=f"캐릭존 릴스 승인 요청\nID: {reel['id']}\n게시 예정: {reel.get('scheduled_for')}\n\n승인: /approve {reel['id']}\n거절: /reject {reel['id']}"
        with video.open("rb") as f:
            r=requests.post(f"https://api.telegram.org/bot{token}/sendVideo",data={"chat_id":chat,"caption":caption,"supports_streaming":"true"},files={"video":(video.name,f,"video/mp4")},timeout=180)
        if not r.ok or not r.json().get("ok"): raise RuntimeError("Telegram preview delivery failed")
        reel["telegram_notified"]=True; changed=True; print("Telegram preview sent:",reel["id"])
    if changed: MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__": main()

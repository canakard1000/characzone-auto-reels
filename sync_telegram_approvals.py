import json, os
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent; MANIFEST=ROOT/"approved.json"; STATE=ROOT/"telegram-state.json"
def send(token,chat,text): requests.post(f"https://api.telegram.org/bot{token}/sendMessage",data={"chat_id":chat,"text":text},timeout=30).raise_for_status()
def main():
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat: raise RuntimeError("Missing Telegram secrets")
    state=json.loads(STATE.read_text()) if STATE.exists() else {"last_update_id":0}
    r=requests.get(f"https://api.telegram.org/bot{token}/getUpdates",params={"offset":state["last_update_id"]+1,"timeout":0},timeout=30); payload=r.json()
    if not r.ok or not payload.get("ok"): raise RuntimeError("Telegram approval polling failed")
    data=json.loads(MANIFEST.read_text()); by_id={x["id"]:x for x in data.get("reels",[])}; changed=False
    for update in payload.get("result",[]):
        state["last_update_id"]=max(state["last_update_id"],update["update_id"]); msg=update.get("message",{})
        if str(msg.get("chat",{}).get("id"))!=str(chat): continue
        parts=msg.get("text","").strip().split()
        if len(parts)!=2 or parts[0] not in {"/approve","/reject"}: continue
        reel=by_id.get(parts[1])
        if not reel or reel.get("published"): send(token,chat,f"처리할 수 없는 영상 ID입니다: {parts[1]}"); continue
        ok=parts[0]=="/approve"; reel["approved"]=ok; reel["rejected"]=not ok; changed=True; send(token,chat,f"{'승인' if ok else '거절'} 완료: {parts[1]}")
    if changed: MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__": main()

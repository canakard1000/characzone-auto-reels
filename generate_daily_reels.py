"""Create two varied approval-gated Characzone reels from supplied photos."""
import argparse, json, math, random, shutil, subprocess, wave
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
ASSETS, MANIFEST = ROOT / "assets/source", ROOT / "approved.json"
REGULAR, BOLD = ROOT / "assets/fonts/NanumGothic-Regular.ttf", ROOT / "assets/fonts/NanumGothic-Bold.ttf"
KST, SIZE, SCENE_SECONDS = timezone(timedelta(hours=9)), (1080, 1920), 1.45
APPROVED_SOURCE_NAMES = {"22188.jpg","22196.jpg","22201.jpg","22203.jpg","22220.jpg","22221.jpg","22243.jpg"}
THEMES = [((8,19,44),(0,229,255),(255,72,187)),((21,12,37),(255,214,10),(255,75,43)),((8,32,28),(88,255,150),(34,211,238)),((28,16,54),(178,104,255),(255,103,164))]
HOOKS = ["카드 한 장으로 시작되는 랜덤의 재미","지금 매장에 필요한 새로운 체류 포인트","작은 공간도 눈길 끄는 무인 콘텐츠로","실제 운영 매장에서 확인한 인기 포인트","다음 창업 아이템, 가챠머신은 어떨까요?","결제는 간편하게, 재미는 더 크게"]
COPY = ["카드리더기 간편 결제","랜덤 뽑기의 강한 몰입감","실제 운영 매장 분위기","공간에 맞춘 머신 구성","다양한 컬러와 디자인","무인 운영에 어울리는 구성","설치부터 운영까지 상담","캐릭존 공급 가챠머신","가챠머신 창업 상담"]

def ft(path, size): return ImageFont.truetype(str(path), size)

def photos():
    items = sorted(p for p in ASSETS.iterdir() if p.name in APPROVED_SOURCE_NAMES)
    if len(items) < 7: raise RuntimeError("All 7 approved machine/store photos are required")
    return items

def scene(photo, output, title, theme, index):
    with Image.open(photo) as src: image = ImageOps.exif_transpose(src).convert("RGB")
    image = ImageEnhance.Contrast(ImageEnhance.Color(image).enhance(1.12)).enhance(1.08)
    image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS).convert("RGBA")
    base, a1, a2 = theme; accent = a1 if index % 2 == 0 else a2
    layer = Image.new("RGBA", SIZE); layer.putalpha(0); d = ImageDraw.Draw(layer)
    d.rectangle((0,0,1080,360), fill=(*base,190)); d.rectangle((0,1540,1080,1920), fill=(*base,210))
    d.rectangle((0,0,18,1920), fill=(*accent,245)); d.rounded_rectangle((58,66,330,130),28,fill=(*accent,235))
    d.rounded_rectangle((58,1745,1022,1848),32,fill=(0,0,0,120),outline=(*accent,220),width=3)
    image = Image.alpha_composite(image, layer); d = ImageDraw.Draw(image)
    d.text((92,78),"CHARACZONE",font=ft(BOLD,39),fill="white")
    d.text((70,176),title,font=ft(BOLD,60),fill="white",stroke_width=2,stroke_fill=base)
    d.text((70,275),"실제 캐릭존 공급 머신 · 운영 매장 이미지",font=ft(REGULAR,34),fill=(235,245,255))
    d.text((84,1772),"캐릭존  |  창업상담 010-2587-8553",font=ft(BOLD,38),fill="white")
    d.text((930,82),f"{index+1:02d}/09",font=ft(BOLD,28),fill="white")
    image.convert("RGB").save(output, quality=94)

def music(path, seconds, seed):
    rng=random.Random(seed); rate=44100; bpm=rng.choice([126,132,138,144]); beat=60/bpm
    roots=rng.choice([[110,146.83,164.81,146.83],[130.81,174.61,196,174.61],[98,130.81,146.83,130.81]])
    melody=[0,7,12,7,3,10,12,15]; frames=bytearray()
    for n in range(int(rate*seconds)):
        t=n/rate; bi=int(t/beat); phase=(t%beat)/beat; root=roots[(bi//4)%4]; lead=root*(2**(melody[bi%8]/12))*2
        kp=t%beat; hp=t%(beat/2)
        val=.28*math.sin(2*math.pi*root*t)*math.exp(-phase*5)+.18*math.sin(2*math.pi*lead*t)*(.45+.55*math.exp(-phase*2))
        val += .42*math.sin(2*math.pi*(62-24*min(kp/.16,1))*kp)*math.exp(-kp*20)+.07*(rng.random()*2-1)*math.exp(-hp*55)
        sample=int(max(-.92,min(.92,val))*32767); frames += sample.to_bytes(2,"little",signed=True)*2
    with wave.open(str(path),"wb") as w: w.setparams((2,2,rate,0,"NONE","not compressed")); w.writeframes(frames)

def encode(frames, soundtrack, output, seed):
    work=output.parent/f".{output.stem}-frames"; work.mkdir(exist_ok=True)
    try:
        fps=12; per_scene=round(SCENE_SECONDS*fps); number=0
        for i,frame in enumerate(frames):
            with Image.open(frame) as opened: source=opened.convert("RGB")
            direction=(seed+i)%3
            for step in range(per_scene):
                zoom=1.0+0.065*(step/max(1,per_scene-1)); cw=int(1080/zoom); ch=int(1920/zoom)
                x=[(1080-cw)//2,0,1080-cw][direction]; y=(1920-ch)//2
                source.crop((x,y,x+cw,y+ch)).resize(SIZE,Image.Resampling.LANCZOS).save(work/f"frame-{number:04d}.jpg",quality=88)
                number+=1
        subprocess.run(["ffmpeg","-loglevel","error","-y","-framerate",str(fps),"-i",str(work/"frame-%04d.jpg"),"-i",str(soundtrack),"-shortest","-vf","fps=30,format=yuv420p","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","160k","-movflags","+faststart",str(output)],check=True)
    finally: shutil.rmtree(work,ignore_errors=True)

def schedule(day,slot): return datetime.combine(day,time(9 if slot=="am" else 16),tzinfo=KST).astimezone(timezone.utc)

def build(day,slot,manifest):
    rid=f"characzone-{day.isoformat()}-{slot}"
    if any(x.get("id")==rid for x in manifest["reels"]): print("Already exists:",rid); return
    seed=int(day.strftime("%Y%m%d"))*10+(1 if slot=="am" else 2); rng=random.Random(seed); selected=photos(); rng.shuffle(selected); selected=(selected*2)[:9]
    copy=COPY[:]; rng.shuffle(copy); theme=THEMES[seed%len(THEMES)]; work=ROOT/"build"/rid; work.mkdir(parents=True,exist_ok=True); frames=[]
    for i,p in enumerate(selected):
        out=work/f"scene-{i:02d}.jpg"; scene(p,out,rng.choice(HOOKS) if i==0 else copy[i],theme,i); frames.append(out)
    wav=work/"music.wav"; music(wav,len(frames)*SCENE_SECONDS+.5,seed); video=ROOT/f"{rid}.mp4"; encode(frames,wav,video,seed)
    captions=["카드리더기로 간편하게 결제하고 랜덤으로 즐기는 가챠머신 창업. 실제 운영 매장과 캐릭존 공급 머신을 확인해보세요.","작은 공간에도 시선을 끄는 가챠머신. 카드 결제부터 머신 구성, 운영 상담까지 캐릭존이 함께합니다.","매장 체류시간과 재미를 더하는 카드결제 가챠머신. 실제 설치 분위기와 다양한 머신을 영상에서 확인하세요.","무인 운영 아이템을 찾고 있다면 카드결제 가챠머신을 확인해보세요. 공간별 구성과 창업 상담을 안내합니다."]
    manifest["reels"].append({"id":rid,"approved":False,"rejected":False,"published":False,"slot":slot,"scheduled_for":schedule(day,slot).isoformat(),"video_url":f"https://raw.githubusercontent.com/canakard1000/characzone-auto-reels/main/{video.name}","caption":captions[seed%4]+" 창업상담 010-2587-8553 #가챠머신 #가챠머신창업 #무인창업 #소자본창업 #캐릭존","source_images":[p.name for p in selected],"music_variant":seed%12,"telegram_notified":False,"created_at":datetime.now(timezone.utc).isoformat()})
    print("Created",video.name,"from 9 supplied photos")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--date"); p.add_argument("--force",action="store_true"); a=p.parse_args(); day=date.fromisoformat(a.date) if a.date else datetime.now(KST).date()+timedelta(days=1)
    data=json.loads(MANIFEST.read_text()); data.setdefault("reels",[])
    if a.force:
        prefix=f"characzone-{day.isoformat()}-"
        data["reels"]=[item for item in data["reels"] if not item.get("id","").startswith(prefix)]
    for slot in ("am","pm"): build(day,slot,data)
    MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__": main()

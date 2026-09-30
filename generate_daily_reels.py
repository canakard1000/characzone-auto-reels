"""Create two varied approval-gated Characzone reels from supplied photos."""
import argparse, json, math, random, shutil, subprocess, textwrap, wave
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
ASSETS, MANIFEST = ROOT / "assets/source", ROOT / "approved.json"
REGULAR, BOLD = ROOT / "assets/fonts/NanumGothic-Regular.ttf", ROOT / "assets/fonts/NanumGothic-Bold.ttf"
KST, SIZE, SCENE_SECONDS = timezone(timedelta(hours=9)), (1080, 1920), 1.35
# 승인된 실제 판매 가챠머신 사진만 누적 사용한다. 집게/크레인 머신 사진은 사용 금지.
APPROVED_SOURCE_PATTERN = "gacha-model-*"
THEMES = [((8,19,44),(0,229,255),(255,72,187)),((21,12,37),(255,214,10),(255,75,43)),((8,32,28),(88,255,150),(34,211,238)),((28,16,54),(178,104,255),(255,103,164)),((35,22,14),(255,174,66),(255,245,190)),((12,24,52),(76,140,255),(255,255,255))]
HOOKS = ["카드 한 장으로 시작되는 랜덤의 재미","지금 매장에 필요한 새로운 체류 포인트","작은 공간도 눈길 끄는 무인 콘텐츠로","실제 운영 매장에서 확인한 인기 포인트","다음 창업 아이템, 가챠머신은 어떨까요?","결제는 간편하게, 재미는 더 크게"]
COPY = ["카드리더기 간편 결제","랜덤 뽑기의 강한 몰입감","실제 운영 매장 분위기","공간에 맞춘 머신 구성","다양한 컬러와 디자인","무인 운영에 어울리는 구성","설치부터 운영까지 상담","캐릭존 공급 가챠머신","가챠머신 창업 상담"]

def ft(path, size): return ImageFont.truetype(str(path), size)

def photos():
    # 새 사진은 다음 gacha-model-N 이름으로 추가한다. 기존 승인 사진은 유지되어
    # 사진 풀이 계속 커지고 날짜마다 만들 수 있는 조합도 함께 늘어난다.
    items = sorted(
        (p for p in ASSETS.glob(APPROVED_SOURCE_PATTERN) if p.is_file()),
        key=lambda p: p.name,
    )
    if len(items) < 5: raise RuntimeError("At least 5 approved Characzone gacha-machine photos are required")
    return items

def centered_text(draw, text, y, font, fill, stroke_fill, max_chars=14):
    lines=textwrap.wrap(text,width=max_chars) or [text]
    boxes=[draw.textbbox((0,0),line,font=font,stroke_width=3) for line in lines]
    heights=[b[3]-b[1] for b in boxes]; total=sum(heights)+18*(len(lines)-1)
    cursor=y-total//2
    for line,box,h in zip(lines,boxes,heights):
        w=box[2]-box[0]
        draw.text(((1080-w)//2,cursor),line,font=font,fill=fill,stroke_width=3,stroke_fill=stroke_fill)
        cursor+=h+18

def scene(photo, output, title, theme, index, template):
    with Image.open(photo) as src: image = ImageOps.exif_transpose(src).convert("RGB")
    image = ImageEnhance.Contrast(ImageEnhance.Color(image).enhance(1.12)).enhance(1.08)
    # 같은 3종도 전경·상단·결제부를 번갈아 보여 9개 장면이 반복되어 보이지 않게 한다.
    centering=((0.5,0.5),(0.5,0.28),(0.5,0.72))[index%3]
    image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS,centering=centering).convert("RGBA")
    base, a1, a2 = theme; accent = a1 if index % 2 == 0 else a2
    layer = Image.new("RGBA", SIZE); layer.putalpha(0); d = ImageDraw.Draw(layer)
    if template%3==0:
        d.rounded_rectangle((70,675,1010,1195),54,fill=(*base,178),outline=(*accent,235),width=5)
    elif template%3==1:
        d.polygon([(0,600),(1080,470),(1080,1210),(0,1340)],fill=(*base,178))
        d.line((0,600,1080,470),fill=(*accent,235),width=8); d.line((0,1340,1080,1210),fill=(*accent,235),width=8)
    else:
        d.ellipse((-120,555,1200,1355),fill=(*base,172),outline=(*accent,235),width=7)
    d.rounded_rectangle((62,62,352,132),30,fill=(*accent,235))
    d.rounded_rectangle((120,1645,960,1760),34,fill=(0,0,0,155),outline=(*accent,220),width=3)
    image = Image.alpha_composite(image, layer); d = ImageDraw.Draw(image)
    d.text((92,78),"CHARACZONE",font=ft(BOLD,39),fill="white")
    centered_text(d,title,940,ft(BOLD,66),"white",base)
    d.text((178,1678),"가챠머신 창업상담  010-2876-8553",font=ft(BOLD,38),fill="white")
    d.text((930,82),f"{index+1:02d}/09",font=ft(BOLD,28),fill="white")
    image.convert("RGB").save(output, quality=94)

def music(path, seconds, seed):
    rng=random.Random(seed); rate=44100
    styles=[(124,[0,7,12,7,3,10,12,15],.34),(132,[0,12,7,15,10,7,3,12],.40),(140,[0,3,7,10,12,15,12,7],.44),(146,[0,7,10,14,12,7,15,10],.48),(128,[0,5,9,12,9,5,14,12],.38)]
    bpm,melody,energy=styles[seed%len(styles)]; beat=60/bpm
    roots=rng.choice([[110,146.83,164.81,146.83],[130.81,174.61,196,174.61],[98,130.81,146.83,130.81]])
    frames=bytearray()
    for n in range(int(rate*seconds)):
        t=n/rate; bi=int(t/beat); phase=(t%beat)/beat; root=roots[(bi//4)%4]; lead=root*(2**(melody[bi%8]/12))*2
        kp=t%beat; hp=t%(beat/2)
        val=.24*math.sin(2*math.pi*root*t)*math.exp(-phase*5)+energy*math.sin(2*math.pi*lead*t)*(.30+.70*math.exp(-phase*3))
        val += .48*math.sin(2*math.pi*(68-28*min(kp/.16,1))*kp)*math.exp(-kp*22)+.09*(rng.random()*2-1)*math.exp(-hp*58)
        sample=int(max(-.92,min(.92,val))*32767); frames += sample.to_bytes(2,"little",signed=True)*2
    with wave.open(str(path),"wb") as w: w.setparams((2,2,rate,0,"NONE","not compressed")); w.writeframes(frames)

def encode(frames, soundtrack, output, seed):
    work=output.parent/f".{output.stem}-frames"; work.mkdir(exist_ok=True)
    try:
        fps=12; per_scene=round(SCENE_SECONDS*fps); number=0
        for i,frame in enumerate(frames):
            with Image.open(frame) as opened: source=opened.convert("RGB")
            direction=(seed+i)%4
            for step in range(per_scene):
                progress=step/max(1,per_scene-1); zoom=1.0+(0.055 if direction<2 else 0.085)*progress; cw=int(1080/zoom); ch=int(1920/zoom)
                x=[(1080-cw)//2,0,1080-cw,int((1080-cw)*(1-progress))][direction]; y=int((1920-ch)*(progress if direction==3 else .5))
                source.crop((x,y,x+cw,y+ch)).resize(SIZE,Image.Resampling.LANCZOS).save(work/f"frame-{number:04d}.jpg",quality=88)
                number+=1
        subprocess.run(["ffmpeg","-loglevel","error","-y","-framerate",str(fps),"-i",str(work/"frame-%04d.jpg"),"-i",str(soundtrack),"-shortest","-vf","fps=30,format=yuv420p","-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","160k","-movflags","+faststart",str(output)],check=True)
    finally: shutil.rmtree(work,ignore_errors=True)

def schedule(day,slot): return datetime.combine(day,time(9 if slot=="am" else 16),tzinfo=KST).astimezone(timezone.utc)

def build(day,slot,manifest):
    rid=f"characzone-{day.isoformat()}-{slot}"
    if any(x.get("id")==rid for x in manifest["reels"]): print("Already exists:",rid); return
    seed=int(day.strftime("%Y%m%d"))*10+(1 if slot=="am" else 2); rng=random.Random(seed); sources=photos(); selected=[]
    for _ in range(2):
        block=sources[:]; rng.shuffle(block); selected.extend(block)
    selected=selected[:9]
    copy=COPY[:]; rng.shuffle(copy); theme=THEMES[seed%len(THEMES)]; work=ROOT/"build"/rid; work.mkdir(parents=True,exist_ok=True); frames=[]
    for i,p in enumerate(selected):
        out=work/f"scene-{i:02d}.jpg"; scene(p,out,rng.choice(HOOKS) if i==0 else copy[i],theme,i,(seed+i)%6); frames.append(out)
    wav=work/"music.wav"; music(wav,len(frames)*SCENE_SECONDS+.5,seed); video=ROOT/f"{rid}.mp4"; encode(frames,wav,video,seed)
    captions=["카드리더기로 간편하게 결제하고 랜덤으로 즐기는 가챠머신 창업. 실제 운영 매장과 캐릭존 공급 머신을 확인해보세요.","작은 공간에도 시선을 끄는 가챠머신. 카드 결제부터 머신 구성, 운영 상담까지 캐릭존이 함께합니다.","매장 체류시간과 재미를 더하는 카드결제 가챠머신. 실제 설치 분위기와 다양한 머신을 영상에서 확인하세요.","무인 운영 아이템을 찾고 있다면 카드결제 가챠머신을 확인해보세요. 공간별 구성과 창업 상담을 안내합니다."]
    manifest["reels"].append({"id":rid,"approved":False,"rejected":False,"published":False,"slot":slot,"scheduled_for":schedule(day,slot).isoformat(),"video_url":f"https://raw.githubusercontent.com/canakard1000/characzone-auto-reels/main/{video.name}","caption":captions[seed%4]+" 창업상담 010-2876-8553 #가챠머신 #가챠머신창업 #무인창업 #소자본창업 #캐릭존","source_images":[p.name for p in selected],"template_variant":seed%6,"music_variant":seed%5,"telegram_notified":False,"created_at":datetime.now(timezone.utc).isoformat()})
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

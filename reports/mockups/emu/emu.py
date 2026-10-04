import json
from playwright.sync_api import sync_playwright
B="http://localhost:8765"
OUT="/workspace/photo3d/reports/mockups/emu/"
devs={"iphone14_portrait":(390,844,3),"iphone14_landscape":(844,390,3),"ipad_portrait":(820,1180,2),"ipad_landscape":(1180,820,2),"ipad_splitview_third":(320,1024,2),"ipad_slideover":(375,1024,2)}
JS="""()=>{
 const vw=innerWidth; const res={scrollW:document.documentElement.scrollWidth, vw};
 const vis=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!='hidden'&&s.display!='none'};
 const sel='button,a[href],input:not([type=hidden]):not([type=file]),select,summary,label.drop,[role=button]';
 const small=[],off=[],fs=[];
 document.querySelectorAll(sel).forEach(e=>{ if(!vis(e)||e.closest('[hidden]')||e.closest('dialog:not([open])'))return; const r=e.getBoundingClientRect();
   const id=(e.id?'#'+e.id:e.tagName.toLowerCase()+(e.className&&typeof e.className=='string'?'.'+e.className.split(' ')[0]:''))+(e.textContent.trim()?'['+e.textContent.trim().slice(0,18)+']':'');
   if(r.width<44||r.height<44) small.push([id,Math.round(r.width),Math.round(r.height)]);
   if(r.right>vw+1||r.left<-1) off.push([id,Math.round(r.left),Math.round(r.right)]);
   if(['INPUT','SELECT','TEXTAREA'].includes(e.tagName)){const f=parseFloat(getComputedStyle(e).fontSize); if(f<16) fs.push([id,f]);}
 });
 const hdr=document.querySelector('.topbar').getBoundingClientRect();
 res.small=small.length; res.smallSample=small.slice(0,14); res.off=off; res.fsSmall=fs.slice(0,12); res.fsCount=fs.length; res.headerH=Math.round(hdr.height);
 res.viewerH=Math.round(document.querySelector('#viewer').getBoundingClientRect().height);
 return res}"""
out={}
with sync_playwright() as p:
    b=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for name,(w,h,d) in devs.items():
        ctx=b.new_context(viewport={'width':w,'height':h},device_scale_factor=d,is_mobile=True,has_touch=True)
        try:
          pass
        except: pass
        pg=ctx.new_page(); pg.set_default_timeout(30000)
        pg.goto(B,wait_until="commit"); pg.wait_for_timeout(3000)
        r={}
        r["studio_empty"]=pg.evaluate(JS)
        pg.screenshot(path=OUT+name+"_studio.png")
        pg.click("#btnSample"); pg.click("#btnBuild"); pg.wait_for_timeout(4500)
        r["studio_built"]=pg.evaluate(JS)
        pg.screenshot(path=OUT+name+"_studio_built.png")
        pg.screenshot(path=OUT+name+"_studio_built_full.png",full_page=True)
        try:
            pg.evaluate("document.querySelector('#btnPrint').click()"); pg.wait_for_timeout(800)
            r["print_dialog"]=pg.evaluate(JS); pg.screenshot(path=OUT+name+"_print.png")
            pg.keyboard.press("Escape")
        except Exception as e: r["print_err"]=str(e)[:100]
        for v in ["edit","showcase","learn"]:
            pg.evaluate(f"document.querySelector('#mainNav [data-view={v}]').click()"); pg.wait_for_timeout(900)
            r[v]=pg.evaluate(JS)
            if name in("iphone14_portrait","ipad_portrait"): pg.screenshot(path=OUT+f"{name}_{v}.png")
        out[name]=r
        ctx.close()
    b.close()
json.dump(out,open("emu.json","w"),indent=1)
for n,r in out.items():
    print(n,{k:(v["scrollW"],v["vw"],v["headerH"],v["small"],v["fsCount"],len(v["off"])) for k,v in r.items() if isinstance(v,dict)})

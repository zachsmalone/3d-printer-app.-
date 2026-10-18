import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { STLExporter } from 'three/addons/exporters/STLExporter.js';
import { heightfield } from './geometry.js';
import { createIcons, Box, Palette, SlidersHorizontal, Sun, Upload, Scan, Download, Check, Route, Info, ImageUp, RotateCcw, Shuffle, Lock, LockOpen } from 'lucide';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const icons = { Box, Palette, SlidersHorizontal, Sun, Upload, Scan, Download, Check, Route, Info, ImageUp, RotateCcw, Shuffle, Lock, LockOpen };
const refreshIcons = () => {createIcons({icons,attrs:{'stroke-width':1.6}});$$('button,input,a,summary').forEach((e,i)=>{if(!e.dataset.testid)e.dataset.testid=e.id||`${e.tagName.toLowerCase()}-${e.dataset.view||e.dataset.lock||e.dataset.litView||i}`;});};
let statusTimer;
function status(message) { const n=$('#status-message'); n.textContent=message; n.hidden=false; clearTimeout(statusTimer);statusTimer=setTimeout(()=>n.hidden=true,6500); }
function download(data,name,type) { const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),20000);status(`${name} is ready. Check your browser downloads.`); }
let currentView='studio';
function showView(v) {currentView=v;$$('.view').forEach(n=>{n.classList.toggle('active',n.id===`view-${v}`);n.hidden=n.id!==`view-${v}`;});$$('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===v);b.setAttribute('aria-current',b.dataset.view===v?'page':'false');});window.scrollTo({top:0,behavior:'instant'});if(v==='studio')requestAnimationFrame(()=>{resizeStage();if(renderer&&scene&&camera){controls.update();renderer.render(scene,camera);}});if(v==='appearance')paintThemeSample();}
$$('[data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view));
$('#appearance-shortcut').onclick=()=>showView('appearance');
document.addEventListener('keydown',e=>{if(/input|textarea|select/i.test(e.target.tagName)||e.ctrlKey||e.metaKey||e.altKey)return;if(['1','2','3'].includes(e.key))showView(['studio','litho','appearance'][+e.key-1]);});

// A file-local state model; no browser storage or external uploads.
const presets=[
 {name:'Workshop',mood:'Quiet & grounded',bg:'#f3f3ee',panel:'#fcfcf8',text:'#242d27',accent:'#315f48'},
 {name:'Kiln',mood:'Warm & tactile',bg:'#f5eee8',panel:'#fffaf6',text:'#392d28',accent:'#a34229'},
 {name:'Blueprint',mood:'Crisp & precise',bg:'#edf1f6',panel:'#fafcfe',text:'#24334a',accent:'#2854a0'},
 {name:'Graphite',mood:'Reduced & focused',bg:'#eeefef',panel:'#fcfcfc',text:'#292d30',accent:'#424b50'},
 {name:'Tidepool',mood:'Fresh & collected',bg:'#edf3f2',panel:'#f9fdfc',text:'#203b3b',accent:'#21636b'},
 {name:'Orchid',mood:'Soft & expressive',bg:'#f4eff2',panel:'#fffafe',text:'#392e38',accent:'#875070'}
];
let theme={...presets[0]}, locks=new Set(), mods={dark:matchMedia('(prefers-color-scheme:dark)').matches,grid:false,left:false,roomy:false};
const roles=['bg','panel','text','accent'],roleNames={bg:'Background',panel:'Surface',text:'Text',accent:'Accent'};
function rgb(hex){return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));}
function lum(hex){return rgb(hex).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);}
function contrast(a,b){const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
function mix(a,b,t){return '#'+rgb(a).map((v,i)=>Math.round(v*(1-t)+rgb(b)[i]*t).toString(16).padStart(2,'0')).join('');}
function safeText(bg,wanted){if(contrast(bg,wanted)>=4.5)return wanted;return contrast(bg,'#ffffff')>contrast(bg,'#000000')?'#ffffff':'#000000';}
function effectiveTheme(){let t={...theme};if(mods.dark){t.bg='#1b211e';t.panel='#242c27';t.text='#e5ebe4';t.accent=mix(theme.accent,'#d9f1df',.55);}t.text=safeText(t.bg,t.text);if(contrast(t.panel,t.text)<4.5){const requested=t.panel;for(let i=1;i<=10;i++){t.panel=mix(requested,t.bg,i/10);if(contrast(t.panel,t.text)>=4.5)break;}}return t;}
function applyTheme(rebuild=true) {
 const t=effectiveTheme(),r=document.documentElement.style;
 let tint=mix(t.accent,t.panel,.89),stageColor=mix(t.bg,t.accent,.055);
 if(contrast(t.text,tint)<4.5)tint=t.panel;if(contrast(t.text,stageColor)<4.5)stageColor=t.bg;
 let muted=mix(t.text,t.bg,.24);if(Math.min(contrast(muted,t.bg),contrast(muted,t.panel),contrast(muted,stageColor))<4.5)muted=t.text;
 const accentText=Math.min(contrast(t.accent,t.bg),contrast(t.accent,tint),contrast(t.accent,t.panel))>=4.5?t.accent:t.text;
 Object.entries({bg:t.bg,panel:t.panel,text:t.text,accent:t.accent,'accent-text':accentText,'on-accent':contrast(t.accent,'#ffffff')>=4.5?'#ffffff':'#000000',muted,line:mix(t.text,t.bg,.83),tint,stage:stageColor,danger:lum(t.bg)<.3?'#ffb5b5':'#a42c2c'}).forEach(([k,v])=>r.setProperty(`--${k}`,v));
 document.body.classList.toggle('left-layout',mods.left);document.body.classList.toggle('roomy',mods.roomy);
 for(const key of Object.keys(mods))$(`#mod-${key}`).checked=mods[key];
 if(scene){scene.background=new THREE.Color(stageColor);grid.visible=!mods.grid;grid.material.opacity=.2;}
 $('#contrast-value').textContent=`${Math.min(contrast(t.text,t.bg),contrast(t.text,t.panel)).toFixed(2)} : 1`;$('#contrast-status').textContent='AA text pass';
 if(rebuild)renderThemeControls();paintThemeSample();
}
function renderThemeControls(){
 $('#theme-presets').innerHTML=presets.map((p,i)=>`<button class="theme-card" data-preset="${i}" aria-pressed="${theme.name===p.name}" data-testid="preset-${p.name}"><div class="theme-swatches">${[p.bg,p.panel,p.accent,p.text].map(c=>`<span style="background:${c}"></span>`).join('')}</div><strong>${p.name}</strong><span>${p.mood}</span></button>`).join('');
 $('#role-colors').innerHTML=roles.map(k=>`<div class="role-color"><label for="role-${k}">${roleNames[k]}</label><input id="role-${k}" type="color" value="${theme[k]}" aria-label="${roleNames[k]} color"><div><code>${theme[k].toUpperCase()}</code><button class="lock-button" data-lock="${k}" aria-label="${locks.has(k)?'Unlock':'Lock'} ${roleNames[k]}" aria-pressed="${locks.has(k)}"><i data-lucide="${locks.has(k)?'lock':'lock-open'}"></i></button></div></div>`).join('');
 $$('[data-preset]').forEach(b=>b.onclick=()=>{theme={...presets[+b.dataset.preset]};mods.dark=false;applyTheme();});
 $$('[data-lock]').forEach(b=>b.onclick=()=>{const k=b.dataset.lock;locks.has(k)?locks.delete(k):locks.add(k);renderThemeControls();});
 roles.forEach(k=>$(`#role-${k}`).oninput=e=>{theme[k]=e.target.value;theme.name='Custom';mods.dark=false;applyTheme(false);e.target.parentElement.querySelector('code').textContent=theme[k].toUpperCase();$$('[data-preset]').forEach(b=>b.setAttribute('aria-pressed','false'));});
 refreshIcons();
}
$('#shuffle-theme').onclick=()=>{if(locks.size===4){status('All colors are locked. Unlock a color to remix it.');return;}let p=presets[Math.floor(Math.random()*presets.length)];for(const k of roles)if(!locks.has(k))theme[k]=p[k];theme.name='Custom';mods.dark=false;applyTheme();};
Object.keys(mods).forEach(k=>$(`#mod-${k}`).onchange=e=>{mods[k]=e.target.checked;applyTheme(false);});
$('#reset-theme').onclick=()=>{theme={...presets[0]};mods={dark:false,grid:false,left:false,roomy:false};locks.clear();applyTheme();status('Workshop colors and default layout restored.');};
$('#export-theme').onclick=()=>download(JSON.stringify({format:'zeim-theme',version:1,colors:Object.fromEntries(roles.map(k=>[k,theme[k]])),mods,locks:[...locks]},null,2),'zeim-workbench-theme.json','application/json');
$('#import-theme-button').onclick=()=>$('#theme-file').click();
$('#theme-file').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>8192)throw Error('Theme files must be smaller than 8 KB.');const x=JSON.parse(await f.text());if(x.format!=='zeim-theme'||x.version!==1||!roles.every(k=>/^#[0-9a-f]{6}$/i.test(x.colors?.[k]))||!Object.keys(mods).every(k=>typeof x.mods?.[k]==='boolean')||(x.locks&&!Array.isArray(x.locks)))throw Error('Choose a valid ZEIM theme v1 JSON file.');theme={name:'Custom',...Object.fromEntries(roles.map(k=>[k,x.colors[k]]))};mods=Object.fromEntries(Object.keys(mods).map(k=>[k,x.mods[k]]));locks=new Set((x.locks||[]).filter(k=>roles.includes(k)));applyTheme();status('Your theme and mods are applied.');}catch(err){status(err.message);}finally{e.target.value='';}};
function paintThemeSample(){
 const c=$('#theme-canvas'),ctx=c.getContext('2d'),t=effectiveTheme();ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle=mix(t.bg,t.accent,.055);ctx.fillRect(0,0,480,340);ctx.strokeStyle=mix(t.text,t.bg,.88);ctx.lineWidth=1;
 if(!mods.grid)for(let i=-8;i<12;i++){ctx.beginPath();ctx.moveTo(240+i*45,70);ctx.lineTo(i*45-50,340);ctx.stroke();ctx.beginPath();ctx.moveTo(0,90+i*26);ctx.lineTo(480,90+i*26);ctx.stroke();}
 const face=(pts,color)=>{ctx.fillStyle=color;ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();ctx.strokeStyle=mix(color,t.text,.15);ctx.stroke();};
 face([[135,210],[290,270],[365,220],[210,160]],mix(t.accent,t.bg,.62));
 face([[135,210],[290,270],[290,284],[135,224]],mix(t.accent,t.text,.1));
 face([[290,270],[365,220],[365,234],[290,284]],mix(t.accent,t.text,.3));
 face([[135,210],[210,160],[210,62],[135,112]],mix(t.accent,t.bg,.38));
 face([[135,112],[210,62],[222,67],[147,117]],mix(t.accent,t.bg,.68));
 face([[147,117],[222,67],[222,165],[147,215]],mix(t.accent,t.bg,.52));
 ctx.fillStyle=mix(t.accent,t.text,.65);ctx.beginPath();ctx.ellipse(184,142,9,14,.5,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.ellipse(280,223,13,6,.3,0,Math.PI*2);ctx.fill();
}

// Real geometry viewer. Mesh editing beyond uniform scale is deliberately not advertised.
let scene,renderer,camera,controls,grid,model,original=null;
const stage=$('#model-stage');
function sampleModel(){
 const material=new THREE.MeshStandardMaterial({color:$('#model-color').value,roughness:.62,metalness:.05,side:THREE.DoubleSide});
 const g=new THREE.Group();
 const base=new THREE.Shape();base.moveTo(-42,-30);base.lineTo(42,-30);base.lineTo(42,30);base.lineTo(-42,30);base.closePath();
 for(const x of [-25,25]){const hole=new THREE.Path();hole.absarc(x,10,5.4,0,Math.PI*2,true);base.holes.push(hole);}
 const geom=new THREE.ExtrudeGeometry(base,{depth:7,bevelEnabled:true,bevelSegments:2,steps:1,bevelSize:1.2,bevelThickness:1.2,curveSegments:36});
 const foot=new THREE.Mesh(geom,material);foot.rotation.x=-Math.PI/2;foot.position.y=1.2;g.add(foot);
 const back=new THREE.Shape();back.moveTo(-42,0);back.lineTo(42,0);back.lineTo(42,60);back.quadraticCurveTo(42,72,30,72);back.lineTo(-30,72);back.quadraticCurveTo(-42,72,-42,60);back.closePath();
 for(const x of [-25,25]){const h=new THREE.Path();h.absarc(x,50,5.4,0,Math.PI*2,true);back.holes.push(h);}
 const wall=new THREE.Mesh(new THREE.ExtrudeGeometry(back,{depth:7,bevelEnabled:true,bevelSegments:2,bevelSize:1.2,bevelThickness:1.2,curveSegments:36}),material);wall.position.z=-28;g.add(wall);
 const rib=new THREE.Shape();rib.moveTo(0,0);rib.lineTo(0,50);rib.lineTo(43,0);rib.closePath();
 for(const x of [-38,34]){const mesh=new THREE.Mesh(new THREE.ExtrudeGeometry(rib,{depth:4,bevelEnabled:false}),material);mesh.rotation.y=-Math.PI/2;mesh.position.set(x,8,-20);g.add(mesh);}
 return g;
}
function disposeObject(obj){obj?.traverse(n=>{if(n.isMesh){n.geometry.dispose();if(n.material?.dispose)n.material.dispose();}});}
function setModel(obj){
 if(model){scene.remove(model);disposeObject(model);}model=obj;scene.add(model);const box=new THREE.Box3().setFromObject(model),center=box.getCenter(new THREE.Vector3());model.position.sub(center);const size=box.getSize(new THREE.Vector3());model.position.y+=size.y/2+1.5;model.updateMatrixWorld(true);$('#model-scale').value=100;$('#scale-output').textContent='100%';original=model.scale.clone();updateDimensions();resetCamera();
}
function updateDimensions(){if(!model)return;model.updateMatrixWorld(true);const s=new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3());$('#model-dimensions').textContent=`${s.x.toFixed(1)} × ${s.z.toFixed(1)} × ${s.y.toFixed(1)} mm`;let count=0;model.traverse(n=>{if(n.isMesh)count+=(n.geometry.index?.count||n.geometry.attributes.position.count)/3;});$('#mesh-count').textContent=`${Math.round(count).toLocaleString()} triangles`;}
function resetCamera(){if(!model)return;const box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());const d=Math.max(size.x,size.y,size.z)*1.8;camera.position.copy(center).add(new THREE.Vector3(d*.9,d*.7,d*1.05));camera.near=Math.max(.001,d/1000);camera.far=d*100;camera.updateProjectionMatrix();controls.target.copy(center);controls.update();grid.scale.setScalar(Math.max(1,d/240));}
function resizeStage(){if(!renderer)return;const w=stage.clientWidth,h=stage.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
try{
 scene=new THREE.Scene();renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;stage.appendChild(renderer.domElement);camera=new THREE.PerspectiveCamera(36,1,.1,10000);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.49;
 scene.add(new THREE.HemisphereLight(0xf8fff7,0x9fa69c,2.5));const key=new THREE.DirectionalLight(0xfff7e7,3);key.position.set(-80,180,130);scene.add(key);const fill=new THREE.DirectionalLight(0xffffff,1.4);fill.position.set(150,80,-80);scene.add(fill);grid=new THREE.GridHelper(440,22,0x7e9686,0xa6b2a4);grid.material.transparent=true;grid.material.opacity=.2;scene.add(grid);
 setModel(sampleModel());new ResizeObserver(resizeStage).observe(stage);renderer.setAnimationLoop(()=>{if(currentView==='studio'){controls.update();renderer.render(scene,camera);}});
}catch(err){stage.insertAdjacentHTML('beforeend','<p class="scope-note">3D rendering is unavailable in this browser. Theme and lithophane controls still work.</p>');status('WebGL viewer unavailable. Try a browser with hardware acceleration.');}
$('#reset-camera').onclick=resetCamera;
function wireframe(value){model?.traverse(n=>{if(n.isMesh)n.material.wireframe=value;});$('#wire-button').classList.toggle('selected',value);$('#solid-button').classList.toggle('selected',!value);$('#wire-button').setAttribute('aria-pressed',String(value));$('#solid-button').setAttribute('aria-pressed',String(!value));}
$('#wire-button').onclick=()=>wireframe(true);$('#solid-button').onclick=()=>wireframe(false);
$('#model-scale').oninput=e=>{if(!model)return;model.scale.copy(original).multiplyScalar(+e.target.value/100);$('#scale-output').textContent=`${e.target.value}%`;updateDimensions();};
$('#model-color').oninput=e=>{model?.traverse(n=>{if(n.isMesh)n.material.color.set(e.target.value);});$('#material-hex').textContent=e.target.value.toUpperCase();};
$('#restore-model').onclick=()=>{if(!scene)return;setModel(sampleModel());$('#stage-filename').textContent='wall-mount.stl · sample mesh';$('#studio-title').innerHTML='A better wall mount<span class="subtle">.stl</span>';$('#project-label').textContent='A better wall mount';wireframe(false);status('Sample restored. No imported source file was modified.');};
$('#import-button').onclick=()=>$('#model-file').click();
$('#model-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(!renderer)throw Error('The 3D viewer is unavailable in this browser.');if(f.size>30*1024*1024)throw Error('For this preview, use a model smaller than 30 MB.');const ext=f.name.split('.').pop().toLowerCase();let obj;if(ext==='stl'){const geometry=new STLLoader().parse(await f.arrayBuffer());if(!geometry.attributes.position.count)throw Error('No triangles found in this STL.');geometry.computeVertexNormals();obj=new THREE.Group();obj.add(new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:$('#model-color').value,roughness:.65,side:THREE.DoubleSide})));}else if(ext==='obj'){obj=new OBJLoader().parse(await f.text());let has=false;obj.traverse(n=>{if(n.isMesh){has=true;n.material=new THREE.MeshStandardMaterial({color:$('#model-color').value,roughness:.65,side:THREE.DoubleSide});}});if(!has)throw Error('This OBJ has no mesh faces.');}else throw Error('This viewer accepts STL and OBJ. STEP/3MF editing is planned, not enabled here.');const box=new THREE.Box3().setFromObject(obj),d=box.getSize(new THREE.Vector3());if(box.isEmpty()||!Number.isFinite(d.length())||d.length()===0)throw Error('The mesh has invalid or empty geometry.');setModel(obj);wireframe(false);$('#stage-filename').textContent=f.name;$('#studio-title').textContent=f.name;$('#project-label').textContent=f.name;status('Model loaded locally. Confirm units; mesh health is not validated in this preview.');}catch(err){status(`Import failed: ${err.message}`);}finally{e.target.value='';}};
$('#export-model').onclick=()=>{if(!model)return status('Load a model first.');model.updateMatrixWorld(true);const data=new STLExporter().parse(model,{binary:true});download(data,'zeim-remix.stl','model/stl');};

// Flat lithophane prototype: source luminance -> monotonic thickness -> closed heightfield mesh.
const source=document.createElement('canvas');source.width=640;source.height=480;
function makeSample(){const c=source.getContext('2d'),g=c.createLinearGradient(0,0,0,480);g.addColorStop(0,'#929ea2');g.addColorStop(.7,'#e6ddc5');g.addColorStop(1,'#4c6260');c.fillStyle=g;c.fillRect(0,0,640,480);c.fillStyle='#eee8d5';c.beginPath();c.arc(470,112,39,0,Math.PI*2);c.fill();const ridge=(pts,col)=>{c.fillStyle=col;c.beginPath();pts.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.lineTo(640,480);c.lineTo(0,480);c.closePath();c.fill();};ridge([[0,310],[80,245],[140,280],[270,115],[330,210],[390,186],[500,290],[640,220]],'#72878a');ridge([[0,380],[145,310],[205,340],[330,230],[460,335],[560,290],[640,340]],'#4e6667');ridge([[0,440],[160,385],[245,405],[340,345],[450,395],[640,355]],'#2c4845');c.fillStyle='#d8dbd3';c.beginPath();c.moveTo(270,115);c.lineTo(218,183);c.lineTo(262,168);c.lineTo(285,186);c.lineTo(308,174);c.closePath();c.fill();for(let i=0;i<50;i++){const x=i*17-55,y=380+Math.sin(i*2.4)*36;c.fillStyle=i%2?'#314e43':'#3b594b';c.beginPath();c.moveTo(x,y-65);c.lineTo(x-18,y);c.lineTo(x+18,y);c.closePath();c.fill();}}
makeSample();let litMode='backlit';
function lithoSettings(){const w=+$('#litho-width').value,min=+$('#litho-min').value,max=+$('#litho-max').value,gamma=+$('#litho-gamma').value,warmth=+$('#light-warmth').value;if(!Number.isFinite(w)||w<30||w>250)throw Error('Choose a width from 30 to 250 mm.');if(!Number.isFinite(min)||!Number.isFinite(max)||min<.4||min>4||max>8||max<=min)throw Error('Use 0.4–4 mm minimum and a larger maximum up to 8 mm.');return{w,min,max,gamma,warmth,h:w*source.height/source.width};}
function luminances(nx,ny,gamma){const tmp=document.createElement('canvas');tmp.width=nx;tmp.height=ny;const c=tmp.getContext('2d',{willReadFrequently:true});c.drawImage(source,0,0,nx,ny);const data=c.getImageData(0,0,nx,ny).data,result=new Float32Array(nx*ny);for(let i=0;i<result.length;i++){let v=(.2126*data[i*4]+.7152*data[i*4+1]+.0722*data[i*4+2])/255;result[i]=Math.pow(v,gamma);}return result;}
function updateLitho(){try{const s=lithoSettings(),c=$('#litho-canvas'),ctx=c.getContext('2d');$('#litho-error').textContent='';$('#export-litho').disabled=false;c.width=640;c.height=Math.round(640*source.height/source.width);if(litMode==='source')ctx.drawImage(source,0,0,c.width,c.height);else{const lum=luminances(c.width,c.height,s.gamma),image=ctx.createImageData(c.width,c.height);for(let i=0;i<lum.length;i++){const t=s.min+(1-lum[i])*(s.max-s.min);let v=litMode==='backlit'?Math.exp(-.65*t)*255:255*(t-s.min)/(s.max-s.min);const warm=(6500-s.warmth)/3800;image.data[i*4]=Math.min(255,v*(1+warm*.09));image.data[i*4+1]=v*(1-warm*.06);image.data[i*4+2]=v*(1-warm*.24);image.data[i*4+3]=255;}ctx.putImageData(image,0,0);}$('#litho-size').textContent=`${s.w.toFixed(0)} × ${s.h.toFixed(1)} mm`;$('#litho-range').textContent=`${s.min.toFixed(1)}–${s.max.toFixed(1)} mm thickness`;$('#gamma-output').textContent=s.gamma.toFixed(2);$('#warmth-output').textContent=`${s.warmth} K`;const ny=Math.max(16,Math.round(160*source.height/source.width));$('#litho-resolution').textContent=`Export grid: 160 × ${ny} cells. Preview quality; not calibrated to a printer.`;}catch(err){$('#litho-error').textContent=err.message;$('#export-litho').disabled=true;}}
$$('[data-lit-view]').forEach(b=>b.onclick=()=>{litMode=b.dataset.litView;$$('[data-lit-view]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});updateLitho();});
['litho-width','litho-min','litho-max','litho-gamma','light-warmth'].forEach(id=>$(`#${id}`).oninput=updateLitho);
$('#photo-button').onclick=()=>$('#photo-file').click();
$('#photo-file').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(!['image/png','image/jpeg','image/webp'].includes(f.type))throw Error('Choose a PNG, JPEG or WebP image.');if(f.size>20*1024*1024)throw Error('Choose an image smaller than 20 MB.');const img=await createImageBitmap(f);if(img.width<8||img.height<8)throw Error('The image is too small.');const ratio=img.width/img.height;if(ratio<.25||ratio>4)throw Error('Use an image with an aspect ratio between 1:4 and 4:1.');source.width=640;source.height=Math.round(640/ratio);const ctx=source.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,source.width,source.height);ctx.drawImage(img,0,0,source.width,source.height);img.close();$('#photo-name').textContent=f.name;updateLitho();status('Image processed in this tab. It was not uploaded.');}catch(err){status(`Image could not be loaded: ${err.message}`);}finally{e.target.value='';}};
$('#export-litho').onclick=()=>{try{const s=lithoSettings(),nx=160,ny=Math.max(16,Math.round(nx*source.height/source.width)),l=luminances(nx+1,ny+1,s.gamma),g=heightfield(nx,ny,s.w,s.h,(x,y)=>s.min+(1-l[(ny-y)*(nx+1)+x])*(s.max-s.min));const m=new THREE.Mesh(g);download(new STLExporter().parse(m,{binary:true}),'zeim-flat-lithophane.stl','model/stl');g.dispose();}catch(err){status(err.message);}};
$('#calibration-export').onclick=()=>{const g=heightfield(160,8,80,20,x=>.4+Math.min(15,Math.floor(x/10))*.25);download(new STLExporter().parse(new THREE.Mesh(g),{binary:true}),'zeim-thickness-coupon-0.40-to-4.15mm.stl','model/stl');g.dispose();status('Coupon: 16 left-to-right steps, 0.40 to 4.15 mm in 0.25 mm increments. Measure with your own light; no automatic calibration is claimed.');};
applyTheme();updateLitho();refreshIcons();if(renderer&&scene&&camera){resizeStage();controls.update();renderer.render(scene,camera);}window.zeimReady=true;

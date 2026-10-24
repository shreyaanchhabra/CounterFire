/* UI wiring. Map/chart drawing is unchanged from firebreak-ui.html; the hardcoded demo data
   is replaced by agent results streamed from the backend (SSE). Uses globals from sim.js. */
(()=>{
const $=id=>document.getElementById(id);
const css=getComputedStyle(document.documentElement);
const col=n=>css.getPropertyValue(n).trim();
const K={ember:col('--ember'),emberDim:col('--ember-dim'),flame:col('--flame'),water:col('--water'),waterDim:col('--water-dim'),faint:col('--faint'),muted:col('--muted'),line:col('--line'),fg:col('--fg'),ok:col('--ok'),warn:col('--warn')};
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
async function api(path,body){
  const opt=body instanceof FormData?{method:"POST",body}:body!==undefined?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{};
  const r=await fetch(path,opt);let d=null;try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d&&d.detail?d.detail:`HTTP ${r.status}`);return d}

/* ---------- state ---------- */
const S={t:0,playing:false,deploy:null,fr:"B",es:true,autoPause:true,edit:null};
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
// RUN holds the pipeline run: timeline from the backend, events waiting for their sim minute, and agent results.
const RUN={tl:{},pend:{},applied:{},shown:{},active:false,src:null,claim:"",incId:"SD-1024",imageUrl:"",
  pro:null,def:null,judge:null,drafted:false,scored:false,edDemo:null,ed:null,answers:null};
let POSTS=[];
let cur=run(null,S.fr,S.es);
function refresh(){cur=run(S.deploy,S.fr,S.es);lastInt=-1;updateCF();drawChart()}

/* ---------- map draw ---------- */
const mc=$('map'),mx=mc.getContext('2d');let MW=0,MH=0;
function fit(c){const r=c.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);c.width=Math.max(1,r.width*d);c.height=Math.max(1,r.height*d);const ctx=c.getContext('2d');ctx.setTransform(d,0,0,d,0,0);return[r.width,r.height]}
const P=(i)=>{const pad=MW<500?18:34;return[pad+pos[i][0]*(MW-2*pad),pad+8+pos[i][1]*(MH-2*pad-8)]};
function drawMap(now){
  const t=S.t,f=Math.min(T,Math.floor(t)),st=cur.frames[f];
  mx.clearRect(0,0,MW,MH);
  mx.lineWidth=.6;mx.strokeStyle="rgba(237,229,217,.06)";mx.beginPath();
  for(const[a,b]of g.edges){const[x1,y1]=P(a),[x2,y2]=P(b);mx.moveTo(x1,y1);mx.lineTo(x2,y2)}mx.stroke();
  // sparks
  for(let k=f;k<=Math.min(T,f+1);k++){for(const[j,i,kind]of cur.ev[k]){if(i<0)continue;const p=Math.max(0,Math.min(1,t-(k-1)));if(p<=0||p>=1.0001)continue;
    const[x1,y1]=P(i),[x2,y2]=P(j);const xe=x1+(x2-x1)*p,ye=y1+(y2-y1)*p;
    const gr=mx.createLinearGradient(x1,y1,xe,ye);const c=kind===1?K.ember:K.water;gr.addColorStop(0,"rgba(0,0,0,0)");gr.addColorStop(1,c);
    mx.strokeStyle=gr;mx.lineWidth=1.6;mx.beginPath();mx.moveTo(x1,y1);mx.lineTo(xe,ye);mx.stroke()}}
  // labels
  mx.font="500 11px 'IBM Plex Mono', monospace";mx.textAlign="center";
  const counts=new Array(C).fill(0);for(let i=0;i<N;i++)if(st[i]===1||st[i]===2)counts[g.cl[i]]++;
  centers.forEach(([cx,cy],c)=>{const pad=MW<500?18:34;let x=pad+cx*(MW-2*pad),y=pad+8+cy*(MH-2*pad-8);
    const dy=c===5?-34:(cy<.5?-58:58);if(c===2){y-=60}else y+=dy;if(c===5)y+=4;
    const hot=counts[c]/PER>.5;mx.fillStyle=hot?K.ember:K.muted;mx.fillText((MW<500?SHORT[c]:GROUPS[c]).toUpperCase(),x,Math.max(12,Math.min(MH-6,y)));});
  // nodes
  for(let i=0;i<N;i++){const s=st[i];const[x,y]=P(i);let r=2.4,c=K.faint;
    if(s===1){c=K.ember;r=3.4+Math.sin(now/120+i)*.7}else if(s===2){c=K.emberDim;r=2.9}else if(s===3){c=K.water;r=3.4+Math.sin(now/150+i)*.5}else if(s===4){c=K.waterDim;r=2.9}
    if(s===1||s===3){mx.fillStyle=s===1?"rgba(255,107,44,.16)":"rgba(92,200,255,.16)";mx.beginPath();mx.arc(x,y,r*3.2,0,7);mx.fill()}
    mx.fillStyle=c;mx.beginPath();mx.arc(x,y,r,0,7);mx.fill()}
  // origin marker
  const[ox,oy]=P(START);mx.strokeStyle=K.flame;mx.lineWidth=1;mx.beginPath();mx.arc(ox,oy,8,0,7);mx.stroke();
}

/* ---------- chart + spark ---------- */
const cc=$('chart'),cx=cc.getContext('2d');let CW=0,CH=0;
function drawChart(){
  if(!CW)return;cx.clearRect(0,0,CW,CH);const L=26,R=6,Tp=6,B=16,w=CW-L-R,h=CH-Tp-B;
  const X=t=>L+t/T*w,Y=v=>Tp+(1-v)*h;
  cx.font="10px 'IBM Plex Mono', monospace";cx.fillStyle=K.muted;cx.textAlign="right";cx.strokeStyle="rgba(237,229,217,.07)";cx.lineWidth=1;
  [0,.5,1].forEach(v=>{cx.beginPath();cx.moveTo(L,Y(v));cx.lineTo(L+w,Y(v));cx.stroke();cx.fillText(Math.round(v*100)+"%",L-4,Y(v)+3)});
  cx.textAlign="center";[0,30,60,90].forEach(t=>cx.fillText("T+"+t,Math.min(X(t),L+w-12),CH-3));
  const area=(idx,color,fill)=>{cx.beginPath();cx.moveTo(X(0),Y(0));cur.bel.forEach((b,t)=>cx.lineTo(X(t),Y(b[idx])));cx.lineTo(X(T),Y(0));cx.closePath();cx.fillStyle=fill;cx.fill();
    cx.beginPath();cur.bel.forEach((b,t)=>t?cx.lineTo(X(t),Y(b[idx])):cx.moveTo(X(t),Y(b[idx])));cx.strokeStyle=color;cx.lineWidth=1.8;cx.stroke()};
  area(0,K.ember,"rgba(255,107,44,.14)");area(1,K.water,"rgba(92,200,255,.12)");
  if(S.deploy!=null){cx.setLineDash([3,3]);cx.strokeStyle=K.water;cx.beginPath();cx.moveTo(X(S.deploy),Tp);cx.lineTo(X(S.deploy),Tp+h);cx.stroke();cx.setLineDash([])}
  cx.strokeStyle=K.fg;cx.lineWidth=1;cx.beginPath();cx.moveTo(X(S.t),Tp);cx.lineTo(X(S.t),Tp+h);cx.stroke();
  const ft=Math.min(T,Math.floor(S.t));cx.fillStyle=K.ember;cx.beginPath();cx.arc(X(ft),Y(cur.bel[ft][0]),3,0,7);cx.fill();
}
const sc=$('spark'),sx=sc.getContext('2d');let SW=0,SH=0;
function velAt(t){if(t<1)return 4;let n=0;for(const[,,k]of cur.ev[t])if(k===1)n++;return n*7+3}
function drawSpark(){if(!SW)return;const f=Math.min(T,Math.floor(S.t));sx.clearRect(0,0,SW,SH);const vals=[];for(let t=0;t<=f;t++)vals.push(velAt(t));
  const mxv=Math.max(30,...vals.map((v,i)=>i?(v+vals[i-1])/2:v));const X=t=>t/T*SW,Y=v=>SH-2-(v/mxv)*(SH-4);
  sx.beginPath();vals.forEach((v,t)=>{const vv=t?(v+vals[t-1])/2:v;t?sx.lineTo(X(t),Y(vv)):sx.moveTo(X(t),Y(vv))});sx.strokeStyle=K.ember;sx.lineWidth=1.5;sx.stroke()}

/* ---------- pipeline strip ---------- */
const pill=a=>document.querySelector(`.agent[data-agent="${a}"]`);
function setPill(a,state,text){const el=pill(a);if(!el)return;el.querySelector('.dot').className="dot"+(state?" "+state:"");if(text!=null)el.querySelector('small').textContent=text}
const STATUS_NOTE={cached:" · cached",fallback:" · fixture"};

async function startScenario(){
  if(RUN.src){RUN.src.close();RUN.src=null}
  Object.assign(RUN,{pend:{},applied:{},shown:{},active:true,pro:null,def:null,judge:null,drafted:false,scored:false,edDemo:null,ed:null,answers:null});
  Object.assign(S,{t:0,deploy:null,autoPause:true,edit:null,playing:true});
  cache.clear();refresh();setPlay();setApproved();
  Object.keys(RUN.tl).forEach(a=>setPill(a,"idle","Queued"));
  $('incId').textContent=`INCIDENT ${RUN.incId} · waiting for Scout`;$('incClaim').innerHTML="&nbsp;";
  $('evImg').src=RUN.imageUrl;renderEvidence();renderFramings();RUN.ed=null;renderRaw();renderOuts();
  $('startBtn').textContent="Restart scenario";postsEl.dataset.sig="";
  try{
    const {run_id}=await api('/api/pipeline/start',{});
    const src=new EventSource('/api/stream?run_id='+run_id);RUN.src=src;
    src.onmessage=e=>{const ev=JSON.parse(e.data);if(ev.agent==="pipeline"){toast("Pipeline error: "+ev.summary,6000);return}RUN.pend[ev.agent]=ev};
    src.addEventListener('end',()=>{src.close();if(RUN.src===src)RUN.src=null});
    src.onerror=()=>{if(RUN.src===src){src.close();RUN.src=null;if(Object.keys(RUN.pend).length<Object.keys(RUN.tl).length){toast("Lost the connection to the agents.",5000);RUN.active=false}}};
  }catch(err){toast("Couldn't start the agents: "+err.message,6000);RUN.active=false}
}

// Holds each result until the map clock reaches its minute, and holds the clock if a result is late.
function pipelineTick(){
  if(!RUN.active)return;let left=0;
  for(const[a,[st,done]]of Object.entries(RUN.tl)){
    if(RUN.applied[a])continue;left++;
    const ev=RUN.pend[a];
    if(ev&&S.t>=ev.sim_t){RUN.applied[a]=true;applyEvent(ev);continue}
    if(S.t>=st&&!RUN.shown[a]){RUN.shown[a]=true;setPill(a,"wait","Running…")}
    if(!ev&&S.playing&&S.t>done){S.t=done;$('scrub').value=S.t}
  }
  if(!left)RUN.active=false;
}

function applyEvent(ev){
  const p=ev.payload,note=STATUS_NOTE[ev.status]||"";
  switch(ev.agent){
    case"scout":RUN.claim=p.claim;$('incId').textContent=`INCIDENT ${p.incident_id} · cluster of ${p.post_count} posts`;$('incClaim').textContent=`"${p.claim}"`;break;
    case"prosecutor":RUN.pro=p;renderEvidence();break;
    case"defender":RUN.def=p;renderEvidence();break;
    case"judge":RUN.judge=p;renderEvidence();break;
    case"drafter":applyDrafter(p);break;
    case"society":applySociety(p);break;
    case"editor":RUN.edDemo=p;break;
    case"broadcaster":if(S.deploy==null)setPill("broadcaster","wait",ev.summary);return;
  }
  setPill(ev.agent,"",ev.summary+note);
}

/* ---------- feed ---------- */
const postsEl=$('posts');
function renderFeed(){
  const f=Math.floor(S.t);const items=[];
  if(S.deploy!=null&&f>=S.deploy){
    const posts=curPosts();
    (RUN.answers||[]).map((r,i)=>[r,i]).filter(([,i])=>f>=S.deploy+5+i).reverse().forEach(([r])=>
      items.push({cls:"fix",who:"@CountyComms_demo",meta:"reply to "+r.who,text:r.answer,stats:"auto-answered by Broadcaster"}));
    if(S.es&&posts.es)items.push({cls:"fix",who:"@CountyComms_demo",meta:"T+"+S.deploy+" · ES",text:posts.es,stats:"targeted: Escondido parent groups"});
    items.push({cls:"fix",who:"@CountyComms_demo",meta:"T+"+S.deploy+(S.edit?" · approved by voice":" · approved"),text:posts.en,stats:"broadcast · "+FR[S.fr].name.toLowerCase()});
  }
  POSTS.filter(p=>p.t<=f).slice().reverse().forEach(p=>items.push(p));
  const sig=items.map(p=>p.who+p.meta+p.text).join("|");if(sig===postsEl.dataset.sig)return;postsEl.dataset.sig=sig;
  postsEl.innerHTML=items.map(p=>`<article class="post ${esc(p.cls)}"><div class="who"><b>${esc(p.who)}</b><span>${esc(p.meta)}</span></div>${p.img?'<div class="thumb" aria-hidden="true"></div>':''}<p>${esc(p.text)}</p><div class="stats">${esc(p.stats)}</div></article>`).join("");
}

/* ---------- evidence ---------- */
const FULL_TAG={provenance:"match found",account:"account",weather:"weather",other:"context"};
function renderEvidence(){
  const pro=RUN.pro,def=RUN.def,j=RUN.judge;
  let boxes="";
  if(pro){
    for(const f of pro.findings){if(!f.box_2d)continue;const[y0,x0,y1,x1]=f.box_2d;
      boxes+=`<div class="box${y0<60?' in':''}" style="top:${y0/10}%;left:${x0/10}%;width:${(x1-x0)/10}%;height:${(y1-y0)/10}%"><span class="tag">${f.id}</span></div>`}
    const nb=pro.findings.find(f=>!f.box_2d);
    if(nb)boxes+=`<div class="box full in"><span class="tag">${nb.id} · ${esc(FULL_TAG[nb.category]||nb.category)}</span></div>`;
  }
  $('evBoxes').innerHTML=boxes;
  $('finds').innerHTML=pro?(pro.findings.map(f=>`<li><span class="tag">${f.id}</span><span>${esc(f.label)}</span></li>`).join("")||'<li class="empty">No red flags found in the image.</li>'):'<li class="empty">Waiting for the Prosecutor…</li>';
  const list=(x,who)=>x?(x.bullets.map(b=>`<li>${esc(b)}</li>`).join("")||'<li class="empty">No points.</li>'):`<li class="empty">Waiting for the ${who}…</li>`;
  $('proList').innerHTML=list(pro,"Prosecutor");$('defList').innerHTML=list(def,"Defender");
  const vcol=j?({False:K.ember,Misleading:K.ember,Unverified:K.warn,True:K.ok}[j.verdict]||K.ember):K.ember;
  $('vword').textContent=j?j.verdict:"–";$('vword').style.color=vcol;
  $('confPct').textContent=j?j.confidence+"%":"–";$('confBar').style.width=(j?j.confidence:0)+"%";$('confBar').style.background=vcol;
  $('miss').innerHTML=j?(j.missing.map((m,i)=>`<div><span>${esc(m.item)}</span><button class="btn sm" data-i="${i}">Draft ask</button></div>`).join("")||'<span class="empty">Nothing critical missing.</span>'):'<span class="empty">Waiting for the Judge…</span>';
  $('miss').querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>draftAsk(j.missing[+b.dataset.i],b));
}
async function draftAsk(m,btn){btn.disabled=true;const old=btn.textContent;btn.textContent="Drafting…";
  try{const d=await api('/api/draft_ask',{item:m.item,ask_target:m.ask_target});toast("Drafted: "+d.text,6000)}
  catch(err){toast("Couldn't draft that ask: "+err.message,5000)}finally{btn.disabled=false;btn.textContent=old}}
$('evImg').onerror=()=>{if($('evImg').src.endsWith(RUN.imageUrl)&&RUN.imageUrl){$('evImg').hidden=true;$('evSvg').hidden=false}};
$('evImg').onload=()=>{$('evImg').hidden=false;$('evSvg').hidden=true};

// Bring your own image: Prosecutor, Defender and Judge run live on it.
$('anBtn').onclick=()=>$('anFile').click();
$('anFile').onchange=async e=>{
  const file=e.target.files[0];e.target.value="";if(!file)return;
  const claim=prompt("What does the post claim?",RUN.claim||"");if(claim===null||!claim.trim())return;
  const prev={pro:RUN.pro,def:RUN.def,judge:RUN.judge,src:$('evImg').src};
  $('evImg').src=URL.createObjectURL(file);$('evBoxes').innerHTML="";$('photo').classList.add('busy');$('anBtn').disabled=true;$('evLabel').textContent="Analyzing…";
  const pills=["prosecutor","defender","judge"].map(a=>[a,pill(a).querySelector('.dot').className,pill(a).querySelector('small').textContent]);
  pills.forEach(([a])=>setPill(a,"wait","Running on your image…"));
  const fd=new FormData();fd.append('image',file);fd.append('claim',claim.trim());
  try{const d=await api('/api/analyze',fd);RUN.pro=d.prosecutor;RUN.def=d.defender;RUN.judge=d.judge;renderEvidence();
    setPill("prosecutor","",`${d.prosecutor.findings.length} red flags in image`);setPill("defender","",`${d.defender.bullets.length} supporting points`);
    setPill("judge","",`${d.judge.verdict} · ${d.judge.confidence}% confident`);toast("Gemini analyzed your image.")}
  catch(err){Object.assign(RUN,{pro:prev.pro,def:prev.def,judge:prev.judge});$('evImg').src=prev.src;renderEvidence();
    pills.forEach(([a,dc,txt])=>{pill(a).querySelector('.dot').className=dc;pill(a).querySelector('small').textContent=txt});toast(err.message,7000)}
  finally{$('photo').classList.remove('busy');$('anBtn').disabled=false;$('evLabel').textContent="Gemini vision"}
};

/* ---------- framings ---------- */
function applyDrafter(d){
  for(const f of d.framings){FR[f.key]=Object.assign(FR[f.key]||{p:[.15,.15,.15,.15,.15,.15],esMult:.25},{name:f.name,text:f.text_en,text_es:f.text_es})}
  RUN.drafted=true;renderFramings();renderOuts();
}
function applySociety(d){
  for(const s of d.framings){const f=FR[s.framing_key];if(!f)continue;
    const sc=[...s.scores].sort((a,b)=>a.group_id-b.group_id);
    f.p=sc.map(x=>clamp(.3*x.belief_drop,.03,.32));
    const esDrop=sc[1]?sc[1].belief_drop:0;f.esMult=esDrop>0?clamp(s.es_group_en_only_drop/esDrop,.1,1):1;
    const top=sc.reduce((a,b)=>b.belief_drop>a.belief_drop?b:a,sc[0]);f.reaction=top?top.reaction:"";f.reactGroup=top?top.group_id:0}
  cache.clear();RUN.scored=true;S.fr=simPick();refresh();renderFramings();renderOuts();
}
function framingAvg(f){const sc=f.p.map((p,c)=>c===1&&!S.es?p*f.esMult:p).map(v=>Math.round(v/.3*100));return{sc,avg:Math.round(sc.reduce((a,b)=>a+b)/sc.length)}}
function simPick(){let best="B",b=-1;for(const[k,f]of Object.entries(FR)){const{avg}=framingAvg(f);if(avg>b){b=avg;best=k}}return best}
function heatColor(v){const a=Math.max(.12,Math.min(1,v));return `rgba(92,200,255,${a.toFixed(2)})`}
function renderFramings(){
  const wrap=$('framings');
  if(!RUN.drafted){wrap.innerHTML='<p class="empty">Waiting for the Drafter and Society Sim…</p>';return}
  const pick=RUN.scored?simPick():null;
  wrap.innerHTML=Object.entries(FR).map(([k,f])=>{
    const{sc,avg}=framingAvg(f);
    const heat=RUN.scored?sc.map((s,c)=>`<span style="background:${heatColor(s/100)}" title="${esc(GROUPS[c])}: ${s}% drop">${s}</span>`).join(""):SHORT.map(()=>'<span class="na">–</span>').join("");
    return `<button class="fr" data-fr="${k}" aria-pressed="${S.fr===k}"><div class="fh"><b>${k} · ${esc(f.name)}</b>${k===pick?'<span class="pick">Sim pick</span>':''}</div>
    <q>${esc(f.text)}</q>
    <div class="heat">${heat}</div>
    <div class="heatkey">${SHORT.map(s=>`<span>${s}</span>`).join("")}</div>
    ${RUN.scored&&f.reaction?`<p class="react">${esc(SHORT[f.reactGroup])}: "${esc(f.reaction)}"</p>`:''}
    <div class="score"><span>Avg. belief drop</span><strong>${RUN.scored?avg+"%":"–"}</strong></div></button>`}).join("");
  wrap.querySelectorAll('.fr').forEach(b=>b.onclick=()=>{S.fr=b.dataset.fr;renderFramings();renderOuts();refresh();toast(`Map rerun with "${FR[S.fr].name}"`)});
}

/* ---------- editor ---------- */
// The officer's own edit wins while its framing is selected; otherwise show the drafted framing.
function curPosts(){if(S.edit&&S.edit.fr===S.fr)return S.edit;const f=FR[S.fr];return{en:f.text,es:f.text_es}}
function rawHTML(ed,n){
  if(!ed)return"&nbsp;";const raw=ed.raw.slice(0,n??ed.raw.length);const cls=new Array(raw.length).fill(0);
  for(const[a,b]of ed.filler_spans)for(let i=a;i<b&&i<raw.length;i++)cls[i]=1;
  for(const[a,b]of ed.command_spans)for(let i=a;i<b&&i<raw.length;i++)cls[i]=2;
  let html="",i=0;while(i<raw.length){let j=i;while(j<raw.length&&cls[j]===cls[i])j++;const t=esc(raw.slice(i,j));
    html+=cls[i]===1?`<span class="um">${t}</span>`:cls[i]===2?`<span class="cmd">${t}</span>`:t;i=j}
  return html||"&nbsp;"}
function renderRaw(n){$('raw').innerHTML=rawHTML(RUN.ed,n)}
function renderOuts(){
  const p=curPosts(),en=p.en||"",es=p.es||"";
  $('enOut').textContent=en||"Drafts appear after the Drafter runs.";$('enLen').textContent=en?en.length+"/280":"";
  $('esOut').textContent=es||"Spanish draft appears after the Drafter runs.";$('esLen').textContent=es?es.length+"/280":"";$('esCard').hidden=!S.es;
  const ce=RUN.drafted?"plaintext-only":"false";$('enOut').contentEditable=ce;$('esOut').contentEditable=ce}
const wave=$('wave');for(let i=0;i<34;i++)wave.appendChild(document.createElement('i'));
const bars=[...wave.children];
const waveLevel=m=>bars.forEach(b=>b.style.height=(15+Math.min(1,m*3)*Math.random()*85)+"%");
const waveReset=()=>bars.forEach(b=>b.style.height="20%");
let dictating=false;

// Types out the transcript, then applies the posts and the spoken commands.
function applyEditor(ed){
  if(dictating)return;dictating=true;RUN.ed=ed;$('outs').classList.add('dim');
  const total=ed.raw.length;let n=0;
  const step=()=>{n+=3;renderRaw(n);waveLevel(.6);
    if(n<total){setTimeout(step,reduce?0:28);return}
    waveReset();$('outs').classList.remove('dim');dictating=false;
    const it=ed.intent;
    if(it.framing_hint&&FR[it.framing_hint])S.fr=it.framing_hint;
    S.edit={fr:S.fr,en:ed.post_en,es:ed.post_es||FR[S.fr].text_es};
    if(it.languages.includes("es")&&!S.es){S.es=true;$('esBtn').setAttribute('aria-pressed',true)}
    renderOuts();renderFramings();refresh();
    toast(`Editor: ${1+(S.es&&S.edit.es?1:0)} clean posts drafted from your voice note`);
    if(it.action==="approve"&&S.deploy==null)approve();
  };
  step()}

// Hold to talk. Records 16 kHz mono WAV (Gemini and most speech APIs accept WAV; Chrome only records webm).
const rec={want:false,stream:null,ctx:null,src:null,node:null,chunks:[],t0:0};
async function recStart(){
  if(rec.want||dictating)return;rec.want=true;
  try{rec.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}})}
  catch{rec.want=false;toast("Mic is blocked. Use Replay demo dictation.",5000);return}
  if(!rec.want){rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;return}
  rec.ctx=new AudioContext();rec.src=rec.ctx.createMediaStreamSource(rec.stream);rec.node=rec.ctx.createScriptProcessor(4096,1,1);rec.chunks=[];
  rec.node.onaudioprocess=e=>{const d=e.inputBuffer.getChannelData(0);rec.chunks.push(new Float32Array(d));let m=0;for(let i=0;i<d.length;i+=32)m=Math.max(m,Math.abs(d[i]));waveLevel(m)};
  rec.src.connect(rec.node);rec.node.connect(rec.ctx.destination);rec.t0=performance.now();$('mic').classList.add('rec');
}
async function recStop(){
  if(!rec.want)return;rec.want=false;if(!rec.stream)return;
  const dur=performance.now()-rec.t0;rec.node.disconnect();rec.src.disconnect();rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;
  const rate=rec.ctx.sampleRate;await rec.ctx.close();$('mic').classList.remove('rec');waveReset();
  if(dur<500){toast("Hold the mic button while you talk.");return}
  sendVoice(encodeWav(rec.chunks,rate,16000));
}
function encodeWav(chunks,inRate,outRate){
  const len=chunks.reduce((a,c)=>a+c.length,0),data=new Float32Array(len);let o=0;for(const c of chunks){data.set(c,o);o+=c.length}
  const ratio=inRate/outRate,n=Math.floor(len/ratio),buf=new ArrayBuffer(44+n*2),v=new DataView(buf);
  const ws=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i))};
  ws(0,"RIFF");v.setUint32(4,36+n*2,true);ws(8,"WAVE");ws(12,"fmt ");v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,outRate,true);v.setUint32(28,outRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);ws(36,"data");v.setUint32(40,n*2,true);
  for(let i=0;i<n;i++){const a=Math.floor(i*ratio),b=Math.max(a+1,Math.min(len,Math.floor((i+1)*ratio)));let s=0;for(let j=a;j<b;j++)s+=data[j];s=clamp(s/(b-a),-1,1);v.setInt16(44+i*2,s<0?s*0x8000:s*0x7fff,true)}
  return new Blob([buf],{type:"audio/wav"})}
async function submitVoice(fd,source){
  if(!RUN.drafted){toast("Start the scenario first so there's a draft to edit.",5000);return false}
  $('raw').innerHTML='<span class="empty">Reading your note…</span>';$('outs').classList.add('dim');
  fd.append('framing_key',S.fr);fd.append('es',S.es);fd.append('source',source);
  setPill("editor","wait","Reading your note…");
  try{const ed=await api('/api/voice',fd);$('outs').classList.remove('dim');applyEditor(ed);
    setPill("editor","",`${1+(ed.post_es?1:0)} posts from voice · ${source==="voiskey"?"Voiskey":"mic"}`);return true}
  catch(err){$('outs').classList.remove('dim');renderRaw();setPill("editor","","Couldn't read that note");toast(err.message+" Try again or use Replay demo dictation.",7000);return false}
}
function sendVoice(blob){const fd=new FormData();fd.append('audio',blob,'voice.wav');submitVoice(fd,"mic")}

// Voiskey has no API: it types into whatever text field has focus. When it stops typing, send the note.
const dict=$('dict');let dictTimer;
async function sendDictation(){clearTimeout(dictTimer);const text=dict.value.trim();if(!text||dictating)return;
  dict.disabled=true;const fd=new FormData();fd.append('text',text);
  if(await submitVoice(fd,"voiskey"))dict.value="";dict.disabled=false}
dict.addEventListener('input',()=>{clearTimeout(dictTimer);dictTimer=setTimeout(sendDictation,1500)});
dict.addEventListener('keydown',e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendDictation()}});

// The posts are editable, so the officer can also dictate straight into them (Voiskey translation into the ES box).
['enOut','esOut'].forEach(id=>$(id).addEventListener('input',()=>{
  S.edit={fr:S.fr,en:$('enOut').textContent,es:$('esOut').textContent};
  $('enLen').textContent=S.edit.en.length+"/280";$('esLen').textContent=S.edit.es.length+"/280";postsEl.dataset.sig=""}));
const mic=$('mic');
mic.addEventListener('pointerdown',e=>{e.preventDefault();mic.setPointerCapture(e.pointerId);recStart()});
['pointerup','pointercancel'].forEach(t=>mic.addEventListener(t,recStop));
mic.addEventListener('keydown',e=>{if((e.key===" "||e.key==="Enter")&&!e.repeat){e.preventDefault();recStart()}});
mic.addEventListener('keyup',e=>{if(e.key===" "||e.key==="Enter")recStop()});
$('replayBtn').onclick=()=>{if(!RUN.edDemo){toast("The demo note loads with the Editor step. Start the scenario first.",5000);return}applyEditor(RUN.edDemo)};
$('esBtn').onclick=()=>{S.es=!S.es;$('esBtn').setAttribute('aria-pressed',S.es);renderOuts();renderFramings();refresh();toast(S.es?"Spanish post back on. Watch the Escondido group.":"Spanish post off. Watch the Escondido group burn.")};

/* ---------- approve ---------- */
function approve(){
  if(S.deploy!=null){S.deploy=null;RUN.answers=null;refresh();setApproved();toast("Broadcast pulled. Rumor runs unchecked.");return}
  if(!RUN.drafted){toast("No correction drafted yet. Start the scenario first.",4000);return}
  S.deploy=Math.max(2,Math.round(S.t));S.autoPause=false;$('whatif').value=S.deploy;refresh();setApproved();
  if(!reduce){S.playing=true;setPlay()}toast(`Approved at T+${S.deploy}. Correction is live.`);
  const p=curPosts(),key=S.fr;
  api('/api/broadcast',{framing_key:key,post_en:p.en,post_es:S.es?p.es:null})
    .then(d=>{if(S.deploy!=null&&S.fr===key){RUN.answers=d.replies;postsEl.dataset.sig=""}}).catch(()=>{});
}
function setApproved(){const on=S.deploy!=null;$('approve').textContent=on?"Pull broadcast":"Approve and broadcast";$('approve').classList.toggle('primary',!on);
  $('apNote').textContent=on?`Broadcast at T+${S.deploy} · Broadcaster answering replies`:"Nothing posts without your approval.";
  if(on)setPill("broadcaster","live",`Live since T+${S.deploy}`);else if(RUN.applied.broadcaster)setPill("broadcaster","wait","Waiting for approval");
  $('wLabel').textContent="T+"+(S.deploy??$('whatif').value);updateCF()}
$('approve').onclick=approve;$('approve2').onclick=approve;
$('whatif').oninput=e=>{S.deploy=+e.target.value;S.autoPause=false;refresh();setApproved()};

function updateCF(){const end=d=>Math.round(run(d,S.fr,S.es).bel[T][0]*100)+"%";const me=S.deploy??+$('whatif').value;
  $('cf10').textContent=end(10);$('cfMe').textContent=end(me);$('cfNo').textContent=end(null);$('cfMeK').textContent="T+"+me+(S.deploy==null?" (preview)":"")}

/* ---------- callout ---------- */
// Which community the rumor reaches next: the biggest jump in believers over the next 8 minutes if nobody corrects.
function nextGroup(f){const base=run(null,S.fr,S.es).frames,a=base[f],b=base[Math.min(T,f+8)];const d=new Array(C).fill(0);
  for(let i=0;i<N;i++){const was=a[i]===1||a[i]===2,now=b[i]===1||b[i]===2;if(now&&!was)d[g.cl[i]]++}return GROUPS[d.indexOf(Math.max(...d))]}
function calloutText(f){const j=RUN.judge;const v=j?`<b>Judge: ${esc(j.verdict.toLowerCase())}, ${j.confidence}% confident.</b> `:"";
  return `${v}Correction drafted${S.edit?" from your voice note":""}. The rumor is moving into the ${esc(nextGroup(f))} group next.`}

/* ---------- transport ---------- */
function setPlay(){$('play').textContent=S.playing?"❚❚":"▶";$('play').setAttribute('aria-label',S.playing?"Pause":"Play")}
$('play').onclick=()=>{if(!S.playing&&S.t>=T)S.t=0;S.playing=!S.playing;setPlay()};
$('scrub').oninput=e=>{S.t=+e.target.value;S.playing=false;setPlay()};
let lastInt=-1;
function fmtClock(t){const m=18+Math.floor(t);const h=7+Math.floor(m/60),mm=m%60;return `T+<b>${Math.floor(t)}</b> min · ${h}:${String(mm).padStart(2,"0")} PM`}
function tickUI(){const f=Math.min(T,Math.floor(S.t));if(f===lastInt)return;lastInt=f;
  const[b,c]=cur.bel[f];$('sBel').textContent=Math.round(b*100)+"%";$('sCor').textContent=Math.round(c*100)+"%";
  $('sRes').textContent=(Math.round(b*N*1850/100)*100).toLocaleString();
  $('vel').innerHTML=velAt(f)+"<small>posts/min</small>";$('clock').innerHTML=fmtClock(S.t);$('tLabel').textContent="T+"+f;
  const show=S.deploy==null&&f>=24&&!S.playing&&RUN.drafted;$('callout').hidden=!show;if(show)$('calloutText').innerHTML=calloutText(f);
  renderFeed();drawSpark()}

let last=performance.now();
function loop(now){const dt=now-last;last=now;
  if(S.playing){S.t=Math.min(T,S.t+dt/230);
    if(S.autoPause&&S.deploy==null&&S.t>=24){S.t=24;S.playing=false;S.autoPause=false;setPlay()}
    if(S.t>=T){S.playing=false;setPlay()}
    $('scrub').value=S.t}
  pipelineTick();tickUI();drawMap(now);drawChart();requestAnimationFrame(loop)}

/* ---------- toast + misc ---------- */
let tt;function toast(m,ms=2600){const el=$('toast');el.textContent=m;el.hidden=false;clearTimeout(tt);tt=setTimeout(()=>el.hidden=true,ms)}
$('startBtn').onclick=startScenario;

function resize(){[MW,MH]=fit(mc);[CW,CH]=fit(cc);[SW,SH]=fit(sc);lastInt=-1}
new ResizeObserver(resize).observe(document.querySelector('.mapbox'));
new ResizeObserver(resize).observe(cc);
renderEvidence();renderFramings();renderRaw();renderOuts();setPlay();setApproved();resize();updateCF();
$('scrub').value=S.t;requestAnimationFrame(loop);
if(document.fonts)document.fonts.ready.then(()=>{lastInt=-1});

api('/api/scenario').then(sc=>{
  POSTS=sc.posts;RUN.tl=sc.timeline;RUN.claim=sc.claim;RUN.incId=sc.incident_id;RUN.imageUrl=sc.image_url;
  $('evImg').src=sc.image_url;$('incId').textContent=`INCIDENT ${sc.incident_id} · waiting for Scout`;lastInt=-1;
}).catch(err=>toast("Backend not reachable: "+err.message,8000));
})();

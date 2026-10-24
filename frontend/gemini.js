/* Gemini evidence board and Voiskey editor, plugged into the Grok desk (app.js) through window.Firebreak.
   Gemini: verifies the viral photo when an episode starts and imports the result as the episode's evidence.
   Voiskey: speak-to-type into the dictation box; Gemini parses the note and loads the editor, then the copy
   is proposed. The officer still clicks Approve: the desk only applies an exact, hashed proposal. */
(()=>{
'use strict';
const F=window.Firebreak;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const css=getComputedStyle(document.documentElement),col=n=>css.getPropertyValue(n).trim();
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
const G={episode:null,verified:new Set(),upload:null,imageUrl:'/data/viral.png',ed:null,dictating:false};
const toast=m=>F.toast(m);

/* ---------- evidence board ---------- */
const FULL_TAG={provenance:'match found',account:'account',weather:'weather',other:'context'};
function list(items,who){return items?(items.map(b=>`<li>${esc(b)}</li>`).join('')||'<li class="empty">No points.</li>'):`<li class="empty">Waiting for the ${who}…</li>`;}
function asList(x){return x==null?null:Array.isArray(x)?x:[typeof x==='string'?x:JSON.stringify(x)];}
function render(v){
  if(v&&v.id!==G.episode){G.episode=v.id;G.upload=null;G.ed=null;renderRaw();}
  const u=G.upload,e=v?.evidence;
  // An uploaded image's analysis is shown instead of the episode evidence until the next episode.
  const pro=u?u.prosecutor:e,findings=(u?u.prosecutor.findings:e?.findings)||[];
  const img=u?u.url:G.imageUrl;if($('evImg').getAttribute('src')!==img)$('evImg').setAttribute('src',img);
  let boxes='';
  for(const f of findings){if(!f||!Array.isArray(f.box_2d))continue;const[y0,x0,y1,x1]=f.box_2d;
    boxes+=`<div class="box${y0<60?' in':''}" style="top:${y0/10}%;left:${x0/10}%;width:${(x1-x0)/10}%;height:${(y1-y0)/10}%"><span class="tag">${esc(f.id)}</span></div>`;}
  const nb=findings.find(f=>f&&typeof f==='object'&&!f.box_2d);
  if(nb)boxes+=`<div class="box full in"><span class="tag">${esc(nb.id)} · ${esc(FULL_TAG[nb.category]||nb.category)}</span></div>`;
  $('evBoxes').innerHTML=boxes;
  const facts=findings.length?findings:(e?.verified_facts||[]);
  $('findings').innerHTML=(u||e)?facts.map((f,i)=>`<li><span class="tag">${esc(f.id??i+1)}</span><span>${esc(f.label??f)}</span></li>`).join('')||'<li class="empty">No red flags found.</li>':'<li class="empty">Waiting for the Prosecutor…</li>';
  $('proList').innerHTML=list(u?u.prosecutor.bullets:asList(e?.prosecutor),'Prosecutor');
  $('defList').innerHTML=list(u?u.defender.bullets:asList(e?.defender),'Defender');
  const j=u?u.judge:e,verdict=j?.verdict,conf=j?.confidence;
  const vcol={False:col('--ember'),Misleading:col('--ember'),Unverified:col('--warn'),True:col('--ok')}[verdict]||col('--ember');
  $('verdict').textContent=verdict||'Awaiting';$('verdict').style.color=vcol;
  $('confidence').textContent=Number.isFinite(conf)?conf+'%':'–';$('confBar').style.width=(Number.isFinite(conf)?conf:0)+'%';$('confBar').style.background=vcol;
  $('reasoning').textContent=j?.reasoning||'';
  const missing=(u?u.judge.missing:e?.missing)||[];
  $('miss').innerHTML=missing.map((m,i)=>`<div><span>${esc(m.item)}</span><button class="btn sm" data-i="${i}">Draft ask</button></div>`).join('')||`<span class="empty">${j?'Nothing critical missing.':'Waiting for the Judge…'}</span>`;
  $('miss').querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>draftAsk(missing[+b.dataset.i],b));
  $('evidencePacket').textContent=e?JSON.stringify(e,null,2):'';
  $('evidenceStatus').textContent=u?'Live Gemini analysis of your image. It is shown here only and does not change the episode.'
    :!e?'Start an episode. Gemini verifies the viral photo automatically.'
    :e.source==='gemini'?`Gemini · ${e.model||'model'} · ${e.status==='cached'?'cached result':'live result'} · imported as this episode's evidence.`
    :e.source==='gemini-fixture'?'Gemini unavailable, showing Gemini sample findings. Check the key and quota, then run verification again.'
    :`${e.source||'Imported'} evidence (not from Gemini). Run Gemini verification to replace it.`;
  $('verifyGemini').disabled=!v||v.mode==='replay'||v.status==='running'||!!v.approval;
  autoVerify(v);
}

function autoVerify(v){
  // Once per episode, before approval: replaces the synthetic fixture packet or fills a live episode's empty evidence.
  if(!v||v.mode==='replay'||v.approval||v.status==='running'||G.verified.has(v.id))return;
  if(v.evidence&&v.evidence.source==='gemini')return;
  G.verified.add(v.id);setTimeout(verify,0);
}
function verify(){
  const v=F.S.view;if(!v)return;
  $('evLabel').textContent='Verifying…';$('photo').classList.add('busy');
  F.act(async()=>{try{const r=await F.api(`/gemini/episodes/${encodeURIComponent(v.id)}/evidence`,{});G.upload=null;F.setView(r.view);
    toast(r.status==='done'?'Gemini verified the photo live.':r.status==='cached'?'Gemini verification loaded from cache.':'Gemini unavailable: using sample findings.');}
    finally{$('evLabel').textContent='Gemini vision';$('photo').classList.remove('busy');}});
}
$('verifyGemini').onclick=()=>{G.upload=null;verify();};

async function draftAsk(m,btn){btn.disabled=true;const old=btn.textContent;btn.textContent='Drafting…';
  try{const d=await F.api('/draft_ask',{item:m.item,ask_target:m.ask_target});toast('Drafted: '+d.text);}
  catch(err){F.error(err);}finally{btn.disabled=false;btn.textContent=old;}}

// Bring your own image: the full Gemini debate runs live on it.
$('anBtn').onclick=()=>$('anFile').click();
$('anFile').onchange=async e=>{
  const file=e.target.files[0];e.target.value='';if(!file)return;
  const claim=prompt('What does the post claim?',F.S.view?.scout?.claim||$('claim').textContent||'');if(claim===null||!claim.trim())return;
  const url=URL.createObjectURL(file);$('evImg').setAttribute('src',url);$('evBoxes').innerHTML='';
  $('photo').classList.add('busy');$('anBtn').disabled=true;$('evLabel').textContent='Analyzing…';F.error(null);
  const fd=new FormData();fd.append('image',file);fd.append('claim',claim.trim());
  try{const r=await fetch('/api/analyze',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);
    G.upload={url,...d};render(F.S.view);toast('Gemini analyzed your image.');}
  catch(err){G.upload=null;render(F.S.view);F.error(err);}
  finally{$('photo').classList.remove('busy');$('anBtn').disabled=false;$('evLabel').textContent='Gemini vision';}
};

/* ---------- Voiskey editor ---------- */
function rawHTML(ed,n){
  if(!ed)return'&nbsp;';const raw=ed.raw.slice(0,n??ed.raw.length);const cls=new Array(raw.length).fill(0);
  for(const[a,b]of ed.filler_spans||[])for(let i=a;i<b&&i<raw.length;i++)cls[i]=1;
  for(const[a,b]of ed.command_spans||[])for(let i=a;i<b&&i<raw.length;i++)cls[i]=2;
  let html='',i=0;while(i<raw.length){let j=i;while(j<raw.length&&cls[j]===cls[i])j++;const t=esc(raw.slice(i,j));
    html+=cls[i]===1?`<span class="um">${t}</span>`:cls[i]===2?`<span class="cmd">${t}</span>`:t;i=j;}
  return html||'&nbsp;';}
function renderRaw(n){$('raw').innerHTML=rawHTML(G.ed,n);}
const wave=$('wave');for(let i=0;i<34;i++)wave.appendChild(document.createElement('i'));
const bars=[...wave.children];
const waveLevel=m=>bars.forEach(b=>b.style.height=(15+Math.min(1,m*3)*Math.random()*85)+'%');
const waveReset=()=>bars.forEach(b=>b.style.height='20%');

// The editor needs copy to rewrite: load the selected draft if the officer hasn't picked one yet.
function ensureCopy(){
  if($('enOut').value.trim())return true;
  const fs=F.S.view?.drafts?.framings||[];const f=fs.find(x=>x.key===F.S.selected)||fs[0];
  if(!f){F.error('Draft corrections first, then dictate.');return false;}
  F.loadEditor(f);return true;}

// Types out the transcript, loads the editor, and proposes the exact copy. Approval stays a click.
function applyEditor(ed){
  if(G.dictating)return;G.dictating=true;G.ed=ed;const total=ed.raw.length;let n=0;
  const step=()=>{n+=3;renderRaw(n);waveLevel(.6);
    if(n<total){setTimeout(step,reduce?0:24);return;}
    waveReset();G.dictating=false;
    const it=ed.intent,es=(it.languages||[]).includes('es');
    F.loadEditor({framing_key:it.framing_hint||F.S.selected,text_en:ed.post_en,text_es:es?(ed.post_es||''):'',
      ...(ed.target_groups?.length?{target_groups:ed.target_groups}:{})});
    const v=F.S.view;
    if(v&&!v.approval&&v.status!=='running'){F.propose();
      toast(it.action==='approve'?'You said publish. Review the exact copy, then click Approve intervention.':'Copy updated and proposed. Review it, then approve.');}
    else toast('Copy updated in the editor.');
  };step();}

async function submitVoice(fd,source){
  if(!ensureCopy())return false;
  fd.append('framing_key',F.S.selected);fd.append('text_en',$('enOut').value);fd.append('text_es',$('esOut').value);
  fd.append('es','true');fd.append('source',source);
  $('raw').innerHTML='<span class="empty">Reading your note…</span>';F.error(null);
  try{const r=await fetch('/api/voice',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||`HTTP ${r.status}`);applyEditor(d);return true;}
  catch(err){renderRaw();F.error(err.message+' Try again or use Replay demo dictation.');return false;}
}

// Voiskey has no API: it types into the focused text box. When it stops typing, send the note.
const dict=$('dict');let dictTimer;
async function sendDictation(){clearTimeout(dictTimer);const text=dict.value.trim();if(!text||G.dictating)return;
  dict.disabled=true;const fd=new FormData();fd.append('text',text);
  if(await submitVoice(fd,'voiskey'))dict.value='';dict.disabled=false;}
dict.addEventListener('input',()=>{clearTimeout(dictTimer);dictTimer=setTimeout(sendDictation,1500);});
dict.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendDictation();}});

// Backup: hold the mic. Records 16 kHz mono WAV, which Gemini transcribes.
const rec={want:false,stream:null,ctx:null,src:null,node:null,chunks:[],t0:0};
async function recStart(){
  if(rec.want||G.dictating)return;rec.want=true;
  try{rec.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});}
  catch{rec.want=false;F.error('Mic is blocked. Use Voiskey dictation or Replay demo dictation.');return;}
  if(!rec.want){rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;return;}
  rec.ctx=new AudioContext();rec.src=rec.ctx.createMediaStreamSource(rec.stream);rec.node=rec.ctx.createScriptProcessor(4096,1,1);rec.chunks=[];
  rec.node.onaudioprocess=e=>{const d=e.inputBuffer.getChannelData(0);rec.chunks.push(new Float32Array(d));let m=0;for(let i=0;i<d.length;i+=32)m=Math.max(m,Math.abs(d[i]));waveLevel(m);};
  rec.src.connect(rec.node);rec.node.connect(rec.ctx.destination);rec.t0=performance.now();$('mic').classList.add('rec');}
async function recStop(){
  if(!rec.want)return;rec.want=false;if(!rec.stream)return;
  const dur=performance.now()-rec.t0;rec.node.disconnect();rec.src.disconnect();rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;
  const rate=rec.ctx.sampleRate;await rec.ctx.close();$('mic').classList.remove('rec');waveReset();
  if(dur<500){toast('Hold the mic button while you talk.');return;}
  const fd=new FormData();fd.append('audio',encodeWav(rec.chunks,rate,16000),'voice.wav');submitVoice(fd,'mic');}
function encodeWav(chunks,inRate,outRate){
  const len=chunks.reduce((a,c)=>a+c.length,0),data=new Float32Array(len);let o=0;for(const c of chunks){data.set(c,o);o+=c.length;}
  const ratio=inRate/outRate,n=Math.floor(len/ratio),buf=new ArrayBuffer(44+n*2),v=new DataView(buf);
  const ws=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i));};
  ws(0,'RIFF');v.setUint32(4,36+n*2,true);ws(8,'WAVE');ws(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,outRate,true);v.setUint32(28,outRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);ws(36,'data');v.setUint32(40,n*2,true);
  for(let i=0;i<n;i++){const a=Math.floor(i*ratio),b=Math.max(a+1,Math.min(len,Math.floor((i+1)*ratio)));let s=0;for(let j=a;j<b;j++)s+=data[j];s=Math.max(-1,Math.min(1,s/(b-a)));v.setInt16(44+i*2,s<0?s*0x8000:s*0x7fff,true);}
  return new Blob([buf],{type:'audio/wav'});}
const mic=$('mic');
mic.addEventListener('pointerdown',e=>{e.preventDefault();mic.setPointerCapture(e.pointerId);recStart();});
['pointerup','pointercancel'].forEach(t=>mic.addEventListener(t,recStop));
mic.addEventListener('keydown',e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat){e.preventDefault();recStart();}});
mic.addEventListener('keyup',e=>{if(e.key===' '||e.key==='Enter')recStop();});

// Loud room fallback: a recorded note from data/gemini_fixtures.
$('replayBtn').onclick=async()=>{if(!ensureCopy())return;try{applyEditor(await (await fetch('/data/gemini_fixtures/editor_demo.json')).json());}catch(err){F.error(err);}};

fetch('/api/scenario').then(r=>r.json()).then(d=>{const img=(d.scenario||d).image;if(img){G.imageUrl='/data/'+img;render(F.S.view);}}).catch(()=>{});
window.FBGemini={render};
render(F.S.view);
})();

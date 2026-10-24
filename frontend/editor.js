/* Editor: the officer shapes the correction by voice or by hand, then approves the exact text.
   Voiskey has no API: it types into the focused box (hold Right Alt), and the note goes to Gemini once it stops.
   The mic is a backup (Gemini transcribes a WAV). Voice never approves: the desk only applies a hashed proposal. */
(()=>{
'use strict';
const FB=window.FB,$=FB.$,S=FB.S,esc=FB.esc;
const D={note:null,typing:false,timer:null};
const NAMES=['Poway residents','Escondido parents (ES)','Local influencers','Retirees on Facebook','Reporters','Skeptics'];

/* ---------- copy and targets ---------- */
function targets(){return[...$('targets').querySelectorAll('.chip[aria-pressed=true]')].map(b=>+b.dataset.g);}
function setTargets(ids){for(const b of $('targets').querySelectorAll('.chip'))b.setAttribute('aria-pressed',String(ids.includes(+b.dataset.g)));}
function counts(){for(const[id,out]of[['enOut','enLen'],['esOut','esLen']]){const n=$(id).value.length;$(out).textContent=`${n}/280`;$(out).classList.toggle('over',n>270);}}
function flash(ids){if(FB.reduced())return;for(const id of ids){const n=$(id);n.classList.remove('changed');void n.offsetWidth;n.classList.add('changed');}}
function loadEditor(f,flashIt=true){
  $('enOut').value=f.text_en||f.text||'';$('esOut').value=f.text_es||'';
  if(f.key||f.framing_key)S.selected=f.key||f.framing_key;
  if(Array.isArray(f.target_groups)&&f.target_groups.length)setTargets(f.target_groups.map(Number));
  S.dirty=true;counts();if(flashIt)flash(['enOut','esOut']);FB.render();}
FB.loadEditor=loadEditor;
FB.intervention=()=>({text_en:$('enOut').value,text_es:$('esOut').value,target_groups:targets(),framing_key:S.selected});
FB.resetEditor=()=>{$('enOut').value='';$('esOut').value='';$('raw').hidden=true;$('dict').value='';S.dirty=false;S.local.edited=false;setTargets([0,1,2,3,4,5]);counts();};
for(const id of['enOut','esOut'])$(id).addEventListener('input',()=>{S.dirty=true;counts();FB.render();});
$('targets').innerHTML=NAMES.map((n,g)=>`<button type="button" class="chip" data-g="${g}" aria-pressed="true">${esc(n.replace(' (ES)',''))}</button>`).join('');
$('targets').addEventListener('click',e=>{const b=e.target.closest('.chip');if(!b||b.disabled)return;b.setAttribute('aria-pressed',String(b.getAttribute('aria-pressed')!=='true'));S.dirty=true;FB.render();});

/* ---------- approve ---------- */
// Propose the exact copy on screen, then approve that revision. Both steps happen on one click.
FB.approve=()=>FB.act(async()=>{
  if(!targets().length)throw new Error('Pick at least one community to send the correction to.');
  let v=S.view;const p=v.pending_intervention,want=FB.intervention();
  const same=p&&!S.dirty&&p.text_en===want.text_en&&(p.text_es||'')===(want.text_es||'');
  if(!same){v=await FB.api(`/episodes/${encodeURIComponent(v.id)}/intervention`,want);S.dirty=false;}
  const q=v.pending_intervention;
  v=await FB.api(`/episodes/${encodeURIComponent(v.id)}/approve`,{revision:q.revision,content_hash:q.content_hash});
  FB.setView(v);FB.toast(`Correction sent to ${want.target_groups.length===6?'all six communities':want.target_groups.length+' communities'}.`);
},'Sending…');
$('approve').onclick=()=>FB.approve();

/* ---------- voice ---------- */
function rawHTML(ed,n){
  const raw=ed.raw.slice(0,n??ed.raw.length),cls=new Array(raw.length).fill(0);
  for(const[a,b]of ed.filler_spans||[])for(let i=a;i<b&&i<raw.length;i++)cls[i]=1;
  for(const[a,b]of ed.command_spans||[])for(let i=a;i<b&&i<raw.length;i++)cls[i]=2;
  let h='',i=0;while(i<raw.length){let j=i;while(j<raw.length&&cls[j]===cls[i])j++;const t=esc(raw.slice(i,j));h+=cls[i]===1?`<span class="um">${t}</span>`:cls[i]===2?`<span class="cmd">${t}</span>`:t;i=j;}
  return h;}
function ensureCopy(){
  if($('enOut').value.trim())return true;
  const fs=S.view?.drafts?.framings||[],f=fs.find(x=>x.key===S.selected)||fs[0];
  if(!f){FB.alert('Draft the corrections first, then record your note.');return false;}
  loadEditor(f,false);return true;}
function applyNote(ed){
  D.typing=true;const raw=$('raw');raw.hidden=false;let n=0;const total=ed.raw.length;
  const done=()=>{
    raw.innerHTML=rawHTML(ed);D.typing=false;S.local.editing=false;
    const it=ed.intent,es=(it.languages||[]).includes('es');
    loadEditor({framing_key:it.framing_hint||S.selected,text_en:ed.post_en,text_es:es?(ed.post_es||''):'',target_groups:ed.target_groups});
    S.local.edited=true;FB.render();
    if(S.view?.round===2&&!S.view.approval){$('approve').classList.remove('ready');void $('approve').offsetWidth;$('approve').classList.add('ready');}
    FB.toast(it.action==='approve'?'Your note updated the copy. Review it, then approve.':'Your note updated the copy.');};
  if(FB.reduced()){done();return;}
  const step=()=>{n+=4;raw.innerHTML=rawHTML(ed,n);if(n<total)setTimeout(step,18);else done();};step();}
async function sendNote(fd,source){
  if(D.typing||!ensureCopy())return false;
  fd.append('framing_key',S.selected);fd.append('text_en',$('enOut').value);fd.append('text_es',$('esOut').value);fd.append('es','true');fd.append('source',source);
  S.local.editing=true;FB.alert(null);$('raw').hidden=false;$('raw').textContent='Reading your note…';FB.render();
  try{applyNote(await FB.api('/voice',fd));return true;}
  catch(e){S.local.editing=false;$('raw').hidden=true;FB.render();FB.alert(e.message+' Try again, or play the sample note.');return false;}}

// Voiskey types into this box. When it stops for 1.5 seconds, send the note.
const dict=$('dict');
async function sendDictation(){
  clearTimeout(D.timer);dict.classList.remove('listening');const text=dict.value.trim();if(!text)return;
  dict.disabled=true;const fd=new FormData();fd.append('text',text);
  if(await sendNote(fd,'voiskey'))dict.value='';dict.disabled=false;}
dict.addEventListener('input',()=>{dict.classList.add('listening');clearTimeout(D.timer);D.timer=setTimeout(sendDictation,1500);});
dict.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendDictation();}});

// Backup: hold the mic. Records 16 kHz mono WAV.
const rec={want:false,stream:null,ctx:null,src:null,node:null,chunks:[],t0:0};
async function recStart(){
  if(rec.want||D.typing)return;rec.want=true;
  try{rec.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});}
  catch{rec.want=false;FB.alert('The microphone is blocked. Use Voiskey in the note box, or play the sample note.');return;}
  if(!rec.want){rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;return;}
  rec.ctx=new AudioContext();rec.src=rec.ctx.createMediaStreamSource(rec.stream);rec.node=rec.ctx.createScriptProcessor(4096,1,1);rec.chunks=[];
  rec.node.onaudioprocess=e=>rec.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  rec.src.connect(rec.node);rec.node.connect(rec.ctx.destination);rec.t0=performance.now();$('mic').classList.add('rec');}
async function recStop(){
  if(!rec.want)return;rec.want=false;if(!rec.stream)return;
  const dur=performance.now()-rec.t0;rec.node.disconnect();rec.src.disconnect();rec.stream.getTracks().forEach(t=>t.stop());rec.stream=null;
  const rate=rec.ctx.sampleRate;await rec.ctx.close();$('mic').classList.remove('rec');
  if(dur<500){FB.toast('Hold the mic button while you talk.');return;}
  const fd=new FormData();fd.append('audio',wav(rec.chunks,rate,16000),'note.wav');sendNote(fd,'mic');}
function wav(chunks,inRate,outRate){
  const len=chunks.reduce((a,c)=>a+c.length,0),data=new Float32Array(len);let o=0;for(const c of chunks){data.set(c,o);o+=c.length;}
  const ratio=inRate/outRate,n=Math.floor(len/ratio),buf=new ArrayBuffer(44+n*2),v=new DataView(buf),ws=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i));};
  ws(0,'RIFF');v.setUint32(4,36+n*2,true);ws(8,'WAVE');ws(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,outRate,true);v.setUint32(28,outRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);ws(36,'data');v.setUint32(40,n*2,true);
  for(let i=0;i<n;i++){const a=Math.floor(i*ratio),b=Math.max(a+1,Math.min(len,Math.floor((i+1)*ratio)));let s=0;for(let j=a;j<b;j++)s+=data[j];s=Math.max(-1,Math.min(1,s/(b-a)));v.setInt16(44+i*2,s<0?s*0x8000:s*0x7fff,true);}
  return new Blob([buf],{type:'audio/wav'});}
const mic=$('mic');
mic.addEventListener('pointerdown',e=>{e.preventDefault();mic.setPointerCapture(e.pointerId);recStart();});
['pointerup','pointercancel'].forEach(t=>mic.addEventListener(t,recStop));
mic.addEventListener('keydown',e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat){e.preventDefault();recStart();}});
mic.addEventListener('keyup',e=>{if(e.key===' '||e.key==='Enter')recStop();});
$('replayBtn').onclick=async()=>{if(D.typing||!ensureCopy())return;try{applyNote(await (await fetch('/data/gemini_fixtures/editor_demo.json')).json());}catch(e){FB.alert(e.message);}};
$('importVoice').onclick=()=>{try{const v=JSON.parse($('voiceInput').value);if(typeof v.text_en!=='string')throw new Error('The JSON needs a text_en string.');loadEditor(v);FB.toast('Copy loaded into the editor.');}catch(e){FB.alert(e.message);}};

/* ---------- from server view ---------- */
FB.renderers.push(v=>{
  const replay=v?.mode==='replay',sent=!!v?.approval,lock=!v||sent||replay||S.busy;
  if(v&&replay&&v.recorded_intervention&&!$('enOut').value){const r=v.recorded_intervention;loadEditor({...r,key:r.framing_key},false);S.dirty=false;}
  else if(v?.pending_intervention&&!S.dirty&&!$('enOut').value){loadEditor({...v.pending_intervention,key:v.pending_intervention.framing_key},false);S.dirty=false;}
  for(const id of['enOut','esOut','dict'])$(id).disabled=lock;
  $('mic').disabled=lock;$('replayBtn').disabled=lock;
  for(const b of $('targets').querySelectorAll('.chip'))b.disabled=lock;
  const ready=!!v&&v.round===2&&v.status==='awaiting_approval'&&!sent&&!S.busy&&!!$('enOut').value.trim();
  $('approve').disabled=!ready;$('approve').textContent=sent?'Sent':'Approve and send';
  $('apNote').textContent=sent?`Sent at T+20 to ${v.interventions?.slice(-1)[0]?.target_groups?.length??targets().length} communities. Copy is locked for this run.`
    :!v?'Start an episode to write a correction.':v.round<2?'You can approve at round 2, once the rumor has spread.':replay?'This saved run replays its recorded correction. Approve it to continue.'
    :'You approve the exact text shown. Nothing posts outside this exercise.';
});
})();

/* Firebreak desk core: server state, the guided next-step button, agent rail, feed, corrections, details drawer.
   map.js, evidence.js and editor.js register their own renderers on window.FB. All episode state lives on the
   server (backend/society_service.py); this file only renders it and calls its endpoints. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const motion=matchMedia('(prefers-reduced-motion: reduce)');
const S={view:null,health:null,scenario:null,busy:false,busyLabel:'',selected:'B',dirty:false,source:null,local:{},recordings:[]};
const AGENTS=[['scout','Scout','grok'],['prosecutor','Prosecutor','gemini'],['defender','Defender','gemini'],['judge','Judge','gemini'],
  ['drafter','Drafter','grok'],['society','Town Bots','grok'],['editor','Editor','voiskey'],['broadcaster','Broadcaster','grok']];
const SPONSOR={grok:'Grok',gemini:'Gemini',voiskey:'Voiskey'};
// Links read better as a domain on screen. The exact text still goes to the server.
const shortLinks=s=>String(s??'').replace(/https?:\/\/(?:www\.)?([a-z0-9.-]+)\/?/gi,(m,h)=>h.replace(/^readysandiego\.org$/i,'ReadySanDiego.org'));

const FB=window.FB={S,$,esc,shortLinks,renderers:[],reduced:()=>motion.matches,api,act,setView,toast,alert:showAlert,refresh,selectFraming};

/* ---------- server ---------- */
async function api(path,body){
  const opt=body instanceof FormData?{method:'POST',body}:body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{};
  const r=await fetch('/api'+path,opt);let d=null;try{d=await r.json();}catch{}
  if(!r.ok){const detail=d?.detail??d?.error;const e=new Error(typeof detail==='string'?detail:Array.isArray(detail)?detail.map(x=>x.msg||x).join('; '):`The server returned ${r.status}.`);e.status=r.status;throw e;}
  return d;}
const ep=suffix=>`/episodes/${encodeURIComponent(S.view.id)}${suffix}`;
async function act(fn,label){
  if(S.busy)return;S.busy=true;S.busyLabel=label||'Working…';showAlert(null);render();
  try{await fn();}catch(e){showAlert(e.message||String(e));$('auto').checked=false;}
  finally{S.busy=false;S.busyLabel='';render();scheduleAuto();}}
function setView(v){
  if(!v||!v.id)return;
  try{localStorage.setItem('firebreak.episodeId',v.id);}catch{}
  try{const u=new URL(location.href);u.searchParams.set('episode',v.id);history.replaceState(null,'',u.pathname+u.search);}catch{}
  if(S.view?.id!==v.id)S.dirty=false;
  S.view=v;render();scheduleAuto();}
async function refresh(){if(!S.view)return;try{setView(await api(ep('')));}catch(e){if(e.status===404)forget();}}
function connect(){
  if(S.source)S.source.close();
  S.source=new EventSource(`/api/episodes/${encodeURIComponent(S.view.id)}/events`);
  S.source.addEventListener('snapshot',e=>{try{const v=JSON.parse(e.data);if(v.id===S.view?.id&&v.version!==S.view.version)setView(v);}catch{}});}
function forget(){try{localStorage.removeItem('firebreak.episodeId');}catch{}S.view=null;render();}
setInterval(()=>{if(S.view?.status==='running')refresh();},4000);

/* ---------- toasts and alerts ---------- */
function toast(text){
  const t=document.createElement('div');t.className='toast';t.textContent=text;$('toasts').append(t);
  setTimeout(()=>{t.classList.add('out');setTimeout(()=>t.remove(),180);},3800);}
function showAlert(text){$('alert').hidden=!text;$('alertText').textContent=text||'';}
$('alertClose').onclick=()=>showAlert(null);

/* ---------- the guided next step ---------- */
// One button walks the whole demo. Each step names exactly what it does.
function nextStep(){
  const v=S.view;
  if(S.busy)return{label:S.busyLabel,disabled:true};
  if(!v)return{label:'Start episode',run:start,guide:'Start an episode. A rumor about the I-15 fire is about to spread.'};
  const replay=v.mode==='replay';
  if(v.status==='error')return{label:'Start new episode',run:start,guide:'This run stopped. Start a new episode to try again.'};
  if(v.status==='running')return{label:v.mode==='live'?'Grok Bots are deciding…':'Working…',disabled:true,
    guide:v.mode==='live'?'The six community Bots are deciding what to do. A round takes about a minute.':'Working…'};
  if(!replay&&S.local.verifying)return{label:'Gemini is checking…',disabled:true,guide:'Gemini is checking the viral photo. The Prosecutor and Defender argue, then the Judge rules.'};
  if(!replay&&!v.evidence)return{label:'Check the photo',run:()=>FB.verify(),guide:'Have Gemini check the photo before writing a correction.'};
  if(!v.drafts)return{label:'Draft corrections',run:draft,guide:`Gemini ruled the post ${String(v.evidence?.verdict||'unverified').toLowerCase()}. Next, Grok drafts three corrections in English and Spanish.`};
  if(v.round<2)return{label:`Run round ${v.round+1}`,run:advance,guide:v.round===0?'Watch the rumor move through the town. Each round is 10 minutes.':'The rumor is spreading. One more round before you decide.'};
  if(v.round===2&&v.status==='awaiting_approval'){
    if(!$('enOut').value.trim())return{label:'Use the selected correction',run:()=>selectFraming(S.selected,true),guide:'Decision point. Pick a correction, or hold Right Alt over the Editor and say what to change.'};
    return{label:'Approve and send',run:()=>FB.approve(),attn:true,guide:'Review the exact text in the Editor, then approve it. It goes to the communities you picked.'};}
  if(v.round<4)return{label:`Run round ${v.round+1}`,run:advance,guide:v.approval?'The correction is out. Watch who accepts it and who passes it on.':'Running without a correction.'};
  if(v.approval&&!replay&&v.broadcast?.status!=='done')return{label:'Answer replies',run:replies,guide:'Residents are asking questions. Have the Broadcaster answer them.'};
  return{label:'Start new episode',run:start,guide:'Done. Open Details to save this run or fork a what-if branch.'};}

function renderCta(){
  const n=nextStep(),b=$('cta');
  b.textContent=n.label;b.disabled=!!n.disabled;b.onclick=n.run?()=>n.run():null;
  b.classList.toggle('attn',!!n.attn&&!S.busy);
  if(n.guide)$('guide').textContent=n.guide;}

async function start(){
  const mode=$('mode').value;
  if(mode==='replay'&&!$('recordings').value){showAlert('Pick a saved run first.');return;}
  await act(async()=>{
    S.local={};S.selected='B';FB.resetEditor?.();
    setView(await api('/episodes',{mode,...(mode==='replay'?{recording_id:$('recordings').value}:{})}));connect();
  },'Starting…');}
const draft=()=>act(async()=>setView(await api(ep('/drafts'),{})),'Drafting…');
const advance=()=>act(async()=>setView(await api(ep('/advance'),{})),'Running the round…');
function replies(){
  return act(async()=>{
    const raw=$('questionsInput').value.trim();let body={};
    if(raw){const p=JSON.parse(raw);body=Array.isArray(p)?{questions:p}:p;}
    // Fixture personas rarely ask questions; fall back to the scenario's scripted ones.
    else if(!(S.view.feed||[]).some(p=>p.kind==='question'||p.kind==='reply')&&S.scenario?.replies?.length)body={questions:S.scenario.replies};
    setView(await api(ep('/replies'),body));
  },'Answering…');}
function scheduleAuto(){
  clearTimeout(S.autoTimer);const v=S.view;
  if($('auto').checked&&!S.busy&&v?.status==='ready'&&v.round!==2)S.autoTimer=setTimeout(advance,700);}

/* ---------- agent rail ---------- */
function renderRail(){
  const by=Object.fromEntries((S.view?.pipeline||[]).map(p=>[p.agent,p]));
  const rail=$('rail');
  if(!rail.children.length)rail.innerHTML=AGENTS.map(([k,n,s])=>`<li data-agent="${k}" data-sponsor="${s}"><span class="name"><i class="dot"></i>${n}</span><span class="who">${SPONSOR[s]}</span></li>`).join('');
  for(const li of rail.children){
    const k=li.dataset.agent,p=by[k];
    let st=p?.status||'waiting';
    if(S.local.verifying&&['prosecutor','defender','judge'].includes(k))st='running';
    if(S.local.editing&&k==='editor')st='running';
    if(k==='editor'&&st==='ready')st=S.local.edited?'done':'waiting';
    li.dataset.state=['done','running','error'].includes(st)?st:'waiting';li.title=p?.summary||'';}}

/* ---------- feed ---------- */
const shown=new Set();
function renderFeed(){
  const v=S.view,list=$('posts'),scout=v?.scout;
  $('claim').textContent=scout?.claim||S.scenario?.claim||'Waiting for the scenario…';
  $('incidentMeta').textContent=scout?`Scout grouped ${scout.post_count} posts in ${(scout.languages||[]).map(l=>({en:'English',es:'Spanish'}[l]||l)).join(' and ')}.`:'Scout groups matching posts into one incident.';
  const items=(v?.feed||[]).map(p=>({id:p.id,who:p.who||'Resident',text:p.text,meta:`${p.language==='es'?'ES  ':''}T+${(p.round||0)*10}`,
    cls:/correction|retract/.test(p.kind)||p.who==='@CountyComms_demo'?'fix':p.kind==='question'?'ask':''}));
  const ask=Object.fromEntries([...(v?.feed||[]),...(S.scenario?.replies||[])].map(p=>[p.id,p]));
  for(const r of v?.broadcast?.replies||[])items.push({id:'reply-'+r.question_id,who:'@CountyComms_demo',cls:'fix',text:r.text,meta:'Reply',q:ask[r.question_id]?.text});
  if(!items.length){shown.clear();list.innerHTML='<li class="empty">Posts appear as the rumor spreads.</li>';return;}
  items.reverse();const first=!shown.size;
  list.innerHTML=items.map(p=>`<li class="post ${p.cls}${!first&&!shown.has(p.id)?' enter':''}"><div class="who"><b>${esc(p.who)}</b><span>${esc(p.meta)}</span></div>${p.q?`<p class="q">${esc(p.q)}</p>`:''}<p>${esc(shortLinks(p.text))}</p></li>`).join('');
  items.forEach(p=>shown.add(p.id));}

/* ---------- corrections ---------- */
let draftsSeen=false;
function renderLab(){
  const fs=S.view?.drafts?.framings||[],wrap=$('framings');
  if(!fs.length){draftsSeen=false;wrap.innerHTML=`<p class="empty">${S.view?.evidence?'Grok drafts three corrections when you ask.':'Corrections are drafted after Gemini checks the photo.'}</p>`;return;}
  const locked=!!S.view.approval||S.view.mode==='replay';
  wrap.innerHTML=fs.map((f,i)=>`<button class="fr${draftsSeen?'':' enter'}" style="animation-delay:${draftsSeen?0:i*80}ms" data-key="${f.key}" aria-pressed="${S.selected===f.key}"${locked?' disabled':''}>
    <span class="fh"><b>${esc(f.name)}</b>${S.selected===f.key&&$('enOut').value.trim()?'<span>In the editor</span>':''}</span>
    <q>${esc(shortLinks(f.text_en))}</q>${f.text_es?`<span class="es">${esc(shortLinks(f.text_es))}</span>`:''}</button>`).join('');
  draftsSeen=true;
  wrap.querySelectorAll('.fr').forEach(b=>b.onclick=()=>selectFraming(b.dataset.key,true));}
function selectFraming(key,load){
  S.selected=key;const f=(S.view?.drafts?.framings||[]).find(x=>x.key===key);
  if(f&&load)FB.loadEditor?.(f);render();}

/* ---------- details drawer ---------- */
function openDrawer(open){
  const d=$('drawer');$('moreBtn').setAttribute('aria-expanded',String(open));
  if(open){d.hidden=false;d.classList.add('opening');requestAnimationFrame(()=>requestAnimationFrame(()=>d.classList.remove('opening')));}
  else{d.classList.add('closing');setTimeout(()=>{d.hidden=true;d.classList.remove('closing');},200);}}
$('moreBtn').onclick=()=>openDrawer($('drawer').hidden);
$('drawerClose').onclick=()=>openDrawer(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('drawer').hidden)openDrawer(false);});
function renderDrawer(){
  const v=S.view,h=S.health;
  $('dStatus').textContent=v?`${{fixture:'Simulated town',live:'Live Grok Bots',replay:'Saved run'}[v.mode]}, round ${v.round} of 4, ${v.status.replace('_',' ')}${v.pending_jobs?.length?`, ${v.pending_jobs.length} Bot jobs pending`:''}. Episode ${v.id.slice(0,8)}.`:'No episode yet.';
  if(h){const n=(h.bots?.groups||[]).filter(Boolean).length;$('dBots').textContent=`Grok Bots: ${n} of 6 communities set up, Comms ${h.bots?.comms?'set up':'missing'}, callback ${h.callback_ready?'set':'missing'}.`;}
  const writable=!!v&&!S.busy&&v.mode!=='replay'&&v.status!=='running';
  $('branchNone').disabled=!writable||v.round<2;$('branchCorrection').disabled=!writable||v.round<2||!$('enOut').value.trim();
  $('branches').disabled=!v||S.busy||v.status==='running';
  $('branches').innerHTML=(v?.branches||[]).map(b=>`<option value="${esc(b.branch_id)}"${b.branch_id===v.branch_id?' selected':''}>${esc(b.branch_id==='main'?'Main run':b.branch_id)}, round ${b.round}, ${esc(b.status.replace('_',' '))}</option>`).join('');
  $('comparisons').innerHTML=(v?.comparisons||[]).map(c=>`<div><span>${esc(c.branch_id==='main'?'Main run':c.branch_id)}</span><span>${Math.round(c.mean_belief*100)}% still believe</span></div>`).join('');
  $('record').disabled=!v||v.status!=='complete'||S.busy;
  $('importEvidence').disabled=!writable||!!v?.approval;$('verifyGemini').disabled=!writable||!!v?.approval;
  $('broadcastStatus').textContent=v?.broadcast?.status==='done'?`Answered ${v.broadcast.replies.length} questions.`:v?.approval?'Ready to answer residents.':'Available after the correction goes out.';
  $('evidencePacket').textContent=v?.evidence?JSON.stringify(v.evidence,null,2):'None yet.';}
for(const[id,kind]of[['branchNone','none'],['branchCorrection','correction']])$(id).onclick=()=>act(async()=>{
  setView(await api(ep('/branch'),{kind,...(kind==='correction'?{intervention:FB.intervention()}:{})}));toast('Branch created at the decision point.');},'Forking…');
$('branches').onchange=()=>act(async()=>setView(await api(ep('/select-branch'),{branch_id:$('branches').value})),'Switching…');
$('record').onclick=()=>act(async()=>{await api(ep('/record'),{});toast('Run saved. Choose "Saved run" to replay it.');await loadRecordings();},'Saving…');
$('importEvidence').onclick=()=>act(async()=>{setView(await api(ep('/evidence'),JSON.parse($('evidenceInput').value)));toast('Evidence imported.');},'Importing…');
$('auto').onchange=scheduleAuto;
$('mode').onchange=()=>{$('recordings').hidden=$('mode').value!=='replay';};
async function loadRecordings(){
  try{const r=await api('/recordings');S.recordings=Array.isArray(r)?r:r.recordings||[];}catch{S.recordings=[];}
  $('recordings').innerHTML=S.recordings.length?S.recordings.map(r=>`<option value="${esc(r.id)}">${esc(r.name||r.id)}</option>`).join(''):'<option value="">No saved runs</option>';}

/* ---------- render ---------- */
function render(){
  const v=S.view;
  $('clock').textContent=v?`T+${v.sim_t??0} min, round ${v.round} of 4`:'T+0 min';
  renderRail();renderCta();renderFeed();renderLab();renderDrawer();
  for(const r of FB.renderers)r(v);}
FB.render=render;

/* ---------- boot ---------- */
document.addEventListener('DOMContentLoaded',async()=>{
  const [h,sc]=await Promise.allSettled([api('/health'),api('/scenario'),loadRecordings()]);
  if(h.status==='fulfilled'){S.health=h.value;const n=(h.value.bots?.groups||[]).filter(Boolean).length,ok=n===6&&h.value.bots?.comms&&h.value.callback_ready;
    $('mode').querySelector('option[value=live]').textContent=ok?'Live Grok Bots':`Live Grok Bots (${n} of 6 set up)`;}
  else showAlert('The local server is not reachable. Start it, then reload.');
  if(sc.status==='fulfilled')S.scenario=sc.value.scenario||sc.value;
  let saved=new URL(location.href).searchParams.get('episode');if(!saved){try{saved=localStorage.getItem('firebreak.episodeId');}catch{}}
  if(saved&&h.status==='fulfilled'){try{const v=await api(`/episodes/${encodeURIComponent(saved)}`);$('mode').value=v.mode;setView(v);connect();}catch{forget();}}
  render();
});
})();

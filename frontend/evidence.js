/* Evidence: Gemini checks the viral photo when an episode starts, and the result becomes the episode's evidence.
   The reveal plays once per new result: boxes and their findings in step, then the debate, verdict and confidence. */
(()=>{
'use strict';
const FB=window.FB,$=FB.$,S=FB.S,esc=FB.esc;
const css=getComputedStyle(document.documentElement),cv=n=>css.getPropertyValue(n).trim();
const E={upload:null,image:'/data/viral.png',key:null,verified:new Set(),timers:[]};
const TAG={provenance:'earlier copy',account:'account',weather:'weather',other:'context'};
const modelName=m=>m?m.replace(/^gemini-/,'Gemini ').replace(/-/g,' ').replace(/\b(flash|lite|pro|preview|latest)\b/g,w=>w[0].toUpperCase()+w.slice(1)):'Gemini';

function current(v){
  // An uploaded image's analysis shows here until the next episode; it never changes the episode.
  if(E.upload)return{img:E.upload.url,findings:E.upload.prosecutor.findings,pro:E.upload.prosecutor.bullets,def:E.upload.defender.bullets,
    j:E.upload.judge,missing:E.upload.judge.missing,source:'Gemini checked your image. It is shown here only and does not change the episode.',key:'up:'+E.upload.image_hash};
  const e=v?.evidence;if(!e)return{img:E.image,findings:[],pro:null,def:null,j:null,missing:[],source:'',key:null};
  const arr=x=>x==null?null:Array.isArray(x)?x:[String(x)];
  const findings=Array.isArray(e.findings)&&e.findings.length?e.findings:(e.verified_facts||[]).map((t,i)=>({id:i+1,label:t,box_2d:null,category:'other'}));
  return{img:E.image,findings,pro:arr(e.prosecutor),def:arr(e.defender),j:e,missing:e.missing||[],key:`${v.id}:${e.image_hash||''}:${e.verdict}:${e.confidence}`,
    source:e.source==='gemini'?`Checked by ${modelName(e.model)}${e.status==='cached'?', loaded from the saved result':''}.`
      :e.source==='gemini-fixture'?'Gemini was unavailable, so these are sample findings. Check the key and quota, then run it again from Details.'
      :`Imported evidence (${e.source||'not from Gemini'}).`};}

function render(v){
  const c=current(v),busy=!!(S.local.verifying||S.local.analyzing);
  $('photo').classList.toggle('busy',busy);
  // Live updates re-render often; rebuilding mid-reveal would hide what already appeared.
  const sig=`${c.key}|${busy}|${c.source}|${c.img}`;if(sig===E.sig){autoVerify(v);return;}E.sig=sig;
  const animate=c.key&&c.key!==E.key&&!FB.reduced();
  if(c.key!==E.key){E.timers.forEach(clearTimeout);E.timers=[];}
  if($('evImg').getAttribute('src')!==c.img)$('evImg').setAttribute('src',c.img);
  const boxed=c.findings.filter(f=>Array.isArray(f.box_2d)),full=c.findings.find(f=>!Array.isArray(f.box_2d));
  $('evBoxes').innerHTML=boxed.map(f=>{const[y0,x0,y1,x1]=f.box_2d;
      return `<div class="box${y0<70?' top':''}" data-id="${esc(f.id)}" style="top:${y0/10}%;left:${x0/10}%;width:${(x1-x0)/10}%;height:${(y1-y0)/10}%"><span class="tag">${esc(f.id)}</span></div>`;}).join('')
    +(full?`<div class="box full" data-id="${esc(full.id)}"><span class="tag">${esc(full.id)} ${esc(TAG[full.category]||full.category)}</span></div>`:'');
  $('findings').innerHTML=c.j||E.upload?c.findings.map(f=>`<li class="reveal" data-id="${esc(f.id)}"><span class="n">${esc(f.id)}</span><span>${esc(f.label)}</span></li>`).join('')||'<li class="empty">No red flags found.</li>'
    :`<li class="empty">${S.local.verifying?'Gemini is reading the photo…':'Gemini checks the photo when the episode starts.'}</li>`;
  const list=(x,who)=>x?x.map(b=>`<li class="reveal">${esc(b)}</li>`).join('')||'<li class="empty">No points.</li>':`<li class="empty">${who} is waiting.</li>`;
  $('proList').innerHTML=list(c.pro,'The Prosecutor');$('defList').innerHTML=list(c.def,'The Defender');
  const verdict=c.j?.verdict,conf=c.j?.confidence;
  const col={False:cv('--ember'),Misleading:cv('--ember'),Unverified:cv('--warn'),True:cv('--ok')}[verdict]||cv('--smoke');
  const vw=$('verdict');vw.textContent=verdict||'Waiting';vw.style.color=col;
  $('confidence').textContent=Number.isFinite(conf)?`${conf}% sure`:'';$('confBar').style.background=col;
  $('reasoning').textContent=c.j?.reasoning||'';
  $('miss').innerHTML=c.missing.length?`<span class="hint">Would change the ruling:</span>`+c.missing.map((m,i)=>`<div class="reveal"><span>${esc(m.item)} <em class="who">from ${esc(m.ask_target)}</em></span><button class="btn sm" data-i="${i}">Draft request</button></div>`).join(''):'';
  $('miss').querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>draftAsk(c.missing[+b.dataset.i],b));
  $('evidenceSource').textContent=c.source;
  const bar=$('confBar');
  if(!animate){
    // Settled state: everything visible, no motion.
    document.querySelectorAll('#evidence .reveal, .evidence .reveal, .box').forEach(n=>n.classList.add('in'));
    bar.style.transition='none';bar.style.transform=`scaleX(${Number.isFinite(conf)?conf/100:0})`;requestAnimationFrame(()=>bar.style.transition='');
  }else{
    // One orchestrated reveal: each box with its finding, then the debate, then the verdict.
    bar.style.transition='none';bar.style.transform='scaleX(0)';
    const at=(ms,fn)=>E.timers.push(setTimeout(fn,ms));
    c.findings.forEach((f,i)=>at(150+i*260,()=>document.querySelectorAll(`.box[data-id="${CSS.escape(String(f.id))}"], #findings li[data-id="${CSS.escape(String(f.id))}"]`).forEach(n=>n.classList.add('in'))));
    const t=150+c.findings.length*260;
    at(t,()=>document.querySelectorAll('#proList .reveal,#defList .reveal').forEach((n,i)=>setTimeout(()=>n.classList.add('in'),i*60)));
    at(t+350,()=>{vw.classList.remove('stamp');void vw.offsetWidth;vw.classList.add('stamp');bar.style.transition='';bar.style.transform=`scaleX(${(conf||0)/100})`;});
    at(t+650,()=>document.querySelectorAll('#miss .reveal').forEach(n=>n.classList.add('in')));}
  E.key=c.key;
  autoVerify(v);}

function autoVerify(v){
  // Once per episode, before approval: replaces sample evidence, or fills a live episode's empty evidence.
  if(!v||v.mode==='replay'||v.approval||v.status==='running'||E.verified.has(v.id)||S.busy)return;
  if(v.evidence?.source==='gemini')return;
  E.verified.add(v.id);setTimeout(verify,0);}
function verify(){
  const v=S.view;if(!v)return;E.upload=null;
  return FB.act(async()=>{S.local.verifying=true;FB.render();
    try{const r=await FB.api(`/gemini/episodes/${encodeURIComponent(v.id)}/evidence`,{});
      FB.toast(r.status==='done'?'Gemini checked the photo.':r.status==='cached'?'Gemini result loaded.':'Gemini was unavailable. Showing sample findings.');
      S.local.verifying=false;FB.setView(r.view);}
    finally{S.local.verifying=false;}},'Gemini is checking…');}
FB.verify=verify;
$('verifyGemini').onclick=verify;

async function draftAsk(m,btn){
  btn.disabled=true;btn.textContent='Drafting…';
  try{const d=await FB.api('/draft_ask',{item:m.item,ask_target:m.ask_target});
    const row=btn.parentElement;row.innerHTML=`<span class="drafted">${esc(d.text)}</span><button class="btn sm">Copy</button>`;
    row.querySelector('button').onclick=async e=>{try{await navigator.clipboard.writeText(d.text);e.target.textContent='Copied';}catch{e.target.textContent='Select and copy';}};}
  catch(err){FB.alert(err.message);btn.disabled=false;btn.textContent='Draft request';}}

// Check your own image: the full Gemini debate runs live on it.
$('anBtn').onclick=()=>$('anFile').click();
$('anFile').onchange=async e=>{
  const file=e.target.files[0];e.target.value='';if(!file)return;
  const claim=prompt('What does the post claim?',S.view?.scout?.claim||S.scenario?.claim||'');if(claim===null||!claim.trim())return;
  const url=URL.createObjectURL(file);$('evImg').setAttribute('src',url);$('evBoxes').innerHTML='';
  S.local.analyzing=true;$('anBtn').disabled=true;FB.alert(null);FB.render();
  const fd=new FormData();fd.append('image',file);fd.append('claim',claim.trim());
  try{const d=await FB.api('/analyze',fd);E.upload={url,...d};FB.toast('Gemini checked your image.');}
  catch(err){E.upload=null;FB.alert(err.message);}
  finally{S.local.analyzing=false;$('anBtn').disabled=false;FB.render();}};

FB.api('/scenario').then(d=>{const img=(d.scenario||d).image;if(img){E.image='/data/'+img;FB.render();}}).catch(()=>{});
FB.renderers.push(v=>{if(v?.id!==E.episode){E.episode=v?.id;E.upload=null;}render(v);});
})();

/* The town: 240 simulated accounts in six communities, drawn from the server's frames.
   Between rounds, node colors blend and each real message delivery (frame.events) travels along its edge.
   The canvas only redraws while a transition runs; reduced motion jumps straight to the end state. */
(()=>{
'use strict';
const FB=window.FB,$=FB.$;
const css=getComputedStyle(document.documentElement),cv=n=>css.getPropertyValue(n).trim();
const rgb=h=>{h=h.replace('#','');return[0,2,4].map(i=>parseInt(h.slice(i,i+2),16));};
// Node states from the server: 0 not reached, 1 sharing the rumor, 2 believes it, 3 sharing the correction, 4 corrected.
const COL=[rgb(cv('--faint')),rgb(cv('--ember')),rgb(cv('--ember-dim')),rgb(cv('--water')),rgb(cv('--water-dim'))];
const EMBER=cv('--ember'),WATER=cv('--water'),SMOKE=cv('--smoke'),BONE=cv('--bone');
const CENTERS=[[.22,.27],[.2,.74],[.5,.5],[.79,.26],[.8,.74],[.5,.12]];
const SHORT=['Poway','Escondido parents','Influencers','Retirees','Reporters','Skeptics'];
const ease=t=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2; // ease-in-out cubic: things already on screen moving
const easeOut=t=>1-Math.pow(1-t,3);

const canvas=$('map'),ctx=canvas.getContext('2d');
const M={episode:null,branch:null,frames:[],groups:[],edges:[],pos:[],from:0,to:0,t0:0,dur:0,running:false,queue:[],W:0,H:0,shownStats:[0,0,0],names:[]};

// Same deterministic layout as the server-side graph view (mulberry32, seed 3).
function random(seed){return()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
function layout(groups){
  const r=random(3);
  return groups.map(g=>{const c=CENTERS[+g]||CENTERS[0];const gauss=()=>Math.sqrt(-2*Math.log(Math.max(1e-6,r())))*Math.cos(2*Math.PI*r());
    const x=c[0]+gauss()*.065;return[x,c[1]+gauss()*(+g===5?.035:.065)];});}
const pad=()=>M.W<500?18:34;
const P=i=>{const p=pad(),q=M.pos[i];return[p+q[0]*(M.W-2*p),p+8+q[1]*(M.H-2*p-8)];};

function fit(){
  const r=canvas.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);
  M.W=r.width;M.H=r.height;canvas.width=Math.max(1,Math.round(r.width*d));canvas.height=Math.max(1,Math.round(r.height*d));
  ctx.setTransform(d,0,0,d,0,0);draw(1);}
new ResizeObserver(fit).observe(canvas.parentElement);

/* ---------- drawing ---------- */
const mix=(a,b,t)=>a.map((v,i)=>Math.round(v+(b[i]-v)*t));
const share=(f,g,set)=>{if(!f)return 0;let n=0,t=0;f.states.forEach((s,i)=>{if(+M.groups[i]===g){t++;if(set.includes(s))n++;}});return t?n/t:0;};
function draw(raw){
  ctx.clearRect(0,0,M.W,M.H);
  const A=M.frames[M.from],B=M.frames[M.to];
  if(!B||!M.pos.length){ctx.fillStyle=SMOKE;ctx.font="500 14px Archivo, sans-serif";ctx.textAlign='center';ctx.fillText('The town appears when the episode starts.',M.W/2,M.H/2);return;}
  const e=ease(raw),step=M.to===M.from+1;
  // edges
  ctx.lineWidth=.6;ctx.strokeStyle='rgba(237,229,217,.055)';ctx.beginPath();
  for(const[a,b]of M.edges){const[x1,y1]=P(a),[x2,y2]=P(b);ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);}ctx.stroke();
  // deliveries travel their edge during a one-round step
  if(step&&raw<1){
    const evs=B.events||[];
    evs.forEach((ev,k)=>{
      if(M.pos[ev.from]==null||M.pos[ev.to]==null)return;
      const d=(k%28)/28*.45,p=Math.min(1,Math.max(0,(raw-d)/.5));if(p<=0||p>=1)return;
      const[x1,y1]=P(ev.from),[x2,y2]=P(ev.to),q=easeOut(p),x=x1+(x2-x1)*q,y=y1+(y2-y1)*q;
      const tail=Math.max(0,q-.18),tx=x1+(x2-x1)*tail,ty=y1+(y2-y1)*tail,col=/correction|evidence|retract/.test(ev.kind)?WATER:EMBER;
      const g=ctx.createLinearGradient(tx,ty,x,y);g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(1,col);
      ctx.strokeStyle=g;ctx.lineWidth=1.6;ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(x,y);ctx.stroke();
      ctx.fillStyle=col;ctx.beginPath();ctx.arc(x,y,2,0,7);ctx.fill();});}
  // nodes
  for(let i=0;i<B.states.length;i++){
    if(!M.pos[i])continue;const[x,y]=P(i),sa=A?A.states[i]:B.states[i],sb=B.states[i];
    const c=mix(COL[sa]||COL[0],COL[sb]||COL[0],e),hot=s=>s===1||s===3?1:0,halo=hot(sa)*(1-e)+hot(sb)*e;
    if(halo>0){ctx.fillStyle=`rgba(${c[0]},${c[1]},${c[2]},${.15*halo})`;ctx.beginPath();ctx.arc(x,y,9,0,7);ctx.fill();}
    ctx.fillStyle=`rgb(${c[0]},${c[1]},${c[2]})`;ctx.beginPath();ctx.arc(x,y,2.6+.7*halo,0,7);ctx.fill();
    // one ring when an account turns to the correction
    if(step&&raw<1&&sb>=3&&sa<3&&raw>.35){const k=(raw-.35)/.65;ctx.strokeStyle=`rgba(92,200,255,${(1-k)*.7})`;ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(x,y,3+k*13,0,7);ctx.stroke();}}
  // community labels with live share believing the rumor
  ctx.textAlign='center';
  CENTERS.forEach(([cx,cy],g)=>{
    const p=pad(),x=p+cx*(M.W-2*p);let y=p+8+cy*(M.H-2*p-8)+(g===2?-62:g===5?-30:cy<.5?-60:60);y=Math.max(14,Math.min(M.H-20,y));
    const b=share(A,g,[1,2])*(1-e)+share(B,g,[1,2])*e,cor=share(A,g,[3,4])*(1-e)+share(B,g,[3,4])*e;
    ctx.font="600 12px Archivo, sans-serif";ctx.fillStyle=b>.5?EMBER:BONE;ctx.fillText(M.W<500?SHORT[g]:(M.names[g]||SHORT[g]),x,y);
    ctx.font="500 11px 'IBM Plex Mono', monospace";ctx.fillStyle=cor>b?WATER:b>.02?EMBER:SMOKE;
    const n=Math.round((cor>b?cor:b)*100);ctx.fillText(M.W<500?`${n}%`:cor>b?`${n}% corrected`:`${n}% believe`,x,y+14);});}

function loop(now){
  if(!M.running)return;
  const raw=Math.min(1,(now-M.t0)/M.dur);draw(raw);
  if(raw<1){requestAnimationFrame(loop);return;}
  M.from=M.to;M.running=false;
  if(M.queue.length){const n=M.queue.shift();go(n,1300);}}
function go(target,dur){
  target=Math.max(0,Math.min(M.frames.length-1,target));
  if(FB.reduced()||!M.W){M.from=M.to=target;M.queue=[];draw(1);sync(target);return;}
  M.from=M.running?M.to:M.from;M.to=target;M.t0=performance.now();M.dur=dur;sync(target);
  if(!M.running){M.running=true;requestAnimationFrame(loop);}}

/* ---------- numbers, bars, timeline ---------- */
function tween(el,from,to,fmt){
  if(FB.reduced()||from===to){el.textContent=fmt(to);return;}
  const t0=performance.now(),d=700;
  const tick=now=>{const k=Math.min(1,(now-t0)/d),v=from+(to-from)*easeOut(k);el.textContent=fmt(v);if(k<1)requestAnimationFrame(tick);};
  requestAnimationFrame(tick);}
function sync(i){
  const f=M.frames[i];if(!f)return;const n=f.states.length||240;
  const bel=f.states.filter(s=>s===1||s===2).length/n,cor=f.states.filter(s=>s>=3).length/n;
  const reach=f.counts?n-(f.counts.unseen??0):f.states.filter(s=>s>0).length;
  const pct=v=>Math.round(v*100)+'%',[pb,pc,pr]=M.shownStats;
  tween($('sBel'),pb,bel,pct);tween($('sCor'),pc,cor,pct);tween($('sReach'),pr,reach,v=>String(Math.round(v)));
  M.shownStats=[bel,cor,reach];
  $('scrub').value=i;$('tLabel').textContent=`Round ${f.round??i}`;
  const names=FB.S.view?.groups||[];
  $('groups').innerHTML=CENTERS.map((_,g)=>{const b=share(f,g,[1,2]),c=share(f,g,[3,4]),grp=names[g];
    const quote=(grp?.reactions||[]).slice(-1)[0];
    return `<li title="${FB.esc(quote?`"${quote}"`:'')}"><span class="gn">${FB.esc(grp?.name||SHORT[g])}</span><span class="gv">${Math.round(b*100)}% / ${Math.round(c*100)}%</span><span class="track"><i class="b" style="transform:scaleX(${b})"></i><i class="c" style="transform:scaleX(${c})"></i></span></li>`;}).join('');}

$('scrub').oninput=e=>{M.queue=[];go(+e.target.value,500);};
$('replayRounds').onclick=()=>{
  if(M.frames.length<2)return;M.queue=[];M.from=M.to=0;draw(1);sync(0);
  M.queue=M.frames.map((_,i)=>i).slice(2);go(1,1300);};

/* ---------- from server view ---------- */
FB.renderers.push(v=>{
  if(!v||!v.network){M.episode=null;M.frames=[];M.pos=[];draw(1);$('groups').innerHTML='';$('scrub').max=0;['sBel','sCor'].forEach(id=>$(id).textContent='0%');$('sReach').textContent='0';M.shownStats=[0,0,0];return;}
  M.names=(v.groups||[]).map(g=>g.name);
  const fresh=v.id!==M.episode||v.branch_id!==M.branch;
  if(fresh){
    M.episode=v.id;M.branch=v.branch_id;M.groups=v.network.groups||[];M.edges=v.network.edges||[];M.pos=layout(M.groups);
    M.frames=v.frames||[];$('scrub').max=Math.max(0,M.frames.length-1);M.queue=[];M.running=false;M.from=M.to=M.frames.length-1;
    if(M.W)draw(1);sync(M.to);return;}
  const grew=(v.frames||[]).length>M.frames.length;
  M.frames=v.frames||[];$('scrub').max=Math.max(0,M.frames.length-1);
  if(grew)go(M.frames.length-1,1600);else sync(M.to);
});
})();

/* Spread simulation. Math is unchanged from firebreak-ui.html and tuned: do not edit run(), hr(), the graph build,
   pFire, the 0.2 conversion factor or the age > 12 burnout. Only FR[x].p and FR[x].esMult are data driven
   (filled from the Drafter and Society Sim in app.js). Top-level names here are shared with app.js. */
/* ---------- simulation ---------- */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function hr(a,b,c,d){let x=(a*73856093)^(b*19349663)^(c*83492791)^(d*2654435761);x=Math.imul(x^(x>>>16),0x45d9f3b);x=Math.imul(x^(x>>>16),0x45d9f3b);x^=x>>>16;return(x>>>0)/4294967296}
const C=6,PER=40,N=C*PER,T=90,START=80;
const GROUPS=["Poway residents","Escondido parents (ES)","Local influencers","Retirees on Facebook","Reporters","Skeptics"];
const SHORT=["Poway","Esc. ES","Influ.","Retirees","Press","Skeptic"];
const pFire=[.05,.05,.07,.05,.02,.012];
// Defaults until the Drafter and Society Sim report. esMult replaces the old hardcoded 0.25 Spanish multiplier.
const FR={
  A:{name:"Fact check",text:"",text_es:"",p:[.10,.08,.12,.07,.30,.25],esMult:.25},
  B:{name:"Action first",text:"",text_es:"",p:[.24,.20,.16,.18,.28,.20],esMult:.25},
  C:{name:"Neighbor voice",text:"",text_es:"",p:[.18,.14,.22,.16,.18,.12],esMult:.25}
};
const g=(()=>{const r=mulberry32(7);const cl=[],adj=[];for(let i=0;i<N;i++){cl.push(Math.floor(i/PER));adj.push(new Set())}
  const link=(a,b)=>{if(a!==b){adj[a].add(b);adj[b].add(a)}};
  for(let i=0;i<N;i++){const c=cl[i];for(let k=0;k<3;k++)link(i,c*PER+Math.floor(r()*PER));
    if(r()<(c===2?.55:.07))link(i,Math.floor(r()*N)); if(c===2&&r()<.5)link(i,Math.floor(r()*N));}
  const A=adj.map(s=>[...s]);const edges=[];A.forEach((l,i)=>l.forEach(j=>{if(j>i)edges.push([i,j])}));
  return{cl,adj:A,edges}})();

const cache=new Map();
function run(deploy,fr,es){
  const key=deploy+"|"+fr+"|"+es;if(cache.has(key))return cache.get(key);
  const s=new Uint8Array(N),age=new Uint8Array(N);const frames=[],ev=[];for(let t=0;t<=T;t++)ev.push([]);
  s[START]=1;ev[0].push([START,-1,1]);frames.push(s.slice());
  const pc=FR[fr].p;
  for(let t=1;t<=T;t++){
    if(deploy!=null&&t===deploy){
      const cnt=new Array(C).fill(0);for(let i=0;i<N;i++)if(s[i]===1||s[i]===2)cnt[g.cl[i]]++;
      const tgt=cnt.indexOf(Math.max(...cnt));
      const seeds=[0,1,2,3].map(k=>4*PER+k*7).concat([0,1,2,3].map(k=>tgt*PER+k*9+3));
      for(const i of seeds){s[i]=3;age[i]=0;ev[t].push([i,-1,3])}
    }
    const n=s.slice();
    for(let i=0;i<N;i++){
      if(s[i]===1){for(const j of g.adj[i])if(s[j]===0&&n[j]===0&&hr(i,j,t,1)<pFire[g.cl[j]]){n[j]=1;age[j]=0;ev[t].push([j,i,1])}}
      if(s[i]===3){for(const j of g.adj[i]){if(n[j]===3)continue;let p=pc[g.cl[j]];if(g.cl[j]===1&&!es)p*=FR[fr].esMult;
        if(s[j]===0&&hr(i,j,t,2)<p){n[j]=3;age[j]=0;ev[t].push([j,i,3])}
        else if((s[j]===1||s[j]===2)&&hr(i,j,t,3)<p*.2){n[j]=3;age[j]=0;ev[t].push([j,i,3])}}}
    }
    for(let i=0;i<N;i++){if(n[i]===1||n[i]===3){age[i]++;if(age[i]>12)n[i]++}}
    s.set(n);frames.push(s.slice());
  }
  const bel=frames.map(f=>{let b=0,c=0;for(const x of f){if(x===1||x===2)b++;else if(x>=3)c++}return[b/N,c/N]});
  const out={frames,ev,bel};cache.set(key,out);return out;
}

/* ---------- layout ---------- */
const centers=[[.22,.27],[.2,.74],[.5,.5],[.79,.26],[.8,.74],[.5,.12]];
const pos=(()=>{const r=mulberry32(3);const gauss=()=>{let u=0,v=0;while(!u)u=r();while(!v)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v)};
  return g.cl.map((c,i)=>{const[x,y]=centers[c];const sx=c===5?.09:.065,sy=c===5?.035:.065;return[x+gauss()*sx,y+gauss()*sy]})})();

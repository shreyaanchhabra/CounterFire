(function(root){
'use strict';
function nextAction(v,{busy=false,dirty=false,hasCopy=false}={}){
 const result=(action,label,phase)=>({action,label,phase});
 if(!v)return busy?result('wait','Starting…',0):result('start','Start demo',0);
 if(busy&&v.status!=='running')return result('wait','Working…',nextAction(v,{dirty,hasCopy}).phase);
 if(v.status==='running'){
  if(v.analysis?.status==='running')return result('wait','Checking the image…',1);
  if(v.editor_status?.status==='running')return result('wait','Applying your note…',2);
  if(v.pending_jobs?.some(j=>j.task_type==='draft'))return result('wait','Drafting a response…',2);
  return result('wait','Communities responding…',v.round<2?0:3);
 }
 if(v.status==='error')return result('start','Start a new run',0);
 if(v.round>=4)return result('replay','Replay the spread',3);
 if(v.round<2)return result('advance',v.round===0?'Watch the rumor spread':'Continue the spread',0);
 if(v.approval || (v.status==='ready'&&!v.pending_intervention&&(v.branch_id!=='main'||v.mode==='replay'&&!v.recorded_intervention)))return result('advance','See the response',3);
 if(v.mode!=='replay'){
  if(v.analysis?.status==='error')return result('analyze','Retry image check',1);
  const checked=v.analysis?.status==='done'||v.evidence&&v.evidence.source!=='synthetic fixture';
  if(!checked)return result('analyze','Check the image',1);
  if(!v.drafts?.framings?.length)return result('draft','Draft a correction',2);
 }
 if(!v.pending_intervention||dirty)return result('propose',dirty?'Review your edits':'Review the correction',2);
 return result('approve','Approve correction',2);
}
const api={nextAction};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.FirebreakDemoFlow=api;
})(typeof globalThis!=='undefined'?globalThis:this);

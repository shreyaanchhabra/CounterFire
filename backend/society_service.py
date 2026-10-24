"""Durable application controller for native Grokbots society episodes."""
import copy
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.clients.grokbots_webhook import GrokBotsWebhookClient, WebhookSettings
from backend.config import ROOT
from backend.grokbots_return import JobStore, RoundTask, callback_observation, canonical
from backend.schemas import BroadcasterReplies, DrafterOut, GROUPS, Incident, ReplyQuestion, ScoutSelection
from backend.simulation import Simulation


class Conflict(ValueError):
    pass


class Intervention(BaseModel):
    model_config = ConfigDict(extra='forbid')
    framing_key: str = Field(pattern='^[ABC]$')
    text_en: str = Field(min_length=1, max_length=280)
    text_es: str | None = Field(default=None, min_length=1, max_length=280)
    target_groups: list[int] = Field(min_length=1, max_length=6)

    @field_validator('text_es', mode='before')
    @classmethod
    def optional_spanish(cls, value):
        return None if value is None or value == '' else value

    @field_validator('text_en', 'text_es')
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Correction copy cannot be blank')
        return value

    @field_validator('target_groups')
    @classmethod
    def groups(cls, value):
        if any(type(g) is not int or g not in range(6) for g in value) or len(set(value)) != len(value):
            raise ValueError('Target groups must be unique IDs from 0 through 5')
        return sorted(value)


def environment():
    return {**dotenv_values(ROOT / '.env'), **os.environ}


def fixture_decisions(observation):
    """Explicit scripted baseline. These choices are never attributed to Grokbots."""
    decisions = []
    gid = observation['group_id']
    for p in observation['personas']:
        known = [m for m in p['messages'] if m['comprehensible']]
        belief = p['belief']
        action, message, parent = 'wait', None, None
        if known:
            current = known[-1]
            parent = current['id']
            corrected = current['kind'] in {'evidence', 'correction', 'retract'}
            if corrected:
                belief = max(0, belief - .3)
                action = 'share'
                message = ('Consulta los avisos oficiales antes de compartir.' if p.get('language') == 'es'
                           else 'Please check the official source before sharing this claim.')
            elif gid in {2, 0, 3}:
                belief = min(1, belief + .15)
                action = 'share'
                message = ('¿Alguien puede confirmar este aviso?' if p.get('language') == 'es'
                           else 'A neighbor shared this claim. Can anyone confirm the source?')
            else:
                action = 'verify'
        decisions.append(dict(persona_id=p['persona_id'], action=action, belief=belief,
                              message=message, parent_id=parent))
    return dict(group_id=gid, decisions=decisions)


class EpisodeManager:
    def __init__(self, directory=None, jobs=None):
        self.directory = Path(directory or ROOT / 'cache/society')
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'recordings').mkdir(exist_ok=True)
        self.jobs = jobs or JobStore(ROOT / 'cache/grokbots/jobs.sqlite3')
        self.lock = threading.RLock()
        self.episodes = {}
        self.workers = {}
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='firebreak')
        self.scenario = json.loads((ROOT / 'data/scenario_sd1024.json').read_text())
        self.fixtures = json.loads((ROOT / 'data/grok_demo_outputs.json').read_text())

    def health(self):
        env = environment()
        groups = [bool(env.get(f'GROKBOTS_GROUP_{i}_URL') and env.get(f'GROKBOTS_GROUP_{i}_KEY')) for i in range(6)]
        return {'status': 'ok', 'bots': {'groups': groups, 'comms': bool(env.get('GROKBOTS_WEBHOOK_URL') and env.get('GROKBOTS_WEBHOOK_KEY'))},
                'callback_ready': bool(env.get('GROKBOTS_CALLBACK_BASE_URL')), 'modes': ['fixture','live','replay']}

    def _load(self, identifier):
        if identifier not in self.episodes:
            if not identifier or any(c not in '0123456789abcdef-' for c in identifier):
                raise KeyError(identifier)
            path = self.directory / (identifier + '.json')
            if not path.exists():
                raise KeyError(identifier)
            data = json.loads(path.read_text())
            for b in data['branches'].values():
                b['sim'] = Simulation.from_state(b['sim'])
                if b['status'] == 'running':
                    b['status'] = 'error'
                    data['error'] = 'Server restarted during native work. Existing task IDs remain in the local job store; no automatic resend.'
            self.episodes[identifier] = data
        return self.episodes[identifier]

    def _save(self, e):
        data = {k: v for k,v in e.items() if k != 'branches'}
        data['branches'] = {key: {**b, 'sim': b['sim'].export_state()} for key,b in e['branches'].items()}
        target = self.directory / (e['id'] + '.json')
        temp = target.with_suffix('.pending')
        temp.write_text(canonical(data))
        temp.chmod(0o600)
        temp.replace(target)

    def _touch(self,e):
        e['version'] += 1
        self._save(e)

    def _branch(self,sim,status='ready'):
        return {'sim':sim,'status':status,'pending':None,'approval':None,'revision':0,
                'no_intervention':False,'history':[sim.export_state()], 'intervention':None,'broadcast':None}

    def create(self, mode='fixture', recording_id=None):
        if mode not in {'fixture','live','replay'}:
            raise ValueError('Mode must be fixture, live, or replay')
        with self.lock:
            record = None
            if mode == 'replay':
                record = self._read_recording(recording_id)
                sim = Simulation.from_state(record['states'][0])
            else:
                sim = Simulation(evidence=self.scenario['verification'] if mode=='fixture' else {})
            identifier = str(uuid4())
            e = {'id':identifier,'mode':mode,'active':'main','version':0,'error':None,
                 'drafts':copy.deepcopy(record['drafts'] if record else self.fixtures['drafter'] if mode=='fixture' else None),
                 'evidence':copy.deepcopy(record['evidence'] if record else {**self.scenario['verification'],'source':'synthetic fixture','revision':1} if mode=='fixture' else None),
                 'scout':copy.deepcopy(record.get('scout') if record else None),
                 'pending_jobs':[],'recording':record,'branches':{'main':self._branch(sim)}}
            self.episodes[identifier]=e
            if record and not record.get('intervention'):
                e['branches']['main']['no_intervention']=True
            self._touch(e)
            return self.view(identifier)

    def view(self,identifier):
        with self.lock:
            e=self._load(identifier); b=e['branches'][e['active']]
            view=b['sim'].snapshot()
            branches=[{'branch_id':key,'round':v['sim'].round,'belief':round(sum(g['belief'] for g in v['sim'].snapshot()['groups'])/6,4),'status':v['status']} for key,v in e['branches'].items()]
            comparisons=[]
            rounds={v['sim'].round for v in e['branches'].values()}
            if len(branches)>1 and len(rounds)==1:
                comparisons=[{'branch_id':v['branch_id'],'round':v['round'],'mean_belief':v['belief'],'label':'Illustrative simulated outcome'} for v in branches]
            status=b['status']
            pipeline=[{'agent':'scout','status':'done' if e['scout'] else 'waiting','summary':e['scout']['summary'] if e['scout'] else 'Waiting for incident clustering'},
                {'agent':'judge','status':'done' if e['evidence'] else 'waiting','summary':(e['evidence'].get('verdict','Imported evidence') if e['evidence'] else 'Awaiting teammate Gemini packet')},
                {'agent':'drafter','status':'done' if e['drafts'] else 'waiting','summary':'Three bilingual corrections' if e['drafts'] else 'Needs evidence and drafting'},
                {'agent':'society','status':'running' if status=='running' else 'done' if b['sim'].round else 'waiting','summary':f'Six communities · round {b["sim"].round}'},
                {'agent':'editor','status':'ready','summary':'Voiskey normalized input or manual edit'},
                {'agent':'broadcaster','status':'done' if b['approval'] else 'waiting','summary':'Approved in-app correction' if b['approval'] else 'Waiting for exact-copy approval'}]
            view.update(id=e['id'],mode=e['mode'],status=status,version=e['version'],error=e['error'],
                pipeline=pipeline,drafts=copy.deepcopy(e['drafts']),evidence=copy.deepcopy(e['evidence']),
                pending_intervention=copy.deepcopy(b['pending']),approval=copy.deepcopy(b['approval']),branches=branches,
                comparisons=comparisons,pending_jobs=copy.deepcopy(e['pending_jobs']),scout=copy.deepcopy(e['scout']),
                broadcast=copy.deepcopy(b.get('broadcast')), source_mode=e['recording']['source_mode'] if e['recording'] else e['mode'],
                recorded_intervention=copy.deepcopy(e['recording'].get('intervention')) if e['recording'] else None)
            return view

    def _check_mutation(self,e):
        if e['branches'][e['active']]['status']=='running':
            raise Conflict('A native round is running; wait for its barrier before editing')

    def _native(self,e,kind,gid,observation):
        env=environment()
        prefix=f'GROKBOTS_GROUP_{gid}' if kind=='community' else 'GROKBOTS_WEBHOOK'
        url=env.get(prefix+'_URL','') if kind=='community' else env.get('GROKBOTS_WEBHOOK_URL','')
        key=env.get(prefix+'_KEY','') if kind=='community' else env.get('GROKBOTS_WEBHOOK_KEY','')
        base=env.get('GROKBOTS_CALLBACK_BASE_URL','')
        if not url or not key or not base:
            raise Conflict(f'Native {kind} routine or callback origin is not configured')
        branch_id=e['active']; b=e['branches'][branch_id]
        task=RoundTask(episode_id=e['id']+':'+branch_id,round_id=b['sim'].round,group_id=gid,
                       observation=observation,task_type=kind)
        job=self.jobs.create(task,ttl=600)
        with self.lock:
            e['pending_jobs'].append({'request_id':job.request_id,'group_id':gid,'task_type':kind,'status':'pending'})
            self._touch(e)
        client=GrokBotsWebhookClient(WebhookSettings(url=url,key=key))
        try:
            full=callback_observation(task,job,base)
            # Native webhook chat context truncates large bodies. Pull exactly one
            # capability-scoped task over HTTPS instead of stuffing it into the trigger.
            trigger={'task_url':full['callback']['url'].replace('/api/results/','/api/tasks/'),
                     'callback':full['callback'],'task_type':kind}
            receipt=client.send(trigger,request_id=job.request_id)
        finally:
            client.close()
        if receipt.delivery=='rejected':
            raise Conflict(f'Native {kind} routine rejected the request (HTTP {receipt.http_status})')
        deadline=time.monotonic()+float(env.get('GROKBOTS_TASK_TIMEOUT_SECONDS','300'))
        while time.monotonic()<deadline:
            result=self.jobs.get(job.request_id)
            if result['status']=='completed':
                with self.lock:
                    e['pending_jobs']=[p for p in e['pending_jobs'] if p['request_id']!=job.request_id]
                    self._touch(e)
                return result['result']['payload']
            if result['status']!='pending':
                raise Conflict('Native task was superseded; no resend attempted')
            time.sleep(.5)
        raise TimeoutError(f'Native {kind} task timed out; request {job.request_id} was not resent')

    def _scout(self,e):
        selection=ScoutSelection.model_validate(self.fixtures['scout'] if e['mode']=='fixture' else self._native(e,'scout',0,{'posts':self.scenario['posts'],'incident_id':self.scenario['incident_id']}))
        posts={p['id']:p for p in self.scenario['posts']}
        ids=selection.selected_post_ids
        if len(set(ids))!=len(ids) or any(i not in posts for i in ids):
            raise ValueError('Scout selected duplicate or unknown post IDs')
        from datetime import datetime
        times=[datetime.fromisoformat(posts[i]['timestamp']) for i in ids]
        e['scout']=Incident(incident_id=self.scenario['incident_id'],claim=selection.claim,post_count=len(ids),
            velocity_per_min=len(ids)/max(1,(max(times)-min(times)).total_seconds()/60),
            languages=sorted({posts[i]['language'] for i in ids}),summary=selection.summary).model_dump()

    def advance(self,identifier):
        with self.lock:
            e=self._load(identifier); b=e['branches'][e['active']]
            if b['status']=='running':
                return self.view(identifier)
            if b['status']=='error':
                raise Conflict('Resolve the failed native run before starting a new episode; no automatic retry')
            if b['sim'].round>=4:
                return self.view(identifier)
            if b['sim'].round>=2 and not b['approval'] and not b['no_intervention']:
                raise Conflict('Approve a proposed correction or fork a no-correction branch')
            if e['mode']=='live':
                health=self.health()
                if not all(health['bots']['groups']) or not health['bots']['comms'] or not health['callback_ready']:
                    raise Conflict('Configure all six official community routines, Comms, and the callback origin first')
                b['status']='running'; self._touch(e)
                self.workers[identifier]=self.pool.submit(self._advance_work,identifier,e['active'])
            else:
                self._advance_work(identifier,e['active'])
            return self.view(identifier)

    def _advance_work(self,identifier,branch_id):
        e=self._load(identifier); b=e['branches'][branch_id]
        try:
            if e['mode']=='replay':
                states=e['recording']['states']; nxt=b['sim'].round+1
                if nxt>=len(states):
                    raise Conflict('Recording has no later computed round')
                b['sim']=Simulation.from_state(states[nxt])
            else:
                if e['scout'] is None:
                    self._scout(e)
                if e['mode']=='fixture':
                    results={gid:fixture_decisions(b['sim'].observation(gid)) for gid in range(6)}
                else:
                    observations={gid:b['sim'].observation(gid) for gid in range(6)}
                    with ThreadPoolExecutor(max_workers=6) as group_pool:
                        futures={gid:group_pool.submit(self._native,e,'community',gid,observations[gid]) for gid in range(6)}
                        results={gid:future.result() for gid,future in futures.items()}
                b['sim'].apply_round(results)
            with self.lock:
                b['history'].append(b['sim'].export_state())
                b['status']='complete' if b['sim'].round>=4 else 'awaiting_approval' if b['sim'].round==2 and not b['approval'] and not b['no_intervention'] else 'ready'
                e['error']=None; self._touch(e)
        except Exception as exc:
            with self.lock:
                b['status']='error'
                e['error']=str(exc) if isinstance(exc,(ValueError,TimeoutError)) else f'Native workflow failed ({type(exc).__name__})'
                self._touch(e)

    def evidence(self,identifier,packet):
        with self.lock:
            e=self._load(identifier); self._check_mutation(e)
            if e['mode']=='replay': raise Conflict('A recorded trajectory cannot be given different evidence')
            if any(b['approval'] for b in e['branches'].values()):
                raise Conflict('Evidence is frozen after approval; create a new episode to use revised evidence')
            facts=packet.get('verified_facts')
            if packet.get('verdict') not in ('False','Misleading','Unverified','True') or not isinstance(facts,list) or any(not isinstance(f,str) or not f.strip() for f in facts):
                raise ValueError('Evidence requires a known verdict and a list of nonblank string facts')
            if 'findings' in packet and not isinstance(packet['findings'],list):
                raise ValueError('Evidence findings must be a list')
            if packet.get('incident_id',self.scenario['incident_id'])!=self.scenario['incident_id']:
                raise Conflict('Evidence belongs to another incident')
            e['evidence']=copy.deepcopy(packet)
            for b in e['branches'].values():
                b['sim'].evidence=copy.deepcopy(packet)
                b['pending']=None
            e['drafts']=None
            self._touch(e); return self.view(identifier)

    def drafts(self,identifier):
        with self.lock:
            e=self._load(identifier); self._check_mutation(e)
            if e['mode']=='replay': return self.view(identifier)
            if not e['evidence']: raise Conflict('Import the teammate evidence packet before drafting')
            if e['mode']=='fixture':
                e['drafts']=DrafterOut.model_validate(self.fixtures['drafter']).model_dump(); self._touch(e)
            else:
                b=e['branches'][e['active']]; previous=b['status']; b['status']='running'; self._touch(e)
                def work():
                    try:
                        payload=self._native(e,'draft',0,{'claim':e['scout']['claim'] if e['scout'] else self.scenario['claim'],**e['evidence'],
                            'safety_action':e['evidence'].get('safety_action','Check official evacuation updates before sharing.'),
                            'official_source':e['evidence'].get('official_source','https://www.readysandiego.org/')})
                        with self.lock:
                            e['drafts']=DrafterOut.model_validate(payload).model_dump(); b['status']=previous;self._touch(e)
                    except Exception as exc:
                        with self.lock:
                            b['status']='error';e['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__;self._touch(e)
                self.workers[identifier]=self.pool.submit(work)
            return self.view(identifier)

    def propose(self,identifier,intervention):
        value=Intervention.model_validate(intervention).model_dump()
        with self.lock:
            e=self._load(identifier); self._check_mutation(e); b=e['branches'][e['active']]
            if b['approval']:
                raise Conflict('This branch already delivered its approved correction. Fork a new branch to test changed copy.')
            b['revision']+=1
            digest=hashlib.sha256(canonical({'episode':identifier,'branch':e['active'],'revision':b['revision'],'intervention':value}).encode()).hexdigest()
            b['pending']={'revision':b['revision'],'content_hash':digest,'intervention':value,**value}
            b['approval']=None
            self._touch(e);return self.view(identifier)

    def approve(self,identifier,revision,content_hash):
        with self.lock:
            e=self._load(identifier);self._check_mutation(e);b=e['branches'][e['active']]
            pending=b['pending']
            if not pending or pending['revision']!=revision or pending['content_hash']!=content_hash:
                raise Conflict('Approval does not match the displayed correction revision')
            if b['approval']:return self.view(identifier)
            if b['sim'].round != 2:
                raise Conflict('Approval is available at the two-round decision point')
            value=pending['intervention']
            if e['mode']=='replay':
                expected=e['recording'].get('intervention')
                if expected!=value:raise Conflict('Replay requires the recorded correction; use a new live or fixture run to edit')
            else:
                b['sim'].intervene({**value,'text_es':value['text_es'] or ''})
            b['approval']={'revision':revision,'content_hash':content_hash,'approved_at':time.time()}
            b['intervention']=copy.deepcopy(value)
            b['status']='ready' if b['sim'].round<4 else 'complete'
            self._touch(e);return self.view(identifier)

    def branch(self,identifier,kind,name=None,intervention=None):
        if kind not in {'none','correction'}:raise ValueError('Branch kind must be none or correction')
        if kind=='correction':
            if not intervention:raise ValueError('Correction branch requires proposed copy')
            intervention=Intervention.model_validate(intervention).model_dump()
        with self.lock:
            e=self._load(identifier);self._check_mutation(e)
            if e['mode']=='replay':raise Conflict('Recorded trajectories cannot generate uncomputed branches')
            source=e['branches'][e['active']]
            # All counterfactuals originate at the same recorded pre-intervention decision point.
            if len(source['history'])<3:raise Conflict('Reach the two-round decision point before forking')
            branch_id='branch-'+uuid4().hex[:8]
            sim=Simulation.from_state(source['history'][2]).fork(branch_id)
            sim.evidence=copy.deepcopy(e['evidence'] or {})
            b=self._branch(sim);b['history']=copy.deepcopy(source['history'][:3])
            b['no_intervention']=kind=='none'
            e['branches'][branch_id]=b;e['active']=branch_id
            if kind=='correction':
                self.propose(identifier,intervention)
                b['status']='awaiting_approval'
            self._touch(e);return self.view(identifier)

    def select(self,identifier,branch_id):
        with self.lock:
            e=self._load(identifier);self._check_mutation(e)
            if branch_id not in e['branches']:raise KeyError(branch_id)
            e['active']=branch_id;self._touch(e);return self.view(identifier)

    def record(self,identifier):
        with self.lock:
            e=self._load(identifier);self._check_mutation(e);b=e['branches'][e['active']]
            if b['sim'].round<4:raise Conflict('Only completed four-round trajectories can be recorded')
            rid=str(uuid4())
            value={'id':rid,'source_mode':e['mode'],'name':f'{e["mode"]} · {e["active"]} · {rid[:8]}',
                   'states':b['history'],'drafts':e['drafts'],'evidence':e['evidence'],'scout':e['scout'],'intervention':b['intervention']}
            (self.directory/'recordings'/(rid+'.json')).write_text(canonical(value))
            return {**self.view(identifier),'recording_id':rid}

    def replies(self,identifier,questions=None):
        with self.lock:
            e=self._load(identifier);self._check_mutation(e);b=e['branches'][e['active']]
            if e['mode']=='replay':raise Conflict('Replay cannot generate new replies')
            if not b['approval']:raise Conflict('Approve the correction before generating replies')
            if questions is None:
                questions=[{'id':p['id'],'text':p['text'],'language':p['language']} for p in b['sim'].feed if p['kind'] in {'question','reply'}][-20:]
            questions=[ReplyQuestion.model_validate(q).model_dump() for q in questions]
            if len(questions)>20 or len({q['id'] for q in questions})!=len(questions):
                raise ValueError('Use up to twenty uniquely identified questions')
            if not questions:
                b['broadcast']={'status':'not_requested','replies':[]};self._touch(e);return self.view(identifier)
            value=b['intervention'];evidence=e['evidence'] or {}
            observation={'approved':True,'framing_key':value['framing_key'],'post_en':value['text_en'],'post_es':value['text_es'],
                         'verified_facts':evidence.get('verified_facts',[]),'official_source':evidence.get('official_source','https://www.readysandiego.org/'),
                         'questions':questions}
            def apply(payload):
                result=BroadcasterReplies.model_validate(payload).model_dump()
                if {r['question_id'] for r in result['replies']} != {q['id'] for q in questions} or len(result['replies'])!=len(questions):
                    raise ValueError('Broadcaster must answer every question ID exactly once')
                b['broadcast']={'status':'done',**result};self._touch(e)
            if e['mode']=='fixture':
                apply({'replies':[{'question_id':q['id'],'text':'Consulta las fuentes oficiales para los avisos actuales.' if q['language']=='es' else 'Please check the official source for current updates.'} for q in questions]})
            else:
                previous=b['status'];b['status']='running';self._touch(e)
                def work():
                    try:
                        payload=self._native(e,'broadcast',0,observation)
                        with self.lock:apply(payload);b['status']=previous;self._touch(e)
                    except Exception as exc:
                        with self.lock:
                            b['status']='error';e['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__;self._touch(e)
                self.workers[identifier]=self.pool.submit(work)
            return self.view(identifier)

    def recordings(self):
        return [{'id':v['id'],'name':v['name'],'source_mode':v['source_mode']} for p in sorted((self.directory/'recordings').glob('*.json')) for v in [json.loads(p.read_text())]]

    def _read_recording(self,identifier):
        if not identifier or any(c not in '0123456789abcdef-' for c in identifier):raise KeyError('Unknown recording')
        path=self.directory/'recordings'/(identifier+'.json')
        if not path.exists():raise KeyError('Unknown recording')
        return json.loads(path.read_text())

"""Episode-bound Gemini evidence, evidence requests and Voiskey/Gemini editing."""
import asyncio
import copy
import hashlib
from uuid import uuid4

from . import config, pipeline
from .gemini_schemas import EditorOut
from .schemas import Framing


async def gemini_job(factory):
    from .clients.gemini_client import session
    async with session():return await factory()


class EpisodeEvidence:
    def _evidence_guard(self,e):
        from .society_service import Conflict
        self._check_mutation(e)
        if e['mode']=='replay':raise Conflict('Replay retains its recorded evidence and editor copy')
        if any(b['approval'] for b in e['branches'].values()):
            raise Conflict('Approved evidence and copy are frozen; create a new episode to analyze or edit')

    def analyze(self,identifier,image=None,mime='image/png'):
        with self.lock:
            e=self._load(identifier);self._evidence_guard(e)
            config.refresh_gemini_settings()
            uploaded=image is not None
            live=e['mode']=='live' or uploaded
            if live and not config.GEMINI_API_KEY:
                from .society_service import Conflict
                raise Conflict('Add GEMINI_API_KEY to .env before live image analysis')
            image=image if uploaded else (config.DATA/'viral.png').read_bytes()
            digest=hashlib.sha256(image).hexdigest()
            if uploaded:
                # Store only validated raster bytes; no user-controlled path or HTML.
                folder=self.directory/'uploads';folder.mkdir(exist_ok=True)
                ext={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/gif':'.gif'}[mime]
                file=folder/(digest+ext);file.write_bytes(image);file.chmod(0o600)
                image_url='/api/media/'+file.name
            else:image_url='/data/viral.png'
            context=__import__('json').loads((config.DATA/'gemini_scenario_sd1024.json').read_text())['context']
            if uploaded:context={k:v for k,v in context.items() if k in {'date','agencies'}}
            b=e['branches'][e['active']];previous=b['status'];b['status']='running'
            operation=uuid4().hex;e['analysis']={'id':operation,'status':'running','stages':{},'image_url':image_url,'source':'gemini' if live else 'fixture'}
            self._touch(e)
            def progress(stages):
                with self.lock:
                    e['analysis']['stages']=stages;self._touch(e)
            def work():
                try:
                    def task():return asyncio.wait_for(pipeline.analyze(image,mime,self.scenario['claim'],context,live=live,progress=progress),config.TIMEOUTS['analyze'])
                    packet=asyncio.run(gemini_job(task) if live else task())
                    with self.lock:
                        packet.update(incident_id=self.scenario['incident_id'],revision=(e.get('evidence') or {}).get('revision',0)+1,image_url=image_url)
                        e['evidence']=packet;e['drafts']=None;e['editor']=None;e['editor_status']=None
                        for branch in e['branches'].values():
                            branch['sim'].evidence=copy.deepcopy(packet);branch['pending']=None
                        e['analysis'].update(status='done');b['status']=previous;self._touch(e)
                except Exception as exc:
                    with self.lock:
                        e['analysis'].update(status='error',error=f'Gemini analysis failed ({type(exc).__name__}). Check credentials or quota and retry.')
                        e['analysis']['stages']={k:('error' if v=='running' else v) for k,v in e['analysis']['stages'].items()}
                        b['status']=previous;self._touch(e)
            self.workers[identifier]=self.pool.submit(work)
            return self.view(identifier)

    def voice(self,identifier,text,framing_key='B',source='',audio=None,mime=None):
        with self.lock:
            e=self._load(identifier);self._evidence_guard(e)
            if not audio and (not isinstance(text,str) or not text.strip()):raise ValueError('Supply a dictation note or audio')
            if text and len(text)>12000:raise ValueError('Dictation note exceeds 12000 characters')
            drafts=(e['drafts'] or {}).get('framings',[])
            framing=next((f for f in drafts if f['key']==framing_key),None)
            if not framing:raise ValueError('Choose a generated framing before processing dictation')
            framing=Framing.model_validate(framing)
            config.refresh_gemini_settings()
            if (e['mode']=='live' or audio) and not config.GEMINI_API_KEY:
                from .society_service import Conflict
                raise Conflict('Add GEMINI_API_KEY to .env before processing live dictation')
            b=e['branches'][e['active']];previous=b['status'];b['status']='running'
            e['editor_status']={'status':'running'};self._touch(e)
            def work():
                try:
                    if e['mode']=='fixture' and not audio:
                        result=pipeline.fixture('editor_demo',EditorOut)
                        provenance='fixture'
                    else:
                        from .agents import editor
                        result=asyncio.run(gemini_job(lambda:asyncio.wait_for(editor.run(framing,self.scenario['claim'],audio=audio,mime=mime,text=text,
                                                                     want_es=True,voiskey_clean=source=='voiskey'),config.TIMEOUTS['editor'])))
                        provenance='gemini'
                    with self.lock:
                        e['editor']={**result.model_dump(),'source':provenance,'framing_key':framing.key};e['editor_status']={'status':'done'}
                        # Spoken approve is an interpretation, never authority to publish.
                        b['pending']=None;b['status']=previous;self._touch(e)
                except Exception as exc:
                    with self.lock:
                        e['editor_status']={'status':'error','error':f'Dictation processing failed ({type(exc).__name__}). Review the note and retry.'}
                        b['status']=previous;self._touch(e)
            self.workers[identifier]=self.pool.submit(work)
            return self.view(identifier)

    def draft_ask(self,identifier,item,target):
        if not isinstance(item,str) or not item.strip() or len(item)>280 or not isinstance(target,str) or not target.strip() or len(target)>120:
            raise ValueError('Supply a short evidence item and recipient')
        with self.lock:
            e=self._load(identifier);self._check_mutation(e);mode=e['mode']
        from .agents import draft_ask
        status='template'
        if mode=='live':
            try:
                config.refresh_gemini_settings()
                if not config.GEMINI_API_KEY:raise ValueError('Gemini key is missing')
                result=asyncio.run(gemini_job(lambda:asyncio.wait_for(draft_ask.run(item,target,self.scenario['claim']),config.TIMEOUTS['draft_ask'])))
                status='gemini'
            except Exception:result=draft_ask.template(item,target)
        else:result=draft_ask.template(item,target)
        return {'text':result.text,'source':status,'sent':False}

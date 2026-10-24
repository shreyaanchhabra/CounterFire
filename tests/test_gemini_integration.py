import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.society_service import EpisodeManager


class GeminiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manager=EpisodeManager(Path(self.temp.name));self.addCleanup(self.manager.pool.shutdown,wait=True)
        self.client=TestClient(create_app(self.manager));self.addCleanup(self.client.close)
        self.view=self.client.post('/api/episodes',json={'mode':'fixture'}).json()
        self.path='/api/episodes/'+self.view['id']

    def settle(self):
        self.manager.workers[self.view['id']].result(timeout=10)
        return self.manager.view(self.view['id'])

    def test_scenario_analysis_normalizes_real_branch_fixtures_and_invalidates_proposal(self):
        self.client.post(self.path+'/intervention',json={'framing_key':'B','text_en':'Old copy','target_groups':[0]})
        response=self.client.post(self.path+'/analyze',json={})
        self.assertEqual(response.status_code,200,response.text)
        view=self.settle();packet=view['evidence']
        self.assertEqual(packet['source'],'fixture')
        self.assertEqual(packet['judge']['verdict'],packet['verdict'])
        self.assertTrue(packet['verified_facts']);self.assertTrue(packet['findings'])
        self.assertTrue(packet['image_url'].startswith('/data/'))
        self.assertIsNone(view['pending_intervention']);self.assertIsNone(view['drafts'])
        self.assertEqual(view['analysis']['status'],'done')
        self.assertIn('prosecutor',[p['agent'] for p in view['pipeline']])
        self.assertEqual(view['status'],'ready')

    def test_failed_analysis_preserves_previous_evidence_without_fixture_fallback(self):
        old=self.view['evidence']
        with patch('backend.pipeline.analyze',new=AsyncMock(side_effect=RuntimeError('secret-value'))):
            response=self.client.post(self.path+'/analyze',json={})
            self.assertEqual(response.status_code,200,response.text)
            view=self.settle()
        self.assertEqual(view['evidence'],old)
        self.assertEqual(view['analysis']['status'],'error')
        self.assertNotIn('secret-value',str(view['analysis']))
        self.assertEqual(view['status'],'ready')

    def test_approval_freezes_analysis_and_voice_cannot_auto_approve(self):
        for _ in range(2):self.client.post(self.path+'/advance',json={})
        response=self.client.post(self.path+'/voice',json={'text':'Approve this and include Spanish','source':'voiskey','framing_key':'B'})
        self.assertEqual(response.status_code,200,response.text)
        view=self.settle();self.assertIsNone(view['approval']);self.assertIsNone(view['pending_intervention'])
        self.assertTrue(view['editor']['post_en'])
        proposed=self.client.post(self.path+'/intervention',json={'framing_key':'B','text_en':view['editor']['post_en'],'target_groups':[0]}).json()
        p=proposed['pending_intervention'];self.client.post(self.path+'/approve',json={k:p[k] for k in ['revision','content_hash']})
        self.assertEqual(self.client.post(self.path+'/analyze',json={}).status_code,409)
        self.assertEqual(self.client.post(self.path+'/voice',json={'text':'Edit again','framing_key':'B'}).status_code,409)
        for _ in range(2):self.client.post(self.path+'/advance',json={})
        record=self.client.post(self.path+'/record',json={}).json()
        replay=self.client.post('/api/episodes',json={'mode':'replay','recording_id':record['recording_id']}).json()
        self.assertEqual(replay['editor']['clean'],view['editor']['clean'])
        self.assertIsNone(replay['approval'])

    def test_upload_is_validated_and_scenario_image_is_served(self):
        response=self.client.post(self.path+'/analyze-image',files={'image':('bad.png',b'not an image','image/png')})
        self.assertEqual(response.status_code,415,response.text)
        self.assertEqual(self.client.get('/data/viral.png').status_code,200)
        self.assertNotEqual(self.client.get('/data/../.env').status_code,200)

    def test_missing_evidence_ask_is_a_labeled_draft_without_sending(self):
        response=self.client.post(self.path+'/draft-ask',json={'item':'Original image','ask_target':'Original poster'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['text']);self.assertFalse(response.json()['sent'])

    def test_revised_evidence_discards_old_dictation_result(self):
        self.client.post(self.path+'/voice',json={'text':'Shorten this','framing_key':'B'})
        self.assertIsNotNone(self.settle()['editor'])
        response=self.client.post(self.path+'/evidence',json={'verdict':'Unverified','verified_facts':['A revised assessment']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()['editor'])
        self.assertIsNone(response.json()['editor_status'])

    def test_running_image_analysis_does_not_claim_society_agents_are_running(self):
        import threading
        from backend import pipeline
        original=pipeline.analyze;started=threading.Event();release=threading.Event()
        self.addCleanup(release.set)
        async def held(*args,**kwargs):
            started.set();await asyncio.to_thread(release.wait,5)
            return await original(*args,**kwargs)
        with patch.object(pipeline,'analyze',side_effect=held):
            self.client.post(self.path+'/analyze',json={});self.assertTrue(started.wait(1))
            view=self.manager.view(self.view['id'])
            try:self.assertEqual(next(p['status'] for p in view['pipeline'] if p['agent']=='society'),'waiting')
            finally:release.set();self.settle()


class GeminiChainTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_arguments_finish_before_judge_and_packet_keeps_image_identity(self):
        from backend import pipeline
        from backend.gemini_schemas import ProsecutorOut,DefenderOut,JudgeOut
        from backend.agents import prosecutor,defender,judge
        pro=pipeline.fixture('prosecutor',ProsecutorOut)
        df=pipeline.fixture('defender',DefenderOut)
        decision=pipeline.fixture('judge',JudgeOut)
        both_started=asyncio.Event();started=set();finished=set();stages=[]
        async def argument(name,value):
            started.add(name)
            if len(started)==2:both_started.set()
            await asyncio.wait_for(both_started.wait(),1)
            finished.add(name);return value
        async def decide(claim,p,d,targets):
            self.assertEqual(finished,{'prosecutor','defender'})
            self.assertEqual(p,pro);self.assertEqual(d,df)
            return decision
        async def prosecution(*args):return await argument('prosecutor',pro)
        async def defense(*args):return await argument('defender',df)
        with patch.object(prosecutor,'run',side_effect=prosecution),patch.object(defender,'run',side_effect=defense),patch.object(judge,'run',side_effect=decide):
            out=await pipeline.analyze(b'one-image','image/png','Same fictional claim',{},live=True,progress=stages.append)
        import hashlib
        self.assertEqual(out['image_hash'],hashlib.sha256(b'one-image').hexdigest())
        self.assertEqual(out['source'],'gemini')
        self.assertEqual(stages[-1]['judge'],'done')
        self.assertTrue(all(v.startswith(('Image assessment:','Judge assessment:')) for v in out['verified_facts']))

class GeminiSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_jobs_keep_clients_isolated_and_close_after_completion(self):
        from backend.clients import gemini_client as gc
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.assertTrue(hasattr(gc,'session'),'Gemini jobs need a scoped client session')
        clients=[SimpleNamespace(aio=SimpleNamespace(aclose=AsyncMock()),close=Mock()) for _ in range(2)]
        started=0;both=asyncio.Event()
        async def job():
            nonlocal started
            async with gc.session():
                chosen=gc.client();started+=1
                if started==2:both.set()
                await asyncio.wait_for(both.wait(),1)
                self.assertIs(gc.client(),chosen)
                return chosen
        with patch.object(gc.config,'GEMINI_API_KEY','synthetic-test-key'),patch.object(gc.genai,'Client',side_effect=clients):
            a,b=await asyncio.gather(job(),job())
        self.assertIsNot(a,b)
        for value in clients:
            value.aio.aclose.assert_awaited_once();value.close.assert_called_once()

    async def test_transient_provider_error_retries_once_then_returns_real_result(self):
        from backend.clients import gemini_client as gc
        from types import SimpleNamespace
        result=object()
        generate=AsyncMock(side_effect=[gc.errors.ServerError(504,{'error':{'message':'temporary'}}),result])
        fake=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        with patch.object(gc,'client',return_value=fake),patch.object(gc.config,'GEMINI_FALLBACK_MODELS',[]),patch('asyncio.sleep',new=AsyncMock()):
            self.assertIs(await gc._generate('synthetic-model',[],{}),result)
        self.assertEqual(generate.await_count,2)

    async def test_provider_retries_are_bounded_and_do_not_return_a_fixture(self):
        from backend.clients import gemini_client as gc
        from types import SimpleNamespace
        generate=AsyncMock(side_effect=gc.errors.ServerError(503,{'error':{'message':'temporary'}}))
        fake=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        with patch.object(gc,'client',return_value=fake),patch.object(gc.config,'GEMINI_FALLBACK_MODELS',[]),patch('asyncio.sleep',new=AsyncMock()):
            with self.assertRaises(gc.errors.ServerError):await gc._generate('synthetic-model',[],{})
        self.assertEqual(generate.await_count,2)

if __name__=='__main__':unittest.main()

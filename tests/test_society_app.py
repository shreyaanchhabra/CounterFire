import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.society_service import EpisodeManager


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = EpisodeManager(Path(self.temp.name))
        self.client = TestClient(create_app(self.manager))
        self.addCleanup(self.client.close)

    def post(self, path, data=None):
        response = self.client.post(path, json=data or {})
        self.assertLess(response.status_code, 300, response.text)
        return response.json()

    def create(self):
        return self.post('/api/episodes', {'mode': 'fixture'})

    def advance(self, episode):
        return self.post(f'/api/episodes/{episode["id"]}/advance')

    def decision_point(self):
        view = self.advance(self.advance(self.create()))
        self.assertEqual(view['round'], 2)
        self.assertEqual(view['status'], 'awaiting_approval')
        return view

    def propose(self, view, text='Check official updates before sharing.'):
        return self.post(f'/api/episodes/{view["id"]}/intervention', {
            'framing_key': 'B', 'text_en': text, 'text_es': 'Consulta los avisos oficiales.',
            'target_groups': [0, 1, 2]})

    def test_entire_episode_requires_exact_approval_and_reaches_completion(self):
        view = self.decision_point()
        path = f'/api/episodes/{view["id"]}'
        self.assertEqual(self.client.post(path+'/advance', json={}).status_code, 409)
        view = self.propose(view)
        pending = view['pending_intervention']
        self.assertEqual(self.client.post(path+'/approve',json={'revision':pending['revision'],'content_hash':'wrong'}).status_code,409)
        view = self.post(path+'/approve', {k:pending[k] for k in ['revision','content_hash']})
        count = len(view['feed'])
        duplicate = self.post(path+'/approve', {k:pending[k] for k in ['revision','content_hash']})
        self.assertEqual(len(duplicate['feed']),count)
        self.assertEqual(self.advance(self.advance(view))['status'],'complete')

    def test_edit_invalidates_old_approval(self):
        view=self.propose(self.decision_point())
        old=view['pending_intervention']
        self.propose(view,'An edited correction.')
        response=self.client.post(f'/api/episodes/{view["id"]}/approve',json={k:old[k] for k in ['revision','content_hash']})
        self.assertEqual(response.status_code,409)

    def test_counterfactual_branch_does_not_change_main_state(self):
        view=self.decision_point()
        base=list(view['frames'][-1]['states'])
        fork=self.post(f'/api/episodes/{view["id"]}/branch',{'kind':'none','name':'No correction'})
        self.assertNotEqual(fork['branch_id'],'main')
        self.advance(fork)
        main=self.post(f'/api/episodes/{view["id"]}/select-branch',{'branch_id':'main'})
        self.assertEqual(main['round'],2)
        self.assertEqual(main['frames'][-1]['states'],base)

    def test_recording_replay_is_distinct_and_requires_fresh_approval(self):
        view=self.propose(self.decision_point())
        pending=view['pending_intervention']
        view=self.post(f'/api/episodes/{view["id"]}/approve',{k:pending[k] for k in ['revision','content_hash']})
        view=self.advance(self.advance(view))
        recording=self.post(f'/api/episodes/{view["id"]}/record')
        self.assertIn('recording_id', recording)
        replay=self.post('/api/episodes',{'mode':'replay','recording_id':recording['recording_id']})
        self.assertEqual(replay['mode'],'replay')
        self.assertIsNone(replay['approval'])
        self.assertEqual(replay['recorded_intervention'], pending['intervention'])
        replay=self.advance(self.advance(replay))
        self.assertEqual(replay['status'],'awaiting_approval')
        self.assertIsNone(replay['approval'])
        replay=self.post(f'/api/episodes/{replay["id"]}/intervention',replay['recorded_intervention'])
        fresh=replay['pending_intervention']
        replay=self.post(f'/api/episodes/{replay["id"]}/approve',{k:fresh[k] for k in ['revision','content_hash']})
        self.assertEqual(self.advance(self.advance(replay))['status'],'complete')

    def test_english_only_and_early_approval_guard(self):
        view=self.create();path=f'/api/episodes/{view["id"]}'
        view=self.post(path+'/intervention',{'framing_key':'B','text_en':'Check official updates.','target_groups':[0]})
        pending=view['pending_intervention']
        self.assertEqual(self.client.post(path+'/approve',json={k:pending[k] for k in ['revision','content_hash']}).status_code,409)
        self.advance(self.advance(view))
        approved=self.post(path+'/approve',{k:pending[k] for k in ['revision','content_hash']})
        self.assertIsNotNone(approved['approval'])

    def test_fork_preserves_current_evidence_and_invalid_fork_is_atomic(self):
        view=self.decision_point();path=f'/api/episodes/{view["id"]}'
        packet={'verdict':'Unverified','verified_facts':['Current bulletin'],'revision':9}
        self.post(path+'/evidence',packet)
        self.assertEqual(self.client.post(path+'/branch',json={'kind':'correction'}).status_code,422)
        self.assertEqual(len(self.manager.view(view['id'])['branches']),1)
        fork=self.post(path+'/branch',{'kind':'none'})
        self.assertEqual(self.manager.episodes[view['id']]['branches'][fork['branch_id']]['sim'].evidence,packet)

    def test_state_survives_reloading_manager_and_ui_is_served(self):
        view=self.advance(self.create())
        loaded=EpisodeManager(Path(self.temp.name)).view(view['id'])
        self.assertEqual(loaded['round'],1)
        self.assertEqual(loaded['frames'],view['frames'])
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertNotIn('GROKBOTS_WEBHOOK_KEY',self.client.get('/api/health').text)

    def test_invalid_evidence_does_not_replace_previous_packet(self):
        view=self.create();path=f'/api/episodes/{view["id"]}/evidence'
        for packet in [{'verdict':['False'],'verified_facts':[]},
                       {'verdict':'Misleading','verified_facts':[{}]},
                       {'verdict':'Misleading','verified_facts':['Fact'],'findings':{}}]:
            self.assertEqual(self.client.post(path,json=packet).status_code,422)
        self.assertEqual(self.manager.view(view['id'])['evidence'],view['evidence'])


if __name__=='__main__':
    unittest.main()

"""Native orchestration integration with a real durable callback inbox, offline."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.bot_contracts import result_schema
from backend.clients.grokbots_webhook import DispatchReceipt
from backend.grokbots_return import JobStore, create_app as create_callback_app
from backend.main import create_app
from backend.society_service import EpisodeManager


class NativeSocietyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.jobs = JobStore(root / 'jobs.sqlite3')
        self.callback_client = TestClient(create_callback_app(self.jobs))
        self.addCleanup(self.callback_client.close)
        self.manager = EpisodeManager(root / 'episodes', jobs=self.jobs)
        self.addCleanup(self.manager.pool.shutdown, wait=True)
        self.client = TestClient(create_app(self.manager))
        self.addCleanup(self.client.close)
        env = {'GROKBOTS_WEBHOOK_URL': 'https://example.invalid/comms',
               'GROKBOTS_WEBHOOK_KEY': 'test-comms-token',
               'GROKBOTS_CALLBACK_BASE_URL': 'https://callback.invalid',
               'GROKBOTS_TASK_TIMEOUT_SECONDS': '2'}
        for gid in range(6):
            env[f'GROKBOTS_GROUP_{gid}_URL'] = f'https://example.invalid/group/{gid}'
            env[f'GROKBOTS_GROUP_{gid}_KEY'] = f'test-group-{gid}'
        self.environment = env
        self.addCleanup(patch.stopall)
        patch('backend.society_service.environment', return_value=env).start()
        # Any hidden fixture fallback must fail the actual workflow.
        patch('backend.society_service.fixture_decisions', side_effect=AssertionError('Native fallback forbidden')).start()
        self.webhook = patch('backend.society_service.GrokBotsWebhookClient').start()
        self.webhook.return_value.send.side_effect = self.complete_send
        self.sent = []
        self.triggers = []
        self.sent_lock = threading.Lock()
        self.community_hook = None
        self.fail_kind = None

    def post(self, path, body=None):
        response = self.client.post(path, json=body or {})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def new_live(self):
        view = self.post('/api/episodes', {'mode': 'live'})
        self.assertEqual(view['mode'], 'live')
        self.assertIsNone(view['drafts'])
        self.assertIsNone(view['scout'])
        return view

    def finish(self, identifier):
        self.manager.workers[identifier].result(timeout=10)
        return self.manager.view(identifier)

    @staticmethod
    def decisions(observation):
        return {'group_id': observation['group_id'], 'decisions': [
            {'persona_id': p['persona_id'], 'action': 'wait', 'belief': p['belief']}
            for p in observation['personas']]}

    def complete_send(self, trigger, *, request_id):
        # Large observations travel through the capability-scoped task endpoint;
        # routine webhook context carries only the small pull instructions.
        self.assertEqual(set(trigger), {'task_url', 'callback', 'task_type'})
        self.assertEqual(set(trigger['callback']), {'url', 'token'})
        encoded_trigger = json.dumps(trigger)
        self.assertLess(len(encoded_trigger.encode()), 1024)
        self.assertNotIn('persona_id', encoded_trigger)
        self.assertNotIn('verified_facts', encoded_trigger)
        self.assertNotIn('Native test bulletin', encoded_trigger)
        self.assertEqual(trigger['task_url'], f'https://callback.invalid/api/tasks/{request_id}')
        self.assertEqual(trigger['callback']['url'], f'https://callback.invalid/api/results/{request_id}')
        path = '/api/tasks/' + request_id
        self.assertEqual(self.callback_client.get(path).status_code, 401)
        self.assertEqual(self.callback_client.get(path, headers={'Authorization': 'Bearer wrong-test-token'}).status_code, 401)
        response = self.callback_client.get(path, headers={
            'Authorization': 'Bearer ' + trigger['callback']['token']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        pulled = response.json()
        self.assertEqual(set(pulled), {'task', 'request_id', 'observation_hash', 'result_schema'})
        self.assertEqual(pulled['request_id'], request_id)
        self.assertNotIn(trigger['callback']['token'], response.text)
        self.assertEqual(pulled['task']['task_type'], trigger['task_type'])
        packet = {**pulled, 'callback': trigger['callback']}
        with self.sent_lock:
            self.triggers.append(copy.deepcopy(trigger))
        task = packet['task']
        kind = task['task_type']
        with self.sent_lock:
            self.sent.append(copy.deepcopy(packet))
        if self.fail_kind == kind:
            # A successful HTTP dispatch receipt without a callback is not success.
            return DispatchReceipt(request_id=request_id, delivery='accepted', http_status=200)
        observation = task['observation']
        if kind == 'community':
            payload = self.decisions(observation)
            if self.community_hook:
                payload = self.community_hook(packet, payload)
        elif kind == 'scout':
            payload = {'claim': 'Native selected claim', 'selected_post_ids': ['p01', 'p04'],
                       'summary': 'Native scout selected two source posts.'}
        elif kind == 'draft':
            payload = {'framings': [
                {'key': key, 'name': name, 'text_en': f'Native {key}: check the bulletin.',
                 'text_es': f'Nativo {key}: consulta el boletín.'}
                for key, name in [('A', 'Fact check'), ('B', 'Action first'), ('C', 'Neighbor voice')]]}
        elif kind == 'broadcast':
            payload = {'replies': [{'question_id': q['id'], 'text': 'Native reply: consult the approved bulletin.'}
                                   for q in observation['questions']]}
        else:
            raise AssertionError(f'Unexpected native task {kind}')
        envelope = {k: task[k] for k in ('episode_id', 'round_id', 'group_id')}
        envelope.update(request_id=request_id, observation_hash=packet['observation_hash'], payload=payload)
        schema = result_schema(kind)
        # Match the exact schema dispatched to the native routine, then authenticate
        # the matching capability against the real SQLite inbox.
        if packet['result_schema'] != schema.model_json_schema():
            raise AssertionError('Native routine received the wrong result schema')
        result = schema.model_validate(envelope)
        self.jobs.accept(request_id, packet['callback']['token'], result)
        return DispatchReceipt(request_id=request_id, delivery='accepted', http_status=200)

    def test_six_dispatches_wait_for_complete_callback_barrier_before_graph_delivery(self):
        view = self.new_live()
        identifier = view['id']
        before = self.manager.episodes[identifier]['branches']['main']['sim'].snapshot()
        blocked = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def hook(packet, payload):
            gid = packet['task']['group_id']
            if gid == 5:
                blocked.set()
                if not release.wait(5):
                    raise AssertionError('Test failed to release final callback')
            if gid == 2:
                persona = packet['task']['observation']['personas'][0]
                payload['decisions'][0].update(action='share', message='Native neighbor asks for confirmation.',
                                               parent_id=persona['messages'][0]['id'])
            return payload

        self.community_hook = hook
        self.post(f'/api/episodes/{identifier}/advance')
        self.assertTrue(blocked.wait(5))
        sim = self.manager.episodes[identifier]['branches']['main']['sim']
        self.assertEqual(sim.snapshot(), before)
        self.assertEqual(self.manager.view(identifier)['status'], 'running')
        release.set()
        final = self.finish(identifier)
        self.assertEqual(final['round'], 1)
        self.assertEqual(final['status'], 'ready')
        self.assertTrue(final['frames'][-1]['events'])
        self.assertEqual(final['feed'][-1]['text'], 'Native neighbor asks for confirmation.')
        community = [p for p in self.sent if p['task']['task_type'] == 'community']
        self.assertEqual(sorted(p['task']['group_id'] for p in community), list(range(6)))
        self.assertTrue(all(p['task']['round_id'] == 0 for p in community))
        self.assertTrue(all(self.jobs.get(p['callback']['url'].split('/')[-1])['status'] == 'completed' for p in community))
        self.assertEqual(final['pending_jobs'], [])

    def test_schema_valid_but_unowned_persona_rejects_entire_round_atomically(self):
        view = self.new_live()
        identifier = view['id']
        before = self.manager.episodes[identifier]['branches']['main']['sim'].export_state()

        def wrong_persona(packet, payload):
            if packet['task']['group_id'] == 5:
                payload['decisions'][0]['persona_id'] = 'g0-p0'
            return payload

        self.community_hook = wrong_persona
        self.post(f'/api/episodes/{identifier}/advance')
        final = self.finish(identifier)
        self.assertEqual(final['status'], 'error')
        self.assertEqual(final['round'], 0)
        self.assertIn('owned persona', final['error'])
        self.assertEqual(self.manager.episodes[identifier]['branches']['main']['sim'].export_state(), before)
        self.assertEqual(len([p for p in self.sent if p['task']['task_type'] == 'community']), 6)
        self.assertEqual(final['mode'], 'live')

    def test_native_scout_draft_and_broadcaster_routes_keep_typed_callback_outputs(self):
        view = self.new_live()
        identifier = view['id']
        path = f'/api/episodes/{identifier}'
        self.post(path + '/advance')
        view = self.finish(identifier)
        self.assertEqual(view['scout']['summary'], 'Native scout selected two source posts.')
        self.assertEqual(view['scout']['post_count'], 2)
        self.assertEqual(view['scout']['languages'], ['en', 'es'])
        scout_task = next(p for p in self.sent if p['task']['task_type'] == 'scout')
        self.assertEqual(len(scout_task['task']['observation']['posts']), 25)
        self.assertEqual(scout_task['task']['observation']['posts'][-1]['id'], 'p25')

        self.post(path + '/advance')
        self.assertEqual(self.finish(identifier)['status'], 'awaiting_approval')
        self.post(path + '/evidence', {'verdict': 'Unverified', 'verified_facts': ['Native test bulletin'], 'revision': 1})
        self.post(path + '/drafts')
        drafts = self.finish(identifier)['drafts']['framings']
        self.assertEqual([f['key'] for f in drafts], ['A', 'B', 'C'])
        self.assertEqual(drafts[1]['text_en'], 'Native B: check the bulletin.')
        proposed = self.post(path + '/intervention', {'framing_key': 'B', 'text_en': drafts[1]['text_en'],
                              'text_es': drafts[1]['text_es'], 'target_groups': [0, 1]})
        pending = proposed['pending_intervention']
        self.post(path + '/approve', {k: pending[k] for k in ('revision', 'content_hash')})
        self.post(path + '/replies', {'questions': [{'id': 'question-native', 'text': 'Where is the bulletin?', 'language': 'en'}]})
        final = self.finish(identifier)
        self.assertEqual(final['broadcast'], {'status': 'done', 'replies': [
            {'question_id': 'question-native', 'text': 'Native reply: consult the approved bulletin.'}]})
        self.assertEqual(final['status'], 'ready')
        broadcast = next(p for p in self.sent if p['task']['task_type'] == 'broadcast')['task']['observation']
        self.assertTrue(broadcast['approved'])
        self.assertEqual(broadcast['post_en'], drafts[1]['text_en'])
        self.assertEqual(broadcast['post_es'], drafts[1]['text_es'])
        self.post(path+'/drafts')
        self.assertEqual(self.finish(identifier)['status'],'ready')
        for _ in range(2):
            self.post(path+'/advance')
            self.finish(identifier)
        self.post(path+'/drafts')
        self.assertEqual(self.finish(identifier)['status'],'complete')

    def test_rejected_native_dispatch_preserves_simulation_and_never_uses_fixture(self):
        view = self.new_live()
        identifier = view['id']
        initial = self.manager.episodes[identifier]['branches']['main']['sim'].export_state()
        self.webhook.return_value.send.side_effect = lambda packet, request_id: DispatchReceipt(
            request_id=request_id, delivery='rejected', http_status=403)
        self.post(f'/api/episodes/{identifier}/advance')
        final = self.finish(identifier)
        self.assertEqual(final['status'], 'error')
        self.assertIn('rejected the request (HTTP 403)', final['error'])
        self.assertEqual(final['mode'], 'live')
        self.assertIsNone(final['scout'])
        self.assertEqual(self.manager.episodes[identifier]['branches']['main']['sim'].export_state(), initial)
        self.assertEqual(self.webhook.return_value.send.call_count, 1)

    def test_accepted_dispatch_without_callback_times_out_without_fixture_fallback(self):
        self.fail_kind = 'scout'
        self.environment['GROKBOTS_TASK_TIMEOUT_SECONDS'] = '0'
        view = self.new_live()
        identifier = view['id']
        initial = self.manager.episodes[identifier]['branches']['main']['sim'].export_state()
        self.post(f'/api/episodes/{identifier}/advance')
        final = self.finish(identifier)
        self.assertEqual(final['status'], 'error')
        self.assertIn('timed out', final['error'])
        self.assertEqual(final['mode'], 'live')
        self.assertIsNone(final['scout'])
        self.assertIsNone(final['drafts'])
        self.assertEqual(self.manager.episodes[identifier]['branches']['main']['sim'].export_state(), initial)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(final['pending_jobs']), 1)
        response = self.client.post(f'/api/episodes/{identifier}/advance', json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.sent), 1)


if __name__ == '__main__':
    unittest.main()

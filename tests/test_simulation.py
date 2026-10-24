"""Local-information and action-delivery invariants for the fictional society."""
import copy
import json
import unittest

from backend.simulation import Simulation


def waits(sim):
    return {g: {'group_id': g, 'decisions': [
        {'persona_id': p['persona_id'], 'action': 'wait', 'belief': p['belief']}
        for p in sim.observation(g)['personas']]} for g in range(6)}


class SimulationTests(unittest.TestCase):
    def test_reproducible_topology_and_persona_mapping(self):
        s = Simulation().snapshot()
        self.assertEqual(s, Simulation().snapshot())
        self.assertEqual(len(s['network']['groups']), 240)
        self.assertEqual(len(set(s['network']['persona_by_node'])), 20)
        self.assertEqual(s['frames'][0]['states'][80], 1)
        self.assertNotEqual(s['network']['edges'], Simulation(seed=8).snapshot()['network']['edges'])

    def test_private_evidence_and_other_personas_are_not_observed(self):
        sim = Simulation(evidence={'secret_fact': 'SECRET_SENTINEL'})
        for g in range(6):
            obs = sim.observation(g)
            self.assertNotIn('SECRET_SENTINEL', str(obs))
            self.assertTrue(all(p['group_id'] == g for p in obs['personas']))

    def test_incomplete_or_invalid_round_is_atomic(self):
        sim = Simulation()
        before = sim.snapshot()
        with self.assertRaises(ValueError):
            sim.apply_round({0: waits(sim)[0]})
        actions = waits(sim)
        actions[5]['decisions'][0]['persona_id'] = actions[0]['decisions'][0]['persona_id']
        with self.assertRaises(ValueError):
            sim.apply_round(actions)
        self.assertEqual(before, sim.snapshot())

    def test_no_information_cannot_change_belief(self):
        sim = Simulation()
        actions = waits(sim)
        actions[0]['decisions'][0]['belief'] = .3
        with self.assertRaises(ValueError):
            sim.apply_round(actions)
        self.assertEqual(sim.snapshot()['round'], 0)

    def test_share_delivers_only_along_edges_and_wait_does_not(self):
        sim = Simulation()
        actions = waits(sim)
        p = sim.observation(2)['personas'][0]
        actions[2]['decisions'][0].update(action='share', message='Check this report', parent_id=p['messages'][0]['id'])
        state = sim.apply_round(actions)
        events = state['frames'][-1]['events']
        self.assertTrue(events)
        edges = {tuple(sorted(edge)) for edge in state['network']['edges']}
        self.assertTrue(all(tuple(sorted((e['from'], e['to']))) in edges for e in events))
        self.assertEqual(state['feed'][-1]['parent_id'], p['messages'][0]['id'])
        sim.apply_round(waits(sim))
        self.assertEqual(sim.snapshot()['frames'][-1]['events'], [])

    def test_verify_reveals_evidence_next_round_only_to_requester(self):
        sim = Simulation(evidence={'verified_facts': ['SECRET_SENTINEL'], 'sources': [{'id':'source-local'}]})
        actions = waits(sim)
        actions[4]['decisions'][0]['action'] = 'verify'
        self.assertNotIn('SECRET_SENTINEL', str(sim.observation(4)))
        sim.apply_round(actions)
        obs = sim.observation(4)
        self.assertIn('SECRET_SENTINEL', str(obs['personas'][0]['messages']))
        self.assertNotIn('SECRET_SENTINEL', str(obs['personas'][1]['messages']))
        self.assertNotIn('SECRET_SENTINEL', str(sim.observation(0)))
        self.assertNotIn('SECRET_SENTINEL', str(sim.snapshot()['feed']))

    def test_verification_without_facts_produces_no_information_or_correction(self):
        for evidence in ({}, {'verdict': 'False', 'verified_facts': []},
                         {'verdict': 'False', 'verified_facts': ['  ']}):
            with self.subTest(evidence=evidence):
                sim = Simulation(evidence=evidence)
                actions = waits(sim)
                actions[4]['decisions'][0]['action'] = 'verify'
                result = sim.apply_round(actions)
                persona = sim.observation(4)['personas'][0]
                self.assertEqual(persona['messages'], [])
                self.assertFalse(persona['accepted_correction'])
                self.assertEqual(result['groups'][4]['corrected'], 0)
                feedback = next(f for f in result['feedback'] if f['persona_id'] == persona['persona_id'])
                self.assertEqual(feedback['verification'], 1)
                self.assertIsNone(feedback['message_id'])
                self.assertIsNone(feedback['accuracy'])
                actions = waits(sim)
                actions[4]['decisions'][0]['belief'] = .3
                with self.assertRaises(ValueError):
                    sim.apply_round(actions)

    def test_accuracy_uses_only_prior_comprehended_evidence_verdict(self):
        cases = [('False', .35, 1), ('False', .65, -1),
                 ('Misleading', .35, 1), ('Misleading', .65, -1),
                 ('True', .65, 1), ('True', .5, 1), ('True', .35, -1),
                 ('False', .5, -1),
                 ('Unverified', .35, None), (None, .65, None)]
        for verdict, belief, expected in cases:
            with self.subTest(verdict=verdict, belief=belief):
                sim = Simulation(evidence={'verdict': verdict, 'verified_facts': ['Fictional finding']})
                actions = waits(sim)
                actions[2]['decisions'][0]['action'] = 'verify'
                first = sim.apply_round(actions)
                self.assertTrue(all(f['accuracy'] is None for f in first['feedback']))
                actions = waits(sim)
                actions[2]['decisions'][0]['belief'] = belief
                final = sim.apply_round(actions)
                feedback = next(f for f in final['feedback'] if f['round'] == 2 and f['persona_id'] == 'g2-p0')
                self.assertEqual(feedback['accuracy'], expected)
                self.assertTrue(all(f['accuracy'] is None for f in final['feedback'] if f['group_id'] != 2))

    def test_global_evidence_edit_does_not_change_accuracy_until_persona_verifies(self):
        sim = Simulation(evidence={'verdict': 'False', 'verified_facts': ['First finding']})
        actions = waits(sim)
        actions[2]['decisions'][0]['action'] = 'verify'
        sim.apply_round(actions)
        sim.evidence = {'verdict': 'True', 'verified_facts': ['Revised finding']}
        actions = waits(sim)
        actions[2]['decisions'][0]['belief'] = .35
        final = sim.apply_round(actions)
        self.assertEqual(next(f for f in final['feedback'] if f['round'] == 2 and f['persona_id'] == 'g2-p0')['accuracy'], 1)
        actions = waits(sim)
        actions[2]['decisions'][0]['action'] = 'verify'
        sim.apply_round(actions)
        final = sim.apply_round(waits(sim))
        self.assertEqual(next(f for f in final['feedback'] if f['round'] == 4 and f['persona_id'] == 'g2-p0')['accuracy'], -1)

    def test_uncomprehended_verification_does_not_reveal_accuracy(self):
        sim = Simulation(evidence={'verdict': 'False', 'verified_facts': ['English-only finding']})
        actions = waits(sim)
        actions[1]['decisions'][0]['action'] = 'verify'
        sim.apply_round(actions)
        final = sim.apply_round(waits(sim))
        self.assertTrue(all(f['accuracy'] is None for f in final['feedback']))

    def test_language_blocks_belief_change_and_intervention_does_not_force_acceptance(self):
        sim = Simulation()
        before = [p['belief'] for p in sim.observation(1)['personas']]
        sim.intervene({'text_en':'Evidence corrected the rumor', 'target_groups':[1], 'framing_key':'A'})
        self.assertEqual(before, [p['belief'] for p in sim.observation(1)['personas']])
        self.assertEqual(sim.snapshot()['groups'][1]['corrected'], 0)
        actions = waits(sim)
        actions[1]['decisions'][0]['belief'] = .1
        with self.assertRaises(ValueError):
            sim.apply_round(actions)
        self.assertFalse(sim.observation(1)['personas'][0]['messages'][-1]['comprehensible'])

    def test_bilingual_correction_allows_bounded_change_and_branch_isolation(self):
        sim = Simulation()
        branch = sim.fork('correction')
        branch.intervene({'text_en':'Correction', 'text_es':'Corrección', 'target_groups':[1], 'framing_key':'B'})
        actions = waits(branch)
        actions[1]['decisions'][0]['belief'] = .3
        branch.apply_round(actions)
        self.assertEqual(sim.snapshot()['round'], 0)
        self.assertEqual(len(sim.snapshot()['feed']), 1)
        self.assertEqual(branch.snapshot()['branch_id'], 'correction')
        actions = waits(branch)
        actions[1]['decisions'][0]['belief'] = 1
        with self.assertRaises(ValueError):
            branch.apply_round(actions)

    def test_correction_delivery_requires_decision_before_acceptance(self):
        sim = Simulation()
        sim.intervene({'text_en': 'Correction', 'target_groups': [0]})
        self.assertEqual(sim.snapshot()['groups'][0]['corrected'], 0)
        sim.apply_round(waits(sim))
        self.assertEqual(sim.snapshot()['groups'][0]['corrected'], 0)

    def test_social_post_budget_is_enforced_before_mutation(self):
        sim = Simulation()
        actions = waits(sim)
        actions[2]['decisions'][0].update(action='share', message='x' * 281,
            parent_id=sim.observation(2)['personas'][0]['messages'][0]['id'])
        with self.assertRaises(ValueError): sim.apply_round(actions)
        self.assertEqual(sim.snapshot()['round'], 0)

    def test_json_state_roundtrip_retains_private_information_and_future_behavior(self):
        sim = Simulation(evidence={'verified_facts': ['private finding']})
        actions = waits(sim)
        actions[4]['decisions'][0]['action'] = 'verify'
        sim.apply_round(actions)
        restored = Simulation.from_state(json.loads(json.dumps(sim.export_state())))
        self.assertEqual(sim.snapshot(), restored.snapshot())
        self.assertEqual(sim.observation(4), restored.observation(4))
        self.assertEqual(sim.apply_round(waits(sim)), restored.apply_round(waits(restored)))
        branch = restored.fork('other')
        branch.intervene({'text_en': 'Correction', 'target_groups': [0]})
        self.assertNotEqual(restored.snapshot()['feed'], branch.snapshot()['feed'])

    def test_retraction_reaches_only_prior_recipients_and_feedback_is_local(self):
        sim = Simulation()
        actions = waits(sim)
        parent = sim.observation(2)['personas'][0]['messages'][0]['id']
        actions[2]['decisions'][0].update(action='share', message='Unverified claim', parent_id=parent)
        sim.apply_round(actions)
        first = {e['to'] for e in sim.snapshot()['frames'][-1]['events']}
        self.assertTrue(first)
        self.assertTrue(all(f['accuracy'] is None for f in sim.snapshot()['feedback']))
        actions = waits(sim)
        actions[2]['decisions'][0].update(action='retract', message='I retract my earlier share', parent_id=parent)
        sim.apply_round(actions)
        events = sim.snapshot()['frames'][-1]['events']
        self.assertTrue(events)
        self.assertTrue(all(e['kind'] == 'retract' and e['to'] in first for e in events))
        self.assertTrue(all(f['group_id'] == 0 for f in sim.observation(0)['feedback']))

    def test_current_round_share_cannot_authorize_another_current_decision(self):
        sim = Simulation()
        actions = waits(sim)
        actions[2]['decisions'][0].update(action='share', message='Rumor',
            parent_id=sim.observation(2)['personas'][0]['messages'][0]['id'])
        actions[0]['decisions'][0]['belief'] = .2
        before = sim.snapshot()
        with self.assertRaises(ValueError): sim.apply_round(actions)
        self.assertEqual(sim.snapshot(), before)

    def test_unknown_parent_and_duplicate_persona_rejected(self):
        sim = Simulation()
        actions = waits(sim)
        actions[2]['decisions'][0].update(action='share', message='hello', parent_id='unknown')
        with self.assertRaises(ValueError): sim.apply_round(actions)
        actions = waits(sim)
        actions[2]['decisions'].append(copy.deepcopy(actions[2]['decisions'][0]))
        with self.assertRaises(ValueError): sim.apply_round(actions)


if __name__ == '__main__': unittest.main()

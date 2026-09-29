import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import workspace_action_contract as contract
import workspace_format_study as study
import workspace_study as old
import workspace_env as envmod
import workspace_tasks as policy


def scenario():
    material, variant = old.materials()[0]
    source = {'family_id': material['family_id'], 'kind': 'synthetic', 'split': 'development',
              'variants': [variant], 'mechanism': 'research_workspace'}
    return old.batch.scenario_for({'max_steps': 48}, source, material, variant)


class ActionContractTests(unittest.TestCase):
    def test_missing_reason_does_not_block_valid_action(self):
        for extra, missingness in [({}, 'omitted'), ({'decision_summary': None}, 'explicit_null'),
                                   ({'decision_summary': ''}, 'empty'), ({'decision_summary': 'Read policy.'}, None)]:
            parsed = contract.parse_output(json.dumps({'tool': 'read', 'args': {'document_id': 'policy'}, **extra}))
            self.assertTrue(parsed['accepted'])
            self.assertEqual(parsed['decision_summary_missingness'], missingness)
            self.assertEqual(parsed['decision_summary'], extra.get('decision_summary'))
            self.assertIsNone(parsed['collector_feedback'])

    def test_ambiguous_and_invalid_outputs_never_execute(self):
        cases = [
            ('{"tool":"read","tool":"submit","args":{}}', 'duplicate_json_key'),
            ('{"tool":"read","args":{"x":NaN}}', 'nonfinite_json_number'),
            ('{"tool":"read","args":{}}\n{"tool":"submit","args":{}}', 'invalid_json'),
            ('[{"tool":"read","args":{}}]', 'object_required'),
            ('{"tool":"shell","args":{}}', 'unknown_tool_name'),
            ('{"tool":"read","args":[]}', 'args_object_required'),
            ('{"tool":"read","args":{},"extra":1}', 'action_fields'),
            ('{"tool":"read","args":{},"decision_summary":123}', 'summary_type'),
            ('<DSML>tool read</DSML>', 'non_json_tool_markup'),
        ]
        for raw, error in cases:
            with self.subTest(error=error):
                env = envmod.ResearchEnv(scenario())
                before = env.snapshot()
                transition, public = contract.apply_output(env, raw)
                self.assertEqual(env.snapshot(), before)
                self.assertEqual(env.events, [])
                self.assertIsNone(transition['action'])
                self.assertIsNone(transition['decision_summary'])
                self.assertEqual(transition['collector_feedback']['error'], error)
                self.assertEqual(public['model_output'], raw)
                self.assertFalse(public['observation']['action_executed'])

    def test_feedback_then_valid_retry_preserves_provenance(self):
        env = envmod.ResearchEnv(scenario())
        rejected, feedback = contract.apply_output(env, '{bad')
        accepted, public = contract.apply_output(env, '{"tool":"read","args":{"document_id":"policy"}}')
        self.assertEqual(feedback['observation']['origin'], 'collector')
        self.assertIn('line 1', feedback['observation']['message'])
        self.assertEqual(rejected['decision_summary_origin'], 'not_extracted_from_rejected_output')
        self.assertEqual(accepted['decision_summary_origin'], 'not_supplied')
        self.assertEqual(accepted['environment_event_index'], 1)
        self.assertEqual(public['observation']['status'], 200)
        self.assertEqual(len(env.events), 1)

    def test_only_single_known_fence_is_normalized(self):
        valid = contract.parse_output('```json\n{"tool":"validate","args":{}}\n```')
        self.assertTrue(valid['accepted'])
        self.assertEqual(valid['normalization'], 'single_json_markdown_fence_removed')
        self.assertFalse(contract.parse_output('Here is my action: ' + '{"tool":"validate","args":{}}')['accepted'])

    def test_environment_argument_error_stays_an_environment_observation(self):
        env = envmod.ResearchEnv(scenario())
        transition, _ = contract.apply_output(env, '{"tool":"read","args":{}}')
        self.assertTrue(transition['accepted'])
        self.assertEqual(transition['observation']['error'], 'document_id_required')
        self.assertIsNone(transition['collector_feedback'])

    def test_capture_keeps_transport_retries_and_original_bad_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = {'task': 'test', 'condition': 'E'}
            frozen = {'providers': old.transport.PROVIDERS, 'system': study.SYSTEM, 'example': study.EXAMPLE,
                      'model_turns': 48, 'transport_attempts_per_turn': 3}
            old.save(root / 'freeze.json', frozen)
            old.save(root / 'tasks/test/scenario.json', scenario())
            requests = []
            def invoke(provider, system, user, config):
                request = json.loads(user)
                requests.append(copy.deepcopy(request))
                self.assertNotIn('scenario', request)
                self.assertNotIn('grade', request)
                if len(requests) == 1:
                    return {'complete': False, 'http_status': 500}
                if len(requests) == 2:
                    return {'complete': True, 'visible_text': '<DSML>bad</DSML>'}
                action = policy.reference_action(request['initial_observation'],
                                                 [x for x in request['history'] if x['action'] is not None])
                return {'complete': True, 'visible_text': json.dumps(action)}
            with patch.object(study.transport, 'invoke', side_effect=invoke), patch.object(study.time, 'sleep'):
                summary = study.run_episode('deepseek', job, frozen, root)
            self.assertEqual(summary['reward'], 1)
            self.assertEqual(summary['protocol_errors'], 1)
            self.assertEqual(summary['transport_errors'], 1)
            self.assertEqual(summary['model_turns'], summary['environment_steps'] + 1)
            self.assertEqual(summary['api_attempts'], summary['model_turns'] + 1)
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(requests[2]['history'][0]['model_output'], '<DSML>bad</DSML>')
            self.assertEqual(requests[2]['history'][0]['observation']['error'], 'non_json_tool_markup')
            self.assertEqual(summary['missing_summaries_on_accepted_actions'], summary['environment_steps'])
            record = old.read(root / 'runs/deepseek/test-E/episode.json')
            self.assertEqual(envmod.verify_record(scenario(), record)['reward'], 1)

if __name__ == '__main__':
    unittest.main()

"""Offline audit of the corrected-collector supplement and its public transcripts."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import workspace_format_study as study
import workspace_action_contract as contract
import workspace_env as envmod


def analyze(root):
    root = Path(root)
    frozen = study.check_freeze(root)
    rows, problems, rejected, unusable, no_usage, local_recoveries = [], [], [], [], [], []
    tool_results, reason_origins = Counter(), Counter()
    model_ids = {p: set() for p in frozen["providers"]}
    for provider in frozen['providers']:
        for job in frozen['jobs_per_provider']:
            target = root / 'runs' / provider / (job['task'] + '-' + job['condition'])
            started = study.read(target / 'started.json')
            assert started['freeze_sha256'] == study.sha(root / 'freeze.json')
            assert all(started[k] == v for k, v in {'provider': provider, **job}.items())
            scenario = study.read(root / 'tasks' / job['task'] / 'scenario.json')
            record = study.read(target / 'episode.json')
            summary = study.read(target / 'summary.json')
            assert envmod.verify_record(scenario, record) == record['grade']
            env = envmod.ResearchEnv(scenario)
            calls, transitions, history = [], [], []
            folders = sorted((target / 'calls').iterdir())
            assert [p.name for p in folders] == [f'{n:03d}' for n in range(1, len(folders) + 1)]
            for turn, folder in enumerate(folders):
                assert not env.finished and turn < frozen['model_turns']
                expected_request = study.request_for(env, history, turn, job['condition'], frozen)
                assert study.read(folder / 'request.json') == expected_request, 'Policy input differs from public history'
                paths = sorted(folder.glob('response-*.json'))
                assert [p.name for p in paths] == [f'response-{i}.json' for i in range(1, len(paths) + 1)]
                attempts = [study.read(p) for p in paths]
                assert 1 <= len(attempts) <= frozen['transport_attempts_per_turn']
                assert not any(x.get('complete') for x in attempts[:-1]), 'Successful output discarded before retry'
                for attempt, response in enumerate(attempts, 1):
                    config = frozen['providers'][provider]
                    assert response['requested_model'] == config['model'] and response['endpoint'] == config['url']
                    assert response['parameters'] == config['params']
                    if response.get('resolved_model'):
                        model_ids[provider].add(response['resolved_model'])
                    model_ids[provider].update(response.get('resolved_models', []))
                    if provider == 'glm':
                        assert response['runtime'] == 'claude_code_coding_plan'
                        if response.get('complete'):
                            assert response['isolated']
                    ref = {'provider': provider, **job, 'turn': turn + 1, 'attempt': attempt}
                    if not response.get('complete'):
                        unusable.append({**ref, 'http_status': response.get('http_status'),
                                         'error_type': response.get('error_type'),
                                         'finish_reason': response.get('finish_reason'),
                                         'visible_output_empty': not bool(response.get('visible_text'))})
                    if not response.get('usage'):
                        no_usage.append(ref)
                calls.extend(attempts)
                if not attempts[-1].get('complete'):
                    assert folder == folders[-1] and not (folder / 'transition.json').exists()
                    assert summary['stop'] == 'transport_incomplete'
                    break
                transition, public = contract.apply_output(env, attempts[-1]['visible_text'])
                assert study.read(folder / 'transition.json') == transition
                transitions.append(transition)
                history.append(public)
                reason_origins[transition['decision_summary_origin']] += 1
                if not transition['accepted']:
                    rejected.append({'provider': provider, **job, 'turn': turn + 1,
                                     'error': transition['collector_feedback']['error'],
                                     'has_later_accepted_action': any(study.read(p / 'transition.json')['accepted']
                                         for p in folders[turn + 1:] if (p / 'transition.json').exists())})
                    continue
                event = env.events[-1]
                assert event == record['events'][len(env.events) - 1]
                tool_results[event['observation'].get('error', 'ok')] += 1
                if not env.missing():
                    for operation in env.operations.values():
                        if operation['step'] == len(env.events):
                            correct = envmod.expected_content(env.documents)
                            mismatches = [k for k, v in correct.items() if operation['content'].get(k) != v]
                            if mismatches:
                                problems.append({'provider': provider, **job, 'turn': turn + 1,
                                                 'environment_step': len(env.events), 'fields': mismatches,
                                                 'result_keys': sorted(operation['content'].get('result', {})),
                                                 'expected_result_keys': sorted(correct['result'])})
            assert record == envmod.record(env, 'actual_model_execution')
            expected_stop = 'environment_terminal' if env.finished else ('transport_incomplete' if not calls[-1].get('complete') else 'model_turn_limit')
            if expected_stop == 'model_turn_limit':
                assert len(transitions) == frozen['model_turns']
            assert summary == study.summarize(provider, job, env, transitions, calls, expected_stop, summary['elapsed_seconds'])
            assert summary['model_turns'] == summary['environment_steps'] + summary['protocol_errors']
            for name, content in env.deliverables().items():
                assert (target / 'deliverables' / name).read_text(encoding='utf-8') == content
            for index, event in enumerate(record['events']):
                observation = event['observation']
                if event['action']['tool'] != 'validate' or observation.get('status') != 200 or observation['validation']['passed']:
                    continue
                later = next((x for x in record['events'][index + 1:] if x['action']['tool'] == 'validate' and x['observation'].get('validation', {}).get('passed')), None)
                local_recoveries.append({'provider': provider, **job, 'failed_validation_step': index + 1,
                                         'failed_checks': [k for k, v in observation['validation']['checks'].items() if not v],
                                         'later_passing_validation_step': later['step'] if later else None,
                                         'episode_reward': summary['reward'],
                                         'scope': 'Public consistency checks only; passing does not imply terminal content correctness.'})
            rows.append(summary)
    results = study.read(root / 'results.json')
    key = lambda r: (r['provider'], r['task'], r['condition'])
    assert results['planned_episodes'] == frozen['planned_episodes'] == len(rows)
    assert results['completed_jobs'] == len(rows)
    assert sorted(results['results'], key=key) == sorted(rows, key=key)
    totals = []
    numeric = ('model_turns', 'environment_steps', 'api_attempts', 'transport_errors', 'protocol_errors',
               'missing_summaries_on_accepted_actions', 'tool_rejections', 'prompt_tokens', 'output_tokens')
    for provider in [*frozen['providers'], 'all']:
        for condition in ('N', 'E'):
            chosen = [r for r in rows if r['condition'] == condition and (provider == 'all' or r['provider'] == provider)]
            totals.append({'provider': provider, 'condition': condition, 'episodes': len(chosen),
                           'complete': sum(r['complete'] for r in chosen), 'successes': sum(r['reward'] for r in chosen),
                           'ready': sum(r['reward'] and r['ticket_status'] == 'ready' for r in chosen),
                           'blocked': sum(r['reward'] and r['ticket_status'] == 'blocked' for r in chosen),
                           **{k: sum(r[k] for r in chosen) for k in numeric}})
    pairs = []
    for provider in frozen['providers']:
        for task in dict.fromkeys(j['task'] for j in frozen['jobs_per_provider']):
            n, e = (next(r for r in rows if r['provider'] == provider and r['task'] == task and r['condition'] == c) for c in ('N', 'E'))
            pairs.append({'provider': provider, 'task': task, 'E_minus_N': {k: e[k] - n[k] for k in ('reward', *numeric)}})
    return {'planned_episodes': frozen['planned_episodes'], 'recorded_episodes': len(rows),
            'successful_episodes': sum(r['reward'] for r in rows), 'totals': totals, 'episodes': rows,
            'within_collector_pairs': pairs, 'observed_tool_results': dict(tool_results),
            'decision_summary_origins': dict(reason_origins), 'observed_model_ids': {p: sorted(v) for p, v in model_ids.items()}, 'format_errors': rejected,
            'unusable_responses': unusable, 'attempts_without_reported_usage': no_usage,
            'accepted_incorrect_edits': problems, 'local_validation_recoveries': local_recoveries,
            'verification_scope': 'Frozen inputs/code, exact public requests, original outputs, explicit collector feedback, environment replay, grades, final artifacts and usage accounting. Does not grade private reasoning or external research truth.'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = analyze(args.root)
    if args.output:
        study.save(args.output, result)
    print(json.dumps({k: result[k] for k in ('planned_episodes', 'recorded_episodes', 'successful_episodes', 'totals',
                                          'observed_tool_results', 'decision_summary_origins', 'unusable_responses',
                                          'attempts_without_reported_usage', 'accepted_incorrect_edits')}, ensure_ascii=False, indent=2))

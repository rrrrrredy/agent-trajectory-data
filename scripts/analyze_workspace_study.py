"""Replay and summarize the frozen usefulness study without further model calls."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path
import workspace_study as study
import workspace_env as e


def analyze(root):
    root=Path(root);frozen=study.read(root/'freeze.json')
    for path,digest in frozen['files'].items():assert study.sha(root/path)==digest,'changed input: '+path
    for path,digest in frozen['code'].items():assert study.sha(study.ROOT/path)==digest,'changed runtime: '+path
    records=[];problem_writes=[];observations={};verified_calls=0;format_errors=[];unusable_responses=[];missing_usage=[]
    for provider in frozen['providers']:
        for job in frozen['jobs_per_provider']:
            folder=root/'runs'/provider/(job['task']+'-'+job['condition'])
            summary=study.read(folder/'summary.json');record=study.read(folder/'episode.json')
            scenario=study.read(root/'tasks'/job['task']/'scenario.json');replay=e.ResearchEnv(scenario);episode_attempts=[]
            assert e.verify_record(scenario,record)==record['grade']
            assert study.read(folder/'started.json')['freeze_sha256']==study.sha(root/'freeze.json')
            for n,event in enumerate(record['events'],1):
                call=folder/'calls'/f'{n:03d}';request=study.read(call/'request.json')
                expected={'initial_observation':replay.initial,'history':[{'action':x['action'],'observation':x['observation']} for x in replay.events],'remaining_environment_steps':48-len(replay.events)}
                if job['condition']=='B':expected['experience_notes']=study.read(root/'experience-notes.json')
                if job['condition']=='C':expected['training_examples']=study.read(root/'demonstrations.json')
                assert request==expected,'unexpected policy input'
                attempts=[study.read(p) for p in sorted(call.glob('response-*.json'))];episode_attempts.extend(attempts)
                assert attempts[-1]['complete'] and not any(x['complete'] for x in attempts[:-1]),'hidden successful retry'
                for attempt,response in enumerate(attempts,1):
                    if not response.get('usage'):missing_usage.append({'provider':provider,**job,'step':n,'attempt':attempt})
                for response in attempts[:-1]:unusable_responses.append({'provider':provider,**job,'step':n,'http_status':response.get('http_status'),'finish_reason':response.get('finish_reason'),'error_type':response.get('error_type'),'visible_output_empty':not bool(response.get('visible_text'))})
                assert all(x['requested_model']==frozen['providers'][provider]['model'] and x['endpoint']==frozen['providers'][provider]['url'] for x in attempts),'provider route changed'
                try:action,reason=study.parse_action(attempts[-1]['visible_text'])
                except (ValueError,TypeError,KeyError):
                    action={'tool':'invalid_model_output','args':{}};reason='Output could not be parsed under the announced action contract.'
                    try:
                        raw=attempts[-1]['visible_text'].strip()
                        if raw.startswith('```') and raw.endswith('```'):raw=raw[raw.index('\n')+1:-3].strip()
                        value=json.loads(raw)
                        missing_reason=isinstance(value,dict) and set(value)=={'tool','args'} and value['tool'] in e.TOOLS and isinstance(value['args'],dict)
                    except (ValueError,TypeError):missing_reason=False
                    format_errors.append({'provider':provider,**job,'step':n,'decision_summary_origin':'collector_error_message_not_model_rationale','action_origin':'collector_rejection_marker; original model output retained in response','category':'missing_decision_summary_only' if missing_reason else ('provider_tool_markup_in_text' if 'DSML' in attempts[-1]['visible_text'] else 'other_action_contract_error')})
                transition=study.read(call/'transition.json')
                assert transition=={'action':action,'decision_summary':reason,'observation':event['observation']}
                assert action==event['action'];replay.step(action);assert replay.events[-1]==event
                label=event['observation'].get('error','ok');observations[label]=observations.get(label,0)+1
                for operation in replay.operations.values():
                    if operation['step']==n and not replay.missing():
                        target=e.expected_content(replay.documents)
                        if any(operation['content'].get(k)!=v for k,v in target.items()):problem_writes.append({'provider':provider,**job,'step':n,'type':'accepted_edit_disagrees_with_current_supplied_evidence'})
                verified_calls+=len(attempts)
            assert summary['reward']==replay.grade()['reward'] and summary['steps']==len(replay.events)
            assert summary['api_attempts']==len(episode_attempts) and summary['transport_errors']==sum(not r['complete'] for r in episode_attempts)
            input_tokens=sum(r.get('usage',{}).get('prompt_tokens',sum(r.get('usage',{}).get(k,0) for k in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens'))) for r in episode_attempts)
            output_tokens=sum(r.get('usage',{}).get('completion_tokens',r.get('usage',{}).get('output_tokens',0)) for r in episode_attempts)
            assert summary['prompt_tokens']==input_tokens and summary['output_tokens']==output_tokens
            for filename,content in replay.deliverables().items():assert (folder/'deliverables'/filename).read_text(encoding='utf-8')==content
            records.append(summary)
    assert len(records)==frozen['planned_episodes']==48
    collected=study.read(root/'results.json')
    assert collected['planned_episodes']==48 and collected['completed_jobs']==48
    order=lambda r:(r['provider'],r['task'],r['condition'])
    assert sorted(collected['results'],key=order)==sorted(records,key=order)
    rows=[]
    for provider in frozen['providers']:
        for condition in 'ABC':
            selected=[x for x in records if x['provider']==provider and x['condition']==condition]
            completed=[x for x in selected if x['complete'] and x['stop']=='environment_terminal']
            rows.append({'provider':provider,'condition':condition,'scheduled':len(selected),'completed':len(completed),'successes':sum(x['reward'] for x in completed),'steps_total':sum(x['steps'] for x in selected),'steps_median':statistics.median(x['steps'] for x in completed) if completed else None,'prompt_tokens':sum(x['prompt_tokens'] for x in selected),'output_tokens':sum(x['output_tokens'] for x in selected),'transport_errors':sum(x['transport_errors'] for x in selected),'protocol_errors':sum(x['protocol_errors'] for x in selected),'elapsed_seconds':round(sum(x['elapsed_seconds'] for x in selected),3)})
    result={'planned_episodes':48,'recorded_episodes':len(records),'completed_episodes':sum(x['complete'] for x in records),'successful_episodes':sum(x['reward'] for x in records),'calls_bound_to_actions':verified_calls,'rows':rows,'episodes':records,'observed_tool_results':observations,'accepted_incorrect_edits':problem_writes,'format_errors':format_errors,'unusable_response_attempts':unusable_responses,'attempts_without_reported_usage':missing_usage,'primary_comparison':'Within each provider, paired by task, A versus B versus C. Four tasks and one rollout per cell; descriptive only.','verification_scope':'Frozen inputs, public input boundary, visible model output to action, deterministic environment replay and rendered final artifacts. Not independent validation of freeform reasoning or external research truth.'}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=analyze(args.root)
    if args.output:study.save(args.output,result)
    print(json.dumps({k:result[k] for k in ('planned_episodes','completed_episodes','successful_episodes','calls_bound_to_actions','rows','observed_tool_results','accepted_incorrect_edits','attempts_without_reported_usage')},ensure_ascii=False,indent=2))
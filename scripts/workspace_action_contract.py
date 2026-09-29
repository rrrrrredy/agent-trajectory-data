"""Public action envelope. Parse failures never become environment tool calls."""
from __future__ import annotations
import json
from workspace_env import TOOLS

VERSION = 'workspace-action-envelope-2'

class ContractError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ContractError('duplicate_json_key', 'Each JSON object key must occur once: ' + key)
        value[key] = item
    return value

def reject_constant(value):
    raise ContractError('nonfinite_json_number', 'Use finite JSON numbers; ' + value + ' is not valid JSON.')

def parse_output(text):
    """Keep observable model rationale separate from host-generated feedback."""
    normalization = None
    try:
        if not isinstance(text, str):
            raise ContractError('text_required', 'Return one JSON object as visible text.')
        raw = text.strip()
        lines = raw.split('\n')
        if len(lines) >= 3 and lines[0].strip() in ('```', '```json') and lines[-1].strip() == '```':
            raw = '\n'.join(lines[1:-1]).strip()
            normalization = 'single_json_markdown_fence_removed'
        try:
            value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except json.JSONDecodeError as exc:
            code = 'non_json_tool_markup' if 'DSML' in raw else 'invalid_json'
            message = ('Provider tool markup cannot execute here. Return one JSON action object as visible text.'
                       if code == 'non_json_tool_markup' else
                       f'Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}. Return exactly one JSON object.')
            raise ContractError(code, message) from exc
        if not isinstance(value, dict):
            raise ContractError('object_required', 'Return one action object, not an array or a scalar.')
        missing = {'tool', 'args'} - set(value)
        extra = set(value) - {'tool', 'args', 'decision_summary'}
        if missing or extra:
            raise ContractError('action_fields', 'Required fields: tool, args. Optional field: decision_summary. '
                                + 'Missing: ' + ', '.join(sorted(missing)) + '; unexpected: ' + ', '.join(sorted(extra)) + '.')
        if not isinstance(value['tool'], str) or value['tool'] not in TOOLS:
            raise ContractError('unknown_tool_name', 'tool must be one of: ' + ', '.join(TOOLS) + '.')
        if not isinstance(value['args'], dict):
            raise ContractError('args_object_required', 'args must be a JSON object; check the public tool arguments.')
        reason = value.get('decision_summary')
        if reason is not None and not isinstance(reason, str):
            raise ContractError('summary_type', 'decision_summary may be a brief visible string, null, or omitted.')
        missingness = ('omitted' if 'decision_summary' not in value else
                       'explicit_null' if reason is None else 'empty' if not reason.strip() else None)
        return {'accepted': True, 'action': {'tool': value['tool'], 'args': value['args']},
                'decision_summary': reason,
                'decision_summary_origin': 'model_visible_output' if reason is not None else 'not_supplied',
                'decision_summary_missingness': missingness,
                'collector_feedback': None, 'normalization': normalization}
    except ContractError as exc:
        return {'accepted': False, 'action': None, 'decision_summary': None,
                'decision_summary_origin': 'not_extracted_from_rejected_output',
                'decision_summary_missingness': 'rejected_output',
                'collector_feedback': {'origin': 'collector', 'error': exc.code,
                                       'message': exc.message, 'action_executed': False},
                'normalization': normalization}

def apply_output(env, visible_text):
    """An envelope rejection consumes a model turn, never an environment action."""
    parsed = parse_output(visible_text)
    if parsed['accepted']:
        observation = env.step(parsed['action'])[0]
        event_index = len(env.events)
        public = {'action': parsed['action'], 'observation': observation}
    else:
        observation, event_index = parsed['collector_feedback'], None
        public = {'action': None, 'model_output': visible_text, 'observation': observation}
    return {**parsed, 'environment_event_index': event_index, 'observation': observation}, public

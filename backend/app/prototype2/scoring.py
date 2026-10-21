"""Prototype 2 supported criteria and precise point allocation.

Only registered evaluators can run. Recommendations never execute code.
"""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pydantic import BaseModel, Field, model_validator

CATALOG = {
    'nonempty': ('Nonempty response', 'Checks the model returned text'),
    'valid_json': ('Valid JSON', 'Checks JSON syntax'),
    'json_object': ('JSON object', 'Checks the response is a JSON object'),
    'required_keys': ('Required JSON fields', 'Checks requested top-level keys'),
    'field_types': ('JSON field types', 'Checks top-level field types'),
    'minimum_length': ('Minimum length', 'Checks response character count'),
    'keywords': ('Keyword coverage', 'Checks required words or phrases'),
    'forbidden_terms': ('Forbidden terms', 'Checks disallowed words or phrases'),
}
TWO = Decimal('0.01')

class CriterionSelection(BaseModel):
    id: str
    points: str
    parameters: dict = Field(default_factory=dict)

class ScoringConfiguration(BaseModel):
    criteria: list[CriterionSelection] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def validate_configuration(self):
        ids = set()
        total = Decimal('0')
        for c in self.criteria:
            if c.id not in CATALOG or c.id in ids:
                raise ValueError(f'Unknown or duplicate criterion: {c.id}')
            ids.add(c.id)
            try:
                weight = Decimal(c.points)
            except (InvalidOperation, ValueError):
                raise ValueError('Criterion points must be decimal numbers') from None
            if not weight.is_finite() or weight <= 0 or weight.as_tuple().exponent < -2:
                raise ValueError('Points must be positive and have at most two decimals')
            total += weight
            p = c.parameters
            if c.id in ('required_keys', 'keywords', 'forbidden_terms'):
                key = {'required_keys':'keys','keywords':'terms','forbidden_terms':'terms'}[c.id]
                if not isinstance(p.get(key), list) or not p[key] or not all(isinstance(x,str) and x.strip() for x in p[key]):
                    raise ValueError(f'{c.id} needs a nonempty {key} list')
            if c.id == 'minimum_length' and (type(p.get('min_chars')) is not int or p['min_chars'] <= 0):
                raise ValueError('minimum_length needs positive min_chars')
            if c.id == 'field_types':
                types = p.get('types')
                if not isinstance(types, dict) or not types or not all(isinstance(k,str) and k and v in ('string','number','boolean','object','array','null') for k,v in types.items()):
                    raise ValueError('field_types needs types mapping to JSON type names')
        if total != Decimal('100.00'):
            raise ValueError(f'Points must total exactly 100.00, not {total}')
        return self

def _json_type(value):
    if value is None: return 'null'
    if isinstance(value,bool): return 'boolean'
    if isinstance(value,str): return 'string'
    if isinstance(value,(int,float)): return 'number'
    if isinstance(value,list): return 'array'
    return 'object'

def evaluate_one(criterion, response):
    """Return normalized fraction and evidence; no implicit pass/fail threshold."""
    cid, p = criterion.id, criterion.parameters
    text = response.strip()
    if cid == 'nonempty':
        return (Decimal(1) if text else Decimal(0)), 'Response has text' if text else 'Response is empty'
    if cid == 'minimum_length':
        count = len(response)
        return min(Decimal(1), Decimal(count)/Decimal(p['min_chars'])), f'{count} of {p["min_chars"]} characters'
    if cid in ('keywords','forbidden_terms'):
        matches = [t for t in p['terms'] if t.casefold() in response.casefold()]
        if cid == 'keywords':
            return Decimal(len(matches))/Decimal(len(p['terms'])), f'Matched {len(matches)} of {len(p["terms"])} terms'
        return (Decimal(0) if matches else Decimal(1)), ('Found forbidden terms: '+', '.join(matches)) if matches else 'No forbidden terms found'
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return Decimal(0), 'Response is not valid JSON'
    if cid == 'valid_json': return Decimal(1), 'Response parses as JSON'
    if cid == 'json_object':
        return (Decimal(1) if isinstance(data,dict) else Decimal(0)), 'Response is a JSON object' if isinstance(data,dict) else 'JSON value is not an object'
    if not isinstance(data,dict): return Decimal(0), 'Expected a top-level JSON object'
    if cid == 'required_keys':
        matched = [k for k in p['keys'] if k in data]
        return Decimal(len(matched))/Decimal(len(p['keys'])), f'Found {len(matched)} of {len(p["keys"])} required fields'
    if cid == 'field_types':
        matched = [k for k,t in p['types'].items() if k in data and _json_type(data[k]) == t]
        return Decimal(len(matched))/Decimal(len(p['types'])), f'{len(matched)} of {len(p["types"])} fields have correct types'
    raise ValueError('Unsupported evaluator')

def evaluate(configuration, response):
    rows=[]
    total=Decimal('0')
    for c in configuration.criteria:
        fraction,evidence=evaluate_one(c,response)
        earned=(Decimal(c.points)*fraction).quantize(TWO,rounding=ROUND_HALF_UP)
        total+=earned
        rows.append({'id':c.id,'name':CATALOG[c.id][0], 'maximum':c.points,'earned':str(earned),'normalized':str(fraction),'evidence':evidence})
    return {'total':str(total.quantize(TWO)),'criteria':rows}

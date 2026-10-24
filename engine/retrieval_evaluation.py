"""Versioned, read-only retrieval measurements; private fixtures stay outside releases."""
import hashlib
import json
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA_VERSION = 1
EVALUATOR_VERSION = '1.0.0'


def load_cases(path, wiki_root):
    """Load a versioned private fixture, retaining invalid cases in its denominator."""
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if document.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('unsupported fixture schema')
    cases = document['cases']
    ids = [c['id'] for c in cases]
    if document.get('question_count') != len(cases) or len(set(ids)) != len(ids):
        raise ValueError('fixture count or duplicate ID mismatch')
    loaded = []
    for case in cases:
        validation = validate_case(case, wiki_root)
        if case.get('provenance', {}).get('kind') == 'real':
            try:
                prov = case['provenance']
                rel = prov['context_file']
                if '/' in rel or '\\' in rel or ':' in rel or rel in ('', '.', '..'):
                    raise ValueError('context must be a plain adjacent fixture filename')
                context_path = Path(path).resolve().parent / rel
                if context_path.is_symlink() or context_path.resolve().parent != Path(path).resolve().parent:
                    raise ValueError('unsafe context file')
                data = context_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != prov['context_sha256']:
                    raise ValueError('captured context hash changed')
                questions = [c['question'] for c in json.loads(data)['cases'] if c['question']['id'] == prov['message_id']]
                if len(questions) != 1:
                    raise ValueError('original question missing or duplicated')
                question = questions[0]
                if not (question['role'] == 'user' and question['_compressed_summary'] == 0
                        and question['session_id'] == prov['session_id'] and question['content'] == case['question']):
                    raise ValueError('captured original user question mismatch')
            except (KeyError, TypeError, ValueError, OSError) as exc:
                validation = {'status': 'invalid', 'quality_eligible': False, 'reference_valid': False, 'reasons': [str(exc)]}
        loaded.append(dict(case, validation=validation))
    return loaded


def validate_case(case, wiki_root):
    """Validate byte/line anchors. Curated records are not certified answer gold."""
    result = {'status': 'unsupported', 'quality_eligible': False, 'reasons': [], 'reference_valid': False}
    root = Path(wiki_root).resolve()
    try:
        if not isinstance(case['id'], str) or not case['id'] or not isinstance(case['question'], str) or not case['question']:
            raise ValueError('nonempty id and exact question required')
        prov = case['provenance']
        if prov.get('kind') == 'real':
            if not (type(prov.get('message_id')) is int and prov.get('role') == 'user'
                    and prov.get('compressed_summary') == 0 and prov.get('session_id')
                    and prov.get('question_sha256') == hashlib.sha256(case['question'].encode('utf-8')).hexdigest()):
                raise ValueError('captured original user provenance required')
        elif prov.get('kind') != 'synthetic':
            raise ValueError('provenance kind required')
        if not case['references']:
            raise ValueError('at least one source anchor required')
        for ref in case['references']:
            rel = ref['path']
            if not isinstance(rel, str) or '\\' in rel or ':' in rel or rel.startswith('/') or any(p in ('', '.', '..') for p in rel.split('/')):
                raise ValueError('unsafe relative source path')
            path = root / rel
            if not path.resolve().is_relative_to(root):
                raise ValueError('source escapes selected root')
            if any(p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0) for p in (path, *path.parents) if p != root):
                raise ValueError('source links forbidden')
            digest = ref['sha256']
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('exact lowercase sha256 required')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                result.update(status='stale', reasons=['source hash changed: ' + rel])
                return result
            lines = data.decode('utf-8').splitlines()
            start, end = ref['start_line'], ref['end_line']
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
                raise ValueError('invalid line anchor')
            if '\n'.join(lines[start - 1:end]) != ref['quote']:
                raise ValueError('exact source quote mismatch')
        values = {}
        for point in case['expected_points']:
            key, value = point['key'], point['value']
            if key in values and values[key] != value:
                result.update(status='conflict', reasons=['conflicting expected points: ' + key])
                return result
            values[key] = value
        result['reference_valid'] = True
        result['reasons'] = [case['gold'].get('reason', 'No independent answer certification')]
    except (KeyError, TypeError, ValueError, OSError) as exc:
        result.update(status='invalid', reasons=[str(exc)])
    return result


def evaluate_retrieval(case, response, project_id, top_k=10):
    """Selected path/exact-quote diagnostics, not relevance or answer correctness."""
    error = None
    if response.get('ok') is not True:
        error = response.get('error', 'response not successful')
    elif response.get('projectId') != project_id:
        error = 'returned project mismatch or missing projectId'
    elif response.get('mode') not in ('hybrid', 'keyword'):
        error = 'missing or unsupported returned mode'
    elif not isinstance(response.get('results'), list):
        error = 'missing results array'
    returned = response.get('results', [])
    if not isinstance(returned, list):
        returned = []
    paths, results = [], []
    for result in returned[:top_k]:
        if not isinstance(result, dict) or not isinstance(result.get('path'), str):
            error = error or 'malformed result path'
            continue
        if result.get('content') is not None and not isinstance(result.get('content'), str):
            error = error or 'malformed result content'
            continue
        if result['path'] not in paths:
            paths.append(result['path'])
            results.append(result)
    refs = case['references']
    ranks = [i + 1 for i, r in enumerate(returned[:top_k]) if isinstance(r, dict) and any(r.get('path') == ref['mirror_path'] for ref in refs)]
    rank = min(ranks) if ranks and not error and case.get('validation', {}).get('reference_valid') else None
    content = '\n'.join(r.get('content', '') or '' for r in results)
    coverage = sum(r['quote'] in content for r in refs) / len(refs) if refs and not error and case.get('validation', {}).get('reference_valid') else None
    return {'case_id': case['id'], 'error': error, 'mode': response.get('mode'),
            'returned_project_id': response.get('projectId'), 'result_count': len(returned),
            'unique_result_count': len(paths), 'result_paths': paths,
            'reference_hit': int(rank is not None), 'reference_rank': rank,
            'reference_reciprocal_rank': 1 / rank if rank else 0,
            'quote_coverage': coverage, 'content_present': any(r.get('content') for r in results),
            'top_k_saturated': len(returned) >= top_k,
            'result_total_known': response.get('total'), 'has_more': response.get('hasMore'),
            'token_hits': response.get('tokenHits'), 'vector_hits': response.get('vectorHits'),
            'graph_hits': response.get('graphHits'), 'answer_correctness': None,
            'llm_tokens': None, 'llm_cost_usd': None}


def search_app(api_base, project_id, query, top_k, embedding_endpoint, timeout=15):
    """Only POST search on literal loopback, with bounded time and no redirects."""
    for endpoint in (api_base, embedding_endpoint):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('unapproved non-loopback or credential-bearing endpoint')
    if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', project_id):
        raise ValueError('project identifier must be an exact lowercase UUID')
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('top_k must be 1..100')
    payload = {'query': query, 'topK': top_k, 'includeContent': True}
    url = api_base.rstrip('/') + '/api/v1/projects/' + project_id + '/search'
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    start = time.monotonic()
    raw, status, error = None, None, None
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        status, raw, error = exc.code, exc.read().decode('utf-8', errors='replace'), 'HTTP ' + str(exc.code)
    except (OSError, urllib.error.URLError) as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    try:
        parsed = json.loads(raw) if raw is not None else {'ok': False, 'error': error}
        if not isinstance(parsed, dict):
            raise ValueError('response must be a JSON object')
    except (ValueError, TypeError) as exc:
        parsed = {'ok': False, 'error': str(exc)}
    if error:
        parsed = dict(parsed, ok=False, error=parsed.get('error') or error)
    return {'request': {'method': 'POST', 'url': url, 'body': payload}, 'http_status': status,
            'raw_body': raw, 'response': parsed, 'transport_error': error,
            'elapsed_seconds': time.monotonic() - start, 'llm_tokens': None, 'llm_cost_usd': None}


def summarize(measurements):
    """All attempts including failed/empty/stale cases remain in diagnostic rates."""
    from collections import Counter
    from statistics import median
    count = len(measurements)
    elapsed = [m['elapsed_seconds'] for m in measurements if isinstance(m.get('elapsed_seconds'), (int, float))]
    return {'attempts': count, 'errors': sum(bool(m['error']) for m in measurements),
            'empty_results': sum(m['result_count'] == 0 for m in measurements),
            'reference_hits': sum(m['reference_hit'] for m in measurements),
            'reference_hit_at_k': sum(m['reference_hit'] for m in measurements) / count if count else None,
            'reference_mrr_at_k': sum(m['reference_reciprocal_rank'] for m in measurements) / count if count else None,
            'modes': dict(Counter(m['mode'] for m in measurements)),
            'elapsed_min_seconds': min(elapsed) if elapsed else None,
            'elapsed_median_seconds': median(elapsed) if elapsed else None,
            'elapsed_max_seconds': max(elapsed) if elapsed else None,
            'answer_correctness': None, 'llm_tokens': None, 'llm_cost_usd': None,
            'keyword_only_comparison': 'unavailable; no supported selector established'}


def main(argv=None):
    """Run only existing GET projects / POST search; no answer generation or settings writes."""
    import argparse
    import datetime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--api-base', default='http://127.0.0.1:19828')
    parser.add_argument('--app-state', type=Path)
    parser.add_argument('--top-k', type=int, default=10)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--query-field', choices=('question', 'context_query'), default='question')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args(argv)
    cases = load_cases(args.cases, args.project)
    if args.validate_only:
        print(json.dumps([{'id': c['id'], **c['validation']} for c in cases], ensure_ascii=False, indent=2))
        return int(any(c['validation']['status'] in ('invalid', 'stale', 'conflict') for c in cases))
    if not args.output or not args.app_state or not 1 <= args.repetitions <= 20 or not 1 <= args.top_k <= 100:
        parser.error('output, app-state and bounded repetitions/top-k required')
    output = args.output.resolve()
    if output.is_relative_to(args.project.resolve()):
        raise ValueError('output must be outside the live selected project')
    config = json.loads(args.app_state.read_text(encoding='utf-8'))['embeddingConfig']
    endpoint = config.get('endpoint') if config.get('enabled') else args.api_base
    for url in (args.api_base, endpoint):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('only literal credential-free loopback endpoints approved')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    projects_url = args.api_base.rstrip('/') + '/api/v1/projects'
    with opener.open(projects_url, timeout=15) as response:
        projects_raw = response.read().decode('utf-8')
    projects = json.loads(projects_raw)
    matches = [p for p in projects.get('projects', []) if p.get('current') is True and Path(p['path']).resolve() == args.project.resolve()]
    if projects.get('ok') is not True or len(matches) != 1:
        raise ValueError('exact current selected project folder not resolved')
    selected = matches[0]
    output.mkdir(parents=True, exist_ok=False)
    measurements = []
    with (output / 'raw-responses.jsonl').open('w', encoding='utf-8') as raw_file:
        for repetition in range(1, args.repetitions + 1):
            for case in cases:
                current_config = json.loads(args.app_state.read_text(encoding='utf-8'))['embeddingConfig']
                if current_config != config:
                    raise ValueError('embedding configuration changed during run; partial raw responses preserved')
                observed = search_app(args.api_base, selected['id'], case[args.query_field], args.top_k, endpoint)
                raw_file.write(json.dumps({'case_id': case['id'], 'repetition': repetition, **observed}, ensure_ascii=False) + '\n')
                raw_file.flush()
                fresh_validation = validate_case(case, args.project)
                validated = dict(case, validation=case['validation'] if case['validation']['status'] == 'invalid' else fresh_validation)
                measurement = evaluate_retrieval(validated, observed['response'], selected['id'], args.top_k)
                measurement.update(repetition=repetition, elapsed_seconds=observed['elapsed_seconds'], http_status=observed['http_status'], validation=validated['validation'])
                measurements.append(measurement)
    final_validation = [dict(id=c['id'], **c['validation']) for c in load_cases(args.cases, args.project)]
    summary = summarize(measurements)
    result = {'schema_version': SCHEMA_VERSION, 'evaluator_version': EVALUATOR_VERSION,
              'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'case_file_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              'evaluator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'selected_project': selected, 'projects_response': projects,
              'embedding_config': {k: config.get(k) for k in ('enabled', 'endpoint', 'model', 'batchSize', 'concurrency')},
              'query_field': args.query_field, 'top_k': args.top_k, 'repetitions': args.repetitions,
              'question_count': len(cases), 'quality_eligible_cases': 0,
              'initial_validation': [{'id': c['id'], **c['validation']} for c in cases],
              'final_validation': final_validation, 'summary': summary, 'measurements': measurements}
    (output / 'projects-response.json').write_text(projects_raw, encoding='utf-8')
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Retrieval measurement report v1', '',
             'Selected-path diagnostics only. No certified answer gold, generated answers or correctness scores.', '',
             'Raw evidence: `results.json`, `raw-responses.jsonl`, `projects-response.json`.', '',
             '```json', json.dumps(summary, indent=2), '```', '',
             '| Case | Repetition | Mode | HTTP | Reference rank | Error |', '|---|---:|---|---:|---:|---|']
    lines += [f"| {m['case_id']} | {m['repetition']} | {m['mode']} | {m['http_status']} | {m['reference_rank']} | {m['error']} |" for m in measurements]
    lines += ['', '## Limits', '',
              '- Selected reference mirror hit/MRR is not gold relevance, full recall, or answer correctness.',
              '- Exact source-quote containment is a lexical diagnostic; paraphrases can be supported without matching.',
              '- Original question and analyst context-query arms are different inputs, not retrieval-mode ablation.',
              '- Ordered repetitions are not independent users, cold-start tests or population latency estimates.',
              '- Query token/vector/graph hit counts are retrieval candidate counts, not LLM usage.',
              '- Missing token/cost data stays null. Keyword-only, model ablation, quality, abstention and decision misuse rates are unmeasured.',
              '- Running binary identity and in-memory embedding settings cannot be certified from stored settings alone.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), **summary}, indent=2))
    return int(bool(summary['errors']) or any(v['status'] in ('invalid', 'stale', 'conflict') for v in final_validation))


if __name__ == '__main__':
    raise SystemExit(main())

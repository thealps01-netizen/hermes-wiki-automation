"""Evidence requests: a drafted finding names the public copy it needs, the owner fetches it.

WHY: the nightly harvest runs without network access on purpose. Its input is conversation text,
and a model that could fetch could also send that text somewhere. A finding (a fact about an outside
tool, paper or product) still needs a retained copy before it may enter the wiki. So the harvest
does not fetch: it writes the finding with an EVIDENCE REQUEST in candidate.json, naming the public
source and the verbatim passages the conversation showed. Nothing is downloaded until the owner,
who sees every address and passage in the review, asks for it. The fetch is evidence_capture.py's
own capture (a passage that is not in the downloaded file means nothing is written) into the
candidate's evidence/<id>/ folder, so the owner then reviews and approves the exact stored bytes
through the normal approval.

A REQUEST is one entry of candidate.json "evidence_requests":
  {"id": "<new evidence id>", "supports": "<the claim it backs>",
   "github": ["<owner>/<repo>@<ref>:<path>", ...]   one repository, the same commit
     or "url": "https://<public host>/...",
   "passages": ["<verbatim text from the source>", ...]}
Its id is also listed in "evidence_ids" and cited by the source text like any evidence id. Only
public GitHub files and public https pages can be requested; a local file never can, because a
request comes from model output and a local file could carry this machine's private data.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shutil
import urllib.parse
from pathlib import Path

from evidence_store import DATE, ID_TOKEN
from workflow_paths import PathRefused, checked_path

MAX_REQUESTS = 5
MAX_FILES = 5
MAX_PASSAGES = 5
GITHUB_SPEC = re.compile(r'[A-Za-z0-9][\w.-]{0,99}/[A-Za-z0-9][\w.-]{0,99}@[\w.\-/]{1,200}:[\w.\-/]{1,300}')
FIELDS = {'id', 'supports', 'github', 'url', 'passages'}


class RequestRefused(ValueError):
    pass


def _public_url(value) -> str:
    if not isinstance(value, str) or len(value) > 2000 or any(ch.isspace() for ch in value):
        raise RequestRefused('A requested address must be one https URL')
    parts = urllib.parse.urlsplit(value)
    host = parts.hostname or ''
    if parts.scheme != 'https' or not host or parts.username or parts.password or parts.port not in (None, 443):
        raise RequestRefused('A requested address must be a public https URL without credentials or port')
    try:
        ipaddress.ip_address(host.strip('[]'))
        literal = True
    except ValueError:
        literal = False
    if literal:
        raise RequestRefused('A requested address must name a host, not an IP address')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.lan', '.home')) or '.' not in host:
        raise RequestRefused('A requested address must be on a public host')
    return value


def _github(value) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_FILES:
        raise RequestRefused(f'A GitHub request names 1 to {MAX_FILES} files')
    for spec in value:
        if not isinstance(spec, str) or not GITHUB_SPEC.fullmatch(spec) or '..' in spec:
            raise RequestRefused('A GitHub file must be <owner>/<repo>@<ref>:<path>')
    if len({spec.split('@', 1)[0].lower() for spec in value}) != 1:
        raise RequestRefused('One evidence request holds one repository; use one request per repository')
    return list(value)


def requests_of(metadata: dict) -> list[dict]:
    """The validated requests of a candidate (an empty list when it has none)."""
    found = metadata.get('evidence_requests')
    if found is None:
        return []
    if not isinstance(found, list) or not 1 <= len(found) <= MAX_REQUESTS:
        raise RequestRefused(f'evidence_requests holds 1 to {MAX_REQUESTS} requests')
    out, seen = [], set()
    ids = metadata.get('evidence_ids')
    for request in found:
        if not isinstance(request, dict) or set(request) - FIELDS or not {'id', 'supports', 'passages'} <= set(request):
            raise RequestRefused('An evidence request has id, supports, passages and one of github or url')
        value = request['id']
        if not isinstance(value, str) or len(value) > 80 or not ID_TOKEN.fullmatch(value) or DATE.fullmatch(value) \
                or value in seen:
            raise RequestRefused('An evidence request needs its own new id of lowercase words joined by hyphens')
        if not isinstance(ids, list) or value not in ids:
            raise RequestRefused(f'Requested evidence {value} must also be listed in evidence_ids')
        seen.add(value)
        supports = request['supports']
        if not isinstance(supports, str) or not 1 <= len(supports.strip()) <= 500:
            raise RequestRefused('supports must state the claim in 1 to 500 characters')
        passages = request['passages']
        if (not isinstance(passages, list) or not 1 <= len(passages) <= MAX_PASSAGES
                or any(not isinstance(p, str) or not 8 <= len(p.strip()) <= 500 for p in passages)):
            raise RequestRefused(f'A request quotes 1 to {MAX_PASSAGES} verbatim passages of 8 to 500 characters')
        if ('github' in request) == ('url' in request):
            raise RequestRefused('An evidence request names either github files or one url')
        source = {'github': _github(request['github'])} if 'github' in request else {'url': _public_url(request['url'])}
        out.append({'id': value, 'supports': supports, 'passages': list(passages), **source})
    return out


def check_new_ids(wiki: Path, requests: list[dict]) -> None:
    for request in requests:
        if checked_path(wiki, f"raw/evidence/{request['id']}").exists():
            raise RequestRefused(f"Evidence id {request['id']} already exists; a new copy needs a new id")


def pending_ids(candidate: Path, metadata: dict) -> list[str]:
    """Requested ids whose copy is not in the candidate's evidence folder yet."""
    return sorted(r['id'] for r in requests_of(metadata) if not (candidate / 'evidence' / r['id']).exists())


def fetch(wiki: Path, inbox: Path, ref: str, expected_review_digest: str) -> dict:
    """Fetch every pending request of the reviewed candidate into its evidence folder."""
    import evidence_capture
    from wiki_candidates import Refused, load_candidate, review_snapshot
    if not isinstance(expected_review_digest, str) or not re.fullmatch('[0-9a-f]{64}', expected_review_digest):
        raise Refused('Fetching evidence needs the digest of the displayed review')
    if review_snapshot(wiki, inbox, ref)['review_digest'] != expected_review_digest:
        raise Refused('The candidate changed since it was displayed; review it again')
    candidate, metadata = load_candidate(inbox, ref)
    if (candidate / 'applied.json').exists():
        raise Refused('The candidate is already applied')
    try:
        requests = requests_of(metadata)
        check_new_ids(wiki, requests)
    except (RequestRefused, PathRefused) as exc:
        raise Refused(str(exc)) from exc
    if not requests:
        raise Refused('The candidate requests no evidence')
    root = checked_path(candidate, 'evidence')
    results = []
    for request in requests:
        folder = checked_path(root, request['id'])
        if folder.exists():
            results.append({'id': request['id'], 'ok': True, 'status': 'already-fetched'})
            continue
        args = argparse.Namespace(id=request['id'], used_by=metadata['target'], supports=request['supports'],
                                  github=request.get('github'), url=request.get('url'), file=None, origin=None,
                                  license=None, passage=request['passages'], allow_lost=False, wayback_save=False)
        partial = folder.with_name(folder.name + '.partial')
        try:
            result = evidence_capture.capture(args)
            root.mkdir(exist_ok=True)
            evidence_capture.write(root, result, False)
            manifest = result['manifest']
            results.append({'id': request['id'], 'ok': True, 'status': manifest.get('status'),
                            'source_url': manifest.get('source_url'), 'commit': manifest.get('commit'),
                            'files': {name: entry['bytes'] for name, entry in manifest['files'].items()},
                            'passages_verified': len(manifest.get('passages') or [])})
        except (evidence_capture.CaptureError, OSError, ValueError) as exc:
            results.append({'id': request['id'], 'ok': False, 'error': str(exc)[:500]})
        finally:
            if partial.exists():
                shutil.rmtree(partial)
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    return {'ref': ref, 'ok': all(r['ok'] for r in results), 'results': results,
            'pending': pending_ids(candidate, metadata)}


def describe(candidate: Path, metadata: dict) -> list[dict]:
    """What the review shows for each request: the source, the passages and whether it is fetched."""
    out = []
    for request in requests_of(metadata):
        folder = candidate / 'evidence' / request['id']
        entry = {**request, 'fetched': folder.exists()}
        if folder.exists():
            try:
                manifest = json.loads((folder / 'manifest.json').read_bytes())
                entry.update({'status': manifest.get('status'), 'source_url': manifest.get('source_url'),
                              'commit': manifest.get('commit'),
                              'files': {k: v.get('bytes') for k, v in (manifest.get('files') or {}).items()}})
            except (OSError, ValueError, AttributeError):
                entry['status'] = 'unreadable'
        out.append(entry)
    return out

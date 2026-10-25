"""Constrained, data-only drafting facade shared by the host integration.

Execution identity is provided by the host, never by model tool arguments.
Run collection must persist that identity before drafting is enabled.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from workflow_paths import PathRefused, checked_path, identifier
from wiki_candidates import NAME_RE, check_format, content_refusals, validate_evidence_bindings, validate_source_citations, Refused
import evidence_store
import evidence_requests

RETAINED_ONLY = ('Evidence citations through this adapter are limited to an update keeping evidence its exact '
                 'current target already cites, each with a retained manifest, and to new ids named by an '
                 'evidence request in evidence_requests')


class DraftRefused(RuntimeError):
    pass


class DraftAdapter:
    def __init__(self, wiki: Path, inbox: Path, run_id: str, execution_id: str, job_id: str):
        self.wiki, self.inbox = Path(wiki), Path(inbox)
        try:
            self.run_id = identifier(run_id)
            self.run = checked_path(inbox, self.run_id)
            manifest_path = checked_path(inbox, f'{self.run_id}/run.json')
            self.manifest = json.loads(manifest_path.read_bytes())
            project_path = checked_path(wiki, '.llm-wiki/project.json')
            project_id = json.loads(project_path.read_bytes())['id']
        except (PathRefused, OSError, ValueError, KeyError) as exc:
            raise DraftRefused('Unreadable or unsafe bound run') from exc
        if not execution_id or not job_id or self.manifest.get('execution_id') != execution_id or self.manifest.get('job_id') != job_id:
            raise DraftRefused('Run is not bound to the current host execution')
        if self.manifest.get('project_id') != project_id:
            raise DraftRefused('Run belongs to a different project')

    def read(self, path: str, offset: int = 0, limit: int = 20000) -> dict:
        try:
            if path.startswith('source:'):
                name = path[len('source:'):]
                if not NAME_RE.fullmatch(name):
                    raise PathRefused('Invalid source name')
                file = checked_path(self.wiki, f'raw/sources/{name}')
            elif path in ('run.json', 'sources-index.md') or (path.startswith('conversations/') and path.endswith('.md')):
                file = checked_path(self.inbox, f'{self.run_id}/{path}')
            else:
                raise PathRefused('Input is outside the drafting allowlist')
            if file.stat().st_size > 2 * 1024 * 1024:
                raise DraftRefused('Input exceeds the two-megabyte limit')
            data = file.read_bytes()
            text = data.decode('utf-8')
            if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 20000:
                raise DraftRefused('Invalid text range')
            end = min(offset + limit, len(text))
            return dict(text=text[offset:end], sha256=hashlib.sha256(data).hexdigest(),
                        truncated=end < len(text), next_offset=end if end < len(text) else None,
                        total_characters=len(text))
        except (PathRefused, OSError, UnicodeError) as exc:
            raise DraftRefused(str(exc)) from exc

    def submit(self, name: str, metadata: dict, source: str | None) -> str:
        try:
            identifier(name)
            allowed = {'kind', 'target', 'summary', 'why', 'evidence_ids', 'base_sha256', 'evidence_requests'}
            if not isinstance(metadata, dict) or set(metadata) - allowed:
                raise DraftRefused('Unsupported candidate fields')
            if metadata.get('kind') not in ('new', 'update', 'retire') or not isinstance(metadata.get('target'), str) or not NAME_RE.fullmatch(metadata['target']):
                raise DraftRefused('Invalid candidate kind or target')
            for field in ('summary', 'why'):
                if not isinstance(metadata.get(field), str) or not 1 <= len(metadata[field]) <= 2000:
                    raise DraftRefused(f'Invalid {field}')
            if not isinstance(metadata.get('evidence_ids'), list):
                raise DraftRefused('Invalid evidence identifiers')
            target = checked_path(self.wiki, f"raw/sources/{metadata['target']}")
            base_bytes = target.read_bytes() if target.is_file() else None
            base = hashlib.sha256(base_bytes).hexdigest() if base_bytes is not None else None
            if metadata['kind'] == 'new' and target.exists():
                raise DraftRefused('New target already exists')
            if metadata['kind'] != 'new' and (base is None or metadata.get('base_sha256') != base):
                raise DraftRefused('Update or retirement requires the exact current base hash')
            try:
                requested = {r['id'] for r in evidence_requests.requests_of(metadata)}
                evidence_requests.check_new_ids(self.wiki, evidence_requests.requests_of(metadata))
            except evidence_requests.RequestRefused as exc:
                raise DraftRefused(str(exc)) from exc
            if requested and metadata['kind'] == 'retire':
                raise DraftRefused('A retirement cannot request evidence')
            retained = [value for value in metadata['evidence_ids'] if value not in requested]
            if retained:
                self._retained_only(metadata, base_bytes, retained)
            if metadata['kind'] == 'retire':
                if source is not None:
                    raise DraftRefused('Retirement cannot include replacement text')
            elif not isinstance(source, str) or len(source.encode('utf-8')) > 262144 or check_format(source):
                raise DraftRefused('Invalid or oversized proposed source')
            if metadata['kind'] != 'retire':
                try:
                    validate_source_citations(source, metadata['evidence_ids'])
                except Refused as exc:
                    raise DraftRefused(RETAINED_ONLY + f' ({exc})') from exc
                refusals = content_refusals(source, base_bytes.decode('utf-8') if base_bytes is not None else '')
                if refusals:
                    raise DraftRefused('Approval would refuse this draft; fix it and submit again: ' + ' | '.join(refusals))
            folder = checked_path(self.inbox, f'{self.run_id}/candidates/{name}')
            encoded = (json.dumps(metadata, sort_keys=True, separators=(',', ':')) + '\n').encode()
            source_bytes = source.encode() if source is not None else None
            if folder.exists():
                if (folder / 'candidate.json').read_bytes() != encoded or ((folder / 'source.md').read_bytes() if (folder / 'source.md').exists() else None) != source_bytes:
                    raise DraftRefused('Existing draft is immutable; submit a new candidate name')
                return f'{self.run_id}/{name}'
            folder.parent.mkdir(parents=True, exist_ok=True)
            folder.mkdir()
            if source_bytes is not None:
                with (folder / 'source.md').open('xb') as f:
                    f.write(source_bytes)
            if metadata['kind'] == 'update':
                with (folder / 'base.md').open('xb') as f:
                    f.write(base_bytes)
            with (folder / 'candidate.json').open('xb') as f:
                f.write(encoded)
            return f'{self.run_id}/{name}'
        except (PathRefused, OSError, ValueError) as exc:
            raise DraftRefused(str(exc)) from exc

    def _retained_only(self, metadata: dict, base_bytes: bytes | None, ids: list[str]) -> None:
        """Evidence ids without a request are admitted only as evidence the exact current target already cites."""
        if metadata['kind'] != 'update' or base_bytes is None:
            raise DraftRefused(RETAINED_ONLY)
        try:
            lines, table = evidence_store._evidence_texts(base_bytes.decode('utf-8'))
        except UnicodeError as exc:
            raise DraftRefused('Current target is not readable text') from exc
        retained = evidence_store.cited_ids(lines + table)
        if not set(ids) <= retained:
            raise DraftRefused(RETAINED_ONLY)
        try:
            validate_evidence_bindings(self.wiki, checked_path(self.run, 'candidates'), ids)
        except (Refused, PathRefused) as exc:
            raise DraftRefused(f'{RETAINED_ONLY} ({exc})') from exc


def main(argv=None) -> int:
    import argparse
    import sys
    import wikiconfig
    parser = argparse.ArgumentParser(description='Bounded data-only wiki drafting operations')
    parser.add_argument('operation', choices=('read', 'submit'))
    parser.add_argument('--execution-id', required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--home', required=True)
    parser.add_argument('--settings', required=True)
    args = parser.parse_args(argv)
    try:
        config = json.loads(Path(args.settings).read_bytes())
        if not config.get('hermes_home') or Path(config['hermes_home']).resolve() != Path(args.home).resolve():
            raise DraftRefused('Engine settings are not owned by the current profile')
        wiki = wikiconfig.project_root(config)
        data = Path(config['audit_dir'])
        request = json.loads(sys.stdin.buffer.read(300001))
        if not isinstance(request, dict):
            raise DraftRefused('Draft request must be an object')
        expected = {'run_id', 'path', 'offset', 'limit'} if args.operation == 'read' else {'run_id', 'name', 'metadata', 'source'}
        if set(request) - expected:
            raise DraftRefused('Unsupported draft request fields')
        adapter = DraftAdapter(wiki, data / 'inbox', request['run_id'], args.execution_id, args.job_id)
        if args.operation == 'read':
            result = adapter.read(request['path'], request.get('offset', 0), request.get('limit', 20000))
        else:
            result = {'ref': adapter.submit(request['name'], request['metadata'], request['source'])}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DraftRefused, wikiconfig.ConfigError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())


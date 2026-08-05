#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class KnowledgeStorage:
    """Project-side adapter for local files or generic AICoordinator object storage."""

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})
        self.backend = str(self.config.get('backend', 'local')).strip().lower()
        if self.backend not in {'local', 'coordinator'}:
            raise ValueError(f'unsupported knowledge storage backend: {self.backend}')
        self.project = str(self.config.get('project', 'MotherboardSearch'))
        self.namespace = str(self.config.get('namespace', 'knowledge-base'))
        self.cache_root = Path(self.config.get('cache_root', 'data/motherboard_kb/cache'))
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.coordinator_url = str(self.config.get('coordinator_url') or os.environ.get('AIW_COORDINATOR_URL') or '').rstrip('/')
        token_env = str(self.config.get('token_env', 'AIW_COORDINATOR_TOKEN'))
        self.token = str(os.environ.get(token_env) or '')
        if self.backend == 'coordinator' and not self.coordinator_url:
            raise ValueError('coordinator storage requires coordinator_url or AIW_COORDINATOR_URL')

    @property
    def collection_url(self) -> str:
        project = urllib.parse.quote(self.project, safe='')
        namespace = urllib.parse.quote(self.namespace, safe='')
        return f'{self.coordinator_url}/storage/projects/{project}/namespaces/{namespace}/objects'

    def headers(self, **extra: str) -> dict[str, str]:
        headers = {'User-Agent': 'MotherboardSearch/1.1'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        headers.update({key: value for key, value in extra.items() if value is not None})
        return headers

    def put(self, path: Path, *, metadata: dict[str, Any], content_type: str) -> dict[str, Any]:
        path = Path(path)
        if self.backend == 'local':
            return {
                'backend': 'local',
                'path': str(path),
                'object_id': None,
                'size_bytes': path.stat().st_size,
                'metadata': metadata,
            }
        request = urllib.request.Request(
            self.collection_url,
            data=path.read_bytes(),
            method='POST',
            headers=self.headers(
                **{
                    'Content-Type': content_type,
                    'X-AIWorkbench-Filename': path.name,
                    'X-AIWorkbench-Metadata': json.dumps(metadata, separators=(',', ':')),
                }
            ),
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'coordinator upload failed HTTP {exc.code}: {detail}') from exc
        return {
            'backend': 'coordinator',
            'project': self.project,
            'namespace': self.namespace,
            'object_id': payload['object_id'],
            'size_bytes': int(payload['size_bytes']),
            'metadata': metadata,
        }

    def materialize(self, record: dict[str, Any], *, suffix: str) -> Path:
        backend = record.get('backend', 'local')
        if backend == 'local':
            path = Path(record['path'])
            if not path.exists():
                raise FileNotFoundError(path)
            return path
        object_id = str(record['object_id'])
        digest = object_id.removeprefix('sha256:')
        destination = self.cache_root / f'{digest}{suffix}'
        if destination.exists() and destination.stat().st_size == int(record.get('size_bytes') or destination.stat().st_size):
            return destination
        project = urllib.parse.quote(str(record.get('project') or self.project), safe='')
        namespace = urllib.parse.quote(str(record.get('namespace') or self.namespace), safe='')
        encoded_id = urllib.parse.quote(object_id, safe=':')
        url = f'{self.coordinator_url}/storage/projects/{project}/namespaces/{namespace}/objects/{encoded_id}'
        request = urllib.request.Request(url, headers=self.headers(), method='GET')
        try:
            with urllib.request.urlopen(request, timeout=60) as response, destination.open('wb') as stream:
                shutil.copyfileobj(response, stream)
        except urllib.error.HTTPError as exc:
            destination.unlink(missing_ok=True)
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'coordinator download failed HTTP {exc.code}: {detail}') from exc
        return destination

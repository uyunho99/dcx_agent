import threading

from fastapi import APIRouter

from app.services.personas import latest_artifact, run_persona
from app.services.s3 import load_json
from app.jobs.manager import job_manager
from app.models.schemas import PersonaRequest

router = APIRouter()


@router.post('/personas')
@router.post('/persona')
def start_persona(req: PersonaRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set('persona', sid, {'status': 'running', 'progress': 0, 'phase': 'loading'})
    threading.Thread(target=lambda: run_persona(config), daemon=True).start()
    return {'sid': sid, 'status': 'started'}


def _saved_result(sid: str):
    key = latest_artifact(f'personas/{sid}/', 'result_', '.json')
    return load_json(key) if key else None


@router.get('/persona-status/{sid}')
def get_persona_status(sid: str):
    job = job_manager.get('persona', sid)
    if job.get('status') in ('running', 'done', 'error'):
        return job
    try:
        data = _saved_result(sid)
        if data:
            # Preserve v1 payloads verbatim. Reading never rewrites old artifacts.
            return {'status': 'done', 'schema_version': data.get('schema_version', 1),
                    'personas': data.get('personas', [])}
    except Exception:
        pass
    return {'status': 'not_found'}


@router.get('/sna-data/{sid}')
def get_sna_data(sid: str):
    """Render both flat v2 personas and the read-only nested v1 shape."""
    try:
        data = _saved_result(sid)
        if not data:
            return {'status': 'error', 'error': 'no persona data'}
        bk = data.get('bk', '제품')
        nodes = [{'id': 'center', 'name': bk, 'type': 'product', 'size': 40}]
        links = []
        seen = set()
        for index, entry in enumerate(data.get('personas') or []):
            if not isinstance(entry, dict):
                continue
            is_v2 = isinstance(entry.get('persona_id'), str)
            cid = entry['persona_id'].rsplit('-P', 1)[0] if is_v2 else entry.get('cluster_id', index)
            cluster_node = f'cluster_{cid}'
            if cluster_node not in seen:
                seen.add(cluster_node)
                nodes.append({'id': cluster_node, 'name': entry.get('cluster_name') or str(cid),
                              'type': 'cluster', 'size': 15})
                links.append({'source': 'center', 'target': cluster_node, 'value': 1})
            children = [entry] if is_v2 else entry.get('personas') or []
            for i, persona in enumerate(children):
                if not isinstance(persona, dict):
                    continue
                pid = persona['persona_id'] if is_v2 else f'persona_{index}_{i}'
                node = {'id': pid, 'name': persona.get('name') or persona.get('desire', ''),
                        'type': 'persona', 'size': 12}
                fields = ('desire', 'goals', 'centrality_top', 'modularity_q', 'status') if is_v2 else ('pain_point', 'insight')
                node.update({field: persona[field] for field in fields if field in persona})
                nodes.append(node)
                links.append({'source': cluster_node, 'target': pid, 'value': 1})
        return {'status': 'ok', 'nodes': nodes, 'links': links, 'bk': bk}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}

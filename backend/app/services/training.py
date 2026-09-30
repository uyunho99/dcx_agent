"""Compatibility reader for legacy training results; training moved to model/.

The legacy /train router may still invoke train_models on its background thread.
That operation only reads a saved result into the existing status projection.
No TensorFlow/sklearn training, classification, or artifact writes remain here.
"""
from app.services.s3 import load_json
from app.context import store
from app.jobs.manager import job_manager


def train_models(config: dict) -> None:
    sid = config.get('sid', 's0')
    try:
        data = store.load_session(sid) or {}
        if data and not store.is_legacy(data):
            result = {'status': 'error', 'readonly': True, 'error': '새 세션은 새 학습 화면을 사용하세요.'}
        else:
            saved = data.get('training') or load_json(f'sessions/{sid}/stage_5.json') or {}
            result = {**saved, 'status': saved.get('status', 'done' if saved else 'not_found'), 'readonly': True}
        job_manager.set('train', sid, result)
    except (OSError, ValueError):
        job_manager.set('train', sid, {'status': 'error', 'readonly': True, 'error': '기존 결과를 읽지 못했습니다.'})

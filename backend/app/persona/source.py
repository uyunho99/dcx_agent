"""Read-only publication guards; safe while holding the session lock."""
from app.context import store as sessions
from app.persona.package import load_package, PackageMissing, evidence_ready


def require_persona(data):
    if ('stage8' in data.get('stale', {}) or
            data.get('persona', {}).get('status') == 'stale'):
        raise sessions.StoreError('근거 또는 확정값이 바뀌었습니다. 페르소나를 다시 만들어 주세요.', 409, 'stale')
    if data.get('persona', {}).get('status') != 'done':
        raise sessions.StoreError('페르소나를 만든 뒤 인사이트를 도출할 수 있습니다.', 409, 'persona_required')


class SourceChanged(Exception):
    pass


class Source:
    def __init__(self, sid, version):
        from app.persona.pipeline import _digest
        self.sid, self.version = sid, version
        data = sessions.assert_writable(sid, version)
        require_persona(data)
        self.generation = self._generation(data)
        from app.persona.store import PersonaStore
        package = load_package(sid, version)
        cards = PersonaStore.open(sid, version).read('cards') or {}
        self.digest = cards.get('package_hash', _digest(package))
        self.package_run = cards.get('package_run', package.run)

    @staticmethod
    def _generation(data):
        persona = data.get('persona', {})
        return persona.get('run'), persona.get('reset_epoch')

    def check(self):
        from app.persona.pipeline import _digest, _confirmed_matches
        data = sessions.assert_writable(self.sid, self.version)
        if self._generation(data) != self.generation:
            raise SourceChanged('Persona generation changed')
        require_persona(data)
        try:
            package = load_package(self.sid, self.version)
            valid = (evidence_ready(self.sid, self.version) and package.run == self.package_run and _digest(package) == self.digest and
                     _confirmed_matches(self.sid, self.version, package))
        except PackageMissing:
            valid = False
        if not valid:
            raise sessions.StoreError('Persona source changed', 409, 'stale')

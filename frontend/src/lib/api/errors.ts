export const versionQuery = (path: string, version?: string) => version ? `${path}${path.includes('?') ? '&' : '?'}version=${encodeURIComponent(version)}` : path;
const genericError = '요청에 실패했습니다. 다시 시도하세요.';
const hasHangul = (message: string) => /[가-힣]/.test(message);
const messages: Record<string, string> = {
 crawl_unfinished: '크롤링 수집을 끝낸 뒤 새 버전을 만드세요.',
 storage_error: '저장 공간에 쓰지 못했습니다. 디스크 여유 공간을 확인하고 이어서 진행하세요.',
 no_collection: '선택된 수집본이 없습니다. 목록 수집을 시작하세요.',
 snapshot_conflict: '다른 상세 수집 대상이 이미 선택되었습니다. 수집 상태를 다시 확인하세요.',
 no_unfinished_phase: '이어서 진행할 수집 작업이 없습니다. 수집 상태를 다시 확인하세요.',
 gate_not_editable: '지금은 검토 게이트를 수정할 수 없습니다. 목록 수집 완료 후 다시 확인하세요.',
 sources_unavailable: '선택한 채널을 사용할 수 없습니다. 수집 설정에서 사용 가능한 채널을 선택하세요.',
 worker_running: '수집 작업이 진행 중입니다. 작업이 끝난 뒤 다시 시도하세요.',
 invalid_request: '요청한 입력값이 올바르지 않습니다. 입력값을 확인하고 다시 시도하세요.',
 unknown_resume_channel: '재개할 채널이 수집본에 없습니다. 수집 상태를 다시 확인하세요.',
 p1_unfinished: '목록 수집이 끝나지 않았습니다. 목록 수집을 완료한 뒤 상세 수집을 시작하세요.',
 finished_collection: '이미 완료된 수집본입니다. 새 수집을 시작하세요.',
 readonly_version: '읽기 전용 버전은 수정할 수 없습니다. 활성 버전을 여세요.',
 version_conflict: '다른 버전이 활성화되었습니다. 활성 버전을 열고 다시 시도하세요.',
};
export function responseError(data: {error?: {code?: string; message?: string}; detail?: string | {msg?: string}[]}, status: number): string {
 if(status === 409 && (data.error?.code === 'version_conflict' || data.error?.message?.includes('다른 버전이 활성화되었습니다')) && typeof window !== 'undefined') window.dispatchEvent(new Event('dcx-version-conflict'));
 const code = data.error?.code ?? '';
 if (Object.hasOwn(messages, code)) return messages[code];
 const message = data.error?.message ?? '';
 return hasHangul(message) ? message : genericError;
}
export function displayError(error: unknown, fallback = genericError): string {
 return error instanceof Error && hasHangul(error.message) ? error.message : fallback;
}

export const versionQuery = (path: string, version?: string) => version ? `${path}${path.includes('?') ? '&' : '?'}version=${encodeURIComponent(version)}` : path;
export function responseError(data: {error?: {message?: string}; detail?: string | {msg?: string}[]}, status: number): string {
 const message = data.error?.message || (typeof data.detail === 'string' ? data.detail : data.detail?.map(e => e.msg).filter(Boolean).join(' · ')) || '요청에 실패했습니다. 다시 시도하세요.';
 if(status === 409 && message.includes('다른 버전이 활성화되었습니다') && typeof window !== 'undefined') window.dispatchEvent(new Event('dcx-version-conflict'));
 return message;
}

export function popoverKeyAction(targetTag: string, key: string, isComposing = false, keyCode?: number): 'submit' | 'native' {
  return !isComposing && keyCode !== 229 && key === 'Enter' && targetTag.toLowerCase() !== 'button' ? 'submit' : 'native';
}

export function isMoveShortcut(event: { code: string; key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; isComposing: boolean }): boolean {
  return event.code === 'KeyM' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.isComposing;
}

export function createActionQueue() {
  let tail: Promise<void> = Promise.resolve();
  return (action: () => Promise<void>): Promise<void> => {
    const result = tail.then(action);
    tail = result.catch(() => {});
    return result;
  };
}

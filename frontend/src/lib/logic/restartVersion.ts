// Finish all fallible fetching before the caller changes the mounted version.
export async function prepareRestartVersion<T>(create: () => Promise<{version: string}>, load: (version: string) => Promise<{data: T}>) {
  const {version} = await create();
  const {data} = await load(version);
  return {version, data};
}

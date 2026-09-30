import { describe, expect, it } from 'vitest';
import { resolveVersionSelection } from './versionSelection';

describe('resolveVersionSelection', () => {
  it('starts a new session at its active version', () => {
    expect(resolveVersionSelection(undefined, { activeVersion: 'v2' })).toEqual({ version: 'v2', newerVersion: undefined });
  });
  it('keeps edits on the selected version when another tab creates a version', () => {
    expect(resolveVersionSelection('v2', { activeVersion: 'v3' })).toEqual({ version: 'v2', newerVersion: 'v3' });
  });
  it('keeps an explicitly selected historical version', () => {
    expect(resolveVersionSelection('v1', { activeVersion: 'v3' }).version).toBe('v1');
  });
  it('clears the notice after explicitly opening the active version', () => {
    expect(resolveVersionSelection('v3', { activeVersion: 'v3' }).newerVersion).toBeUndefined();
  });
});

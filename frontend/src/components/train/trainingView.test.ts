import { describe, expect, it } from 'vitest';
import { record, number, percent, trainingState, mlpDifference, ensembleModels } from './trainingView';

describe('training presentation contract', () => {
  it('does not invent absent or invalid metrics', () => {
    expect(record(null)).toEqual({});
    expect(record([])).toEqual({});
    expect(number(NaN)).toBeUndefined();
    expect(number('88')).toBeUndefined();
    expect(percent(undefined)).toBe('확인 불가');
    expect(percent(.88)).toBe('88%');
    expect(percent(0)).toBe('0%');
  });
  it('waits for inference and prevents exporting a previous result during retraining', () => {
    expect(trainingState({training:{modelId:'old'},workers:[{runId:'r',kind:'train',state:'running',progress:.1,detail:{}}]}).busy).toBe(true);
    expect(trainingState({training:{modelId:'m',inferStatus:'running'}}).ready).toBe(false);
    expect(trainingState({training:{modelId:'m',inferStatus:'done'}}).ready).toBe(true);
    expect(trainingState({training:{}}).ready).toBe(false);
  });
  it('surfaces stopped workers instead of leaving a permanent spinner', () => {
    const state = trainingState({training:{modelId:'m',inferStatus:'running'},workers:[{runId:'r',kind:'infer',state:'failed',progress:.3,detail:{},error:'실패'}]});
    expect(state.busy).toBe(false);
    expect(state.ready).toBe(false);
    expect(state.error).toBe('실패');
  });
  it('compares three MLP members with the linear member only with complete measurements', () => {
    expect(mlpDifference({members:[{grade_accuracy:.9},{grade_accuracy:.8},{grade_accuracy:.85},{grade_accuracy:.8}]})).toBeCloseTo(5);
    expect(mlpDifference({members:[{grade_accuracy:.9}]})).toBeUndefined();
  });
  it('never shows distilled registry rows', () => {
    expect(ensembleModels([{modelId:'a',kind:'ensemble'},{modelId:'b',kind:'distilled'}]).map(m=>m.modelId)).toEqual(['a']);
  });
});

import { exportAndAdvance } from './trainingView';
import { vi } from 'vitest';
it('advances only after export and PATCH succeed', async () => {
  const order: string[] = [];
  await exportAndAdvance(async () => { order.push('export'); }, async () => { order.push('patch'); }, () => { order.push('navigate'); });
  expect(order).toEqual(['export','patch','navigate']);
  const next = vi.fn();
  await expect(exportAndAdvance(async () => { throw Error('export failed'); }, next, next)).rejects.toThrow('export failed');
  expect(next).not.toHaveBeenCalled();
  await expect(exportAndAdvance(async () => {}, async () => { throw Error('patch failed'); }, next)).rejects.toThrow('patch failed');
  expect(next).not.toHaveBeenCalled();
});

import { trainingLabels, modelDate, driftMessage, shouldPollTraining } from './trainingView';
it('uses accepted labels for the count and empty state', () => {
 expect(trainingLabels({accepted:0, merged:25})).toEqual({count:0, empty:true});
 expect(trainingLabels({accepted:12, merged:0})).toEqual({count:12, empty:false});
 expect(trainingLabels(null).empty).toBe(false);
});
it('formats model date without time and requires a model for drift', () => {
 expect(modelDate('2026-10-02T12:00:00')).toBe('2026. 10. 2.');
 expect(modelDate('invalid')).toBe('—');
 expect(driftMessage(false,.18)).toBeNull();
 expect(driftMessage(true,.15)).toBeNull();
 expect(driftMessage(true,.18)).toContain('18% 엇갈렸습니다');
});
it('polls active work and stops at idle, done or failed', () => {
 for (const inferStatus of ['idle','done','failed']) expect(shouldPollTraining({training:{inferStatus,runId:'old'}})).toBe(false);
 expect(shouldPollTraining({training:{inferStatus:'running'}})).toBe(true);
 expect(shouldPollTraining({training:{},workers:[{runId:'r',kind:'train',state:'running',progress:0,detail:{}}]})).toBe(true);
 expect(shouldPollTraining({training:{inferStatus:'running'},workers:[{runId:'r',kind:'infer',state:'failed',progress:0,detail:{}}]})).toBe(false);
});

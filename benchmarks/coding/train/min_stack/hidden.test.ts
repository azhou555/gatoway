import test from 'node:test';
import assert from 'node:assert/strict';
import { MinStack } from './solution.ts';
test('trace 0', () => {
  const obj = new MinStack(...[] as any);
  assert.deepEqual(obj.push(...[3] as any), undefined);
  assert.deepEqual(obj.push(...[1] as any), undefined);
  assert.deepEqual(obj.getMin(...[] as any), 1);
  assert.deepEqual(obj.pop(...[] as any), 1);
  assert.deepEqual(obj.getMin(...[] as any), 3);
});
test('trace 1', () => {
  const obj = new MinStack(...[] as any);
  assert.deepEqual(obj.top(...[] as any), undefined);
  assert.deepEqual(obj.pop(...[] as any), undefined);
  assert.deepEqual(obj.getMin(...[] as any), undefined);
});
test('trace 2', () => {
  const obj = new MinStack(...[] as any);
  assert.deepEqual(obj.push(...[1] as any), undefined);
  assert.deepEqual(obj.push(...[1] as any), undefined);
  assert.deepEqual(obj.pop(...[] as any), 1);
  assert.deepEqual(obj.getMin(...[] as any), 1);
});
test('trace 3', () => {
  const obj = new MinStack(...[] as any);
  assert.deepEqual(obj.push(...[-3] as any), undefined);
  assert.deepEqual(obj.push(...[-5] as any), undefined);
  assert.deepEqual(obj.top(...[] as any), -5);
  assert.deepEqual(obj.getMin(...[] as any), -5);
});
test('trace 4', () => {
  const obj = new MinStack(...[] as any);
  assert.deepEqual(obj.push(...[0] as any), undefined);
  assert.deepEqual(obj.pop(...[] as any), 0);
  assert.deepEqual(obj.getMin(...[] as any), undefined);
});

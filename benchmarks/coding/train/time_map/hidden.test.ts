import test from 'node:test';
import assert from 'node:assert/strict';
import { TimeMap } from './solution.ts';
test('trace 0', () => {
  const obj = new TimeMap(...[] as any);
  assert.deepEqual(obj.set(...["a", "one", 1] as any), undefined);
  assert.deepEqual(obj.set(...["a", "three", 3] as any), undefined);
  assert.deepEqual(obj.get(...["a", 2] as any), "one");
  assert.deepEqual(obj.get(...["a", 3] as any), "three");
});
test('trace 1', () => {
  const obj = new TimeMap(...[] as any);
  assert.deepEqual(obj.get(...["missing", 10] as any), undefined);
});
test('trace 2', () => {
  const obj = new TimeMap(...[] as any);
  assert.deepEqual(obj.set(...["a", "v", 5] as any), undefined);
  assert.deepEqual(obj.get(...["a", 4] as any), undefined);
  assert.deepEqual(obj.get(...["a", 99] as any), "v");
});
test('trace 3', () => {
  const obj = new TimeMap(...[] as any);
  assert.deepEqual(obj.set(...["a", "x", 1] as any), undefined);
  assert.deepEqual(obj.set(...["a", "y", 1] as any), undefined);
  assert.deepEqual(obj.get(...["a", 1] as any), "y");
});
test('trace 4', () => {
  const obj = new TimeMap(...[] as any);
  assert.deepEqual(obj.set(...["a", "x", 2] as any), undefined);
  assert.deepEqual(obj.set(...["b", "y", 1] as any), undefined);
  assert.deepEqual(obj.get(...["a", 2] as any), "x");
  assert.deepEqual(obj.get(...["b", 1] as any), "y");
});

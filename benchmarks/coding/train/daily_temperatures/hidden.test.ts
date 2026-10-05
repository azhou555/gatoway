import test from 'node:test';
import assert from 'node:assert/strict';
import { dailyTemperatures } from './solution.ts';
test('case 0', () => assert.deepEqual(dailyTemperatures(...[[73, 74, 75, 71, 69, 72, 76, 73]] as any), [1, 1, 4, 2, 1, 1, 0, 0]));
test('case 1', () => assert.deepEqual(dailyTemperatures(...[[]] as any), []));
test('case 2', () => assert.deepEqual(dailyTemperatures(...[[5, 5, 6]] as any), [2, 1, 0]));
test('case 3', () => assert.deepEqual(dailyTemperatures(...[[3, 2, 1]] as any), [0, 0, 0]));
test('case 4', () => assert.deepEqual(dailyTemperatures(...[[1]] as any), [0]));

import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateRpn } from './solution.ts';
test('case 0', () => assert.deepEqual(evaluateRpn(...[["2", "1", "+", "3", "*"]] as any), 9));
test('case 1', () => assert.deepEqual(evaluateRpn(...[["4", "13", "5", "/", "+"]] as any), 6));
test('case 2', () => assert.deepEqual(evaluateRpn(...[["-7", "3", "/"]] as any), -2));
test('case 3', () => assert.deepEqual(evaluateRpn(...[["3", "8", "-"]] as any), -5));
test('case 4', () => assert.deepEqual(evaluateRpn(...[["42"]] as any), 42));
test('case 5', () => assert.ok(evaluateRpn(...[["1", "-2", "/"]] as any) === 0));

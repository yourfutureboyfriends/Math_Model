import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { getApiBaseUrl, getWebSocketUrl, getWsBaseUrl } from './network';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it('ships no unexpanded ${...} template in the production env file', () => {
  // Vite loads .env values literally, so a templated URL reaches the browser verbatim.
  // Vitest's root is frontend/, and import.meta.url is not a file: URL under the transform.
  const env = readFileSync(resolve(process.cwd(), '.env.production'), 'utf8');
  const offenders = env
    .split('\n')
    .filter((line) => !line.startsWith('#'))
    .filter((line) => line.includes('${'));
  expect(offenders).toEqual([]);
});

it('builds a same-origin socket URL from a relative API base', () => {
  vi.stubEnv('VITE_API_URL', '/api');
  vi.stubEnv('VITE_WS_URL', '');
  const { protocol, host } = window.location;
  expect(getWsBaseUrl()).toBe(`${protocol}//${host}`);
  expect(getWebSocketUrl('/ws/prices')).toBe(`${protocol}//${host}/ws/prices`);
});

it('never emits an unexpanded env template or a doubled /ws prefix', () => {
  vi.stubEnv('VITE_API_URL', '/api');
  vi.stubEnv('VITE_WS_URL', '');
  const url = getWebSocketUrl('/ws/prices');
  expect(url).not.toContain('${');
  expect(url.match(/\/ws/g)).toHaveLength(1);
});

it('upgrades an absolute API base to the matching socket scheme', () => {
  vi.stubEnv('VITE_API_URL', 'https://macro.example.com/api');
  vi.stubEnv('VITE_WS_URL', '');
  expect(getWebSocketUrl('/ws/prices')).toBe('wss://macro.example.com/api/ws/prices');
});

it('honours an explicit absolute VITE_WS_URL over derivation', () => {
  vi.stubEnv('VITE_WS_URL', 'wss://socket.example.com/');
  expect(getWsBaseUrl()).toBe('wss://socket.example.com');
  expect(getWebSocketUrl('ws/prices')).toBe('wss://socket.example.com/ws/prices');
});

it('falls back to the backend port when no API base is configured', () => {
  vi.stubEnv('VITE_API_URL', '');
  vi.stubEnv('VITE_WS_URL', '');
  expect(getApiBaseUrl()).toBe('http://localhost:8000');
  expect(getWebSocketUrl('/ws/prices')).toBe('ws://localhost:8000/ws/prices');
});

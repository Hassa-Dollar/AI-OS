import { describe, it, expect } from 'vitest';
import type { AddressInfo } from 'node:net';
import { createApp } from '../app';
import { health } from './health';

async function start(): Promise<{ url: string; close: () => Promise<void> }> {
  const server = createApp([health]);
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

describe('GET /health', () => {
  it('returns 200 and JSON body with status "ok"', async () => {
    const app = await start();
    try {
      const res = await fetch(`${app.url}/health`);
      expect(res.status).toBe(200);
      const body = (await res.json()) as Record<string, unknown>;
      expect(body.status).toBe('ok');
    } finally {
      await app.close();
    }
  });

  it('returns uptime_s as a non-negative integer', async () => {
    const app = await start();
    try {
      const res = await fetch(`${app.url}/health`);
      const body = (await res.json()) as Record<string, unknown>;
      expect(typeof body.uptime_s).toBe('number');
      expect(Number.isInteger(body.uptime_s as number)).toBe(true);
      expect(body.uptime_s as number).toBeGreaterThanOrEqual(0);
    } finally {
      await app.close();
    }
  });
});
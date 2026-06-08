import { describe, it, expect } from 'vitest';
import type { AddressInfo } from 'node:net';
import { createApp, type Route } from './app';

async function start(routes: Route[]): Promise<{ url: string; close: () => Promise<void> }> {
  const server = createApp(routes);
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}`,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

describe('createApp', () => {
  it('404s an unknown route', async () => {
    const app = await start([]);
    try {
      const res = await fetch(`${app.url}/nope`);
      expect(res.status).toBe(404);
      expect(await res.json()).toEqual({ error: 'not_found' });
    } finally {
      await app.close();
    }
  });

  it('dispatches a matching route', async () => {
    const ping: Route = {
      method: 'GET',
      path: '/ping',
      handler: (_req, res) => {
        res.statusCode = 200;
        res.end('pong');
      },
    };
    const app = await start([ping]);
    try {
      const res = await fetch(`${app.url}/ping`);
      expect(res.status).toBe(200);
      expect(await res.text()).toBe('pong');
    } finally {
      await app.close();
    }
  });
});

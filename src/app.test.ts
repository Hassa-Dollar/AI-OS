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

  it('matches route by pathname, ignoring query string', async () => {
    const health: Route = {
      method: 'GET',
      path: '/health',
      handler: (_req, res) => {
        res.statusCode = 200;
        res.setHeader('content-type', 'application/json');
        res.end(JSON.stringify({ status: 'ok' }));
      },
    };
    const app = await start([health]);
    try {
      const [bare, withQuery] = await Promise.all([
        fetch(`${app.url}/health`),
        fetch(`${app.url}/health?probe=1`),
      ]);
      expect(bare.status).toBe(200);
      expect(withQuery.status).toBe(200);
      expect(await withQuery.json()).toEqual(await bare.json());
    } finally {
      await app.close();
    }
  });

  it('does not match a near-miss path like /healthx against /health', async () => {
    const health: Route = {
      method: 'GET',
      path: '/health',
      handler: (_req, res) => {
        res.statusCode = 200;
        res.end('ok');
      },
    };
    const app = await start([health]);
    try {
      const res = await fetch(`${app.url}/healthx`);
      expect(res.status).toBe(404);
      expect(await res.json()).toEqual({ error: 'not_found' });
    } finally {
      await app.close();
    }
  });

  it('404s an unknown path even with a query string', async () => {
    const app = await start([]);
    try {
      const res = await fetch(`${app.url}/nope?x=1`);
      expect(res.status).toBe(404);
      expect(await res.json()).toEqual({ error: 'not_found' });
    } finally {
      await app.close();
    }
  });
});

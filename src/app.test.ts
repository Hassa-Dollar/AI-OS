import { describe, it, expect } from 'vitest';
import type { AddressInfo } from 'node:net';
import { connect } from 'node:net';
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

/** Send a raw GET request by TCP to avoid URL normalization that fetch() performs. */
function rawGet(port: number, path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = connect(port, '127.0.0.1', () => {
      client.write(`GET ${path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n`);
    });
    let data = '';
    client.on('data', (chunk: string) => {
      data += chunk;
    });
    client.on('end', () => {
      resolve(data.split('\r\n', 1)[0] ?? '');
    });
    client.on('error', reject);
  });
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

  it('does NOT match /../health against /health (path normalization leak)', async () => {
    const health: Route = {
      method: 'GET',
      path: '/health',
      handler: (_req, res) => {
        res.statusCode = 200;
        res.end('ok');
      },
    };
    const server = createApp([health]);
    await new Promise<void>((resolve) => server.listen(0, resolve));
    const { port } = server.address() as AddressInfo;
    try {
      const statusLine = await rawGet(port, '/../health');
      expect(statusLine).toMatch(/^HTTP\/1\.[01] 404 /);
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });

  it('does NOT match /./health against /health (dot-segment leak)', async () => {
    const health: Route = {
      method: 'GET',
      path: '/health',
      handler: (_req, res) => {
        res.statusCode = 200;
        res.end('ok');
      },
    };
    const server = createApp([health]);
    await new Promise<void>((resolve) => server.listen(0, resolve));
    const { port } = server.address() as AddressInfo;
    try {
      const statusLine = await rawGet(port, '/./health');
      expect(statusLine).toMatch(/^HTTP\/1\.[01] 404 /);
    } finally {
      await new Promise<void>((r) => server.close(() => r()));
    }
  });
});

import { createServer, type IncomingMessage, type ServerResponse, type Server } from 'node:http';

/** One HTTP route. Handlers stay thin — see AGENTS.md §4 and architecture/invariants.md #3. */
export interface Route {
  method: string;
  path: string;
  handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>;
}

/** Build an HTTP server that dispatches by exact method + path, and 404s everything else. */
export function createApp(routes: Route[]): Server {
  return createServer((req, res) => {
    // Match on the path only. Strip the query manually — NOT via `new URL().pathname`,
    // which normalizes dot-segments (`/../health` → `/health`) and would defeat exact matching.
    const pathname = (req.url ?? '/').split('?')[0] ?? '/';
    const route = routes.find((r) => r.method === req.method && r.path === pathname);
    if (route === undefined) {
      const pathMatched = routes.filter((r) => r.path === pathname);
      if (pathMatched.length > 0) {
        const allow = [...new Set(pathMatched.map((r) => r.method))].sort().join(', ');
        res.statusCode = 405;
        res.setHeader('content-type', 'application/json');
        res.setHeader('allow', allow);
        res.end(JSON.stringify({ error: 'method_not_allowed' }));
        return;
      }
      res.statusCode = 404;
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ error: 'not_found' }));
      return;
    }
    Promise.resolve(route.handler(req, res)).catch(() => {
      if (!res.headersSent) res.statusCode = 500;
      res.end();
    });
  });
}

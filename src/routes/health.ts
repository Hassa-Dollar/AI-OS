import type { Route } from '../app';

export const health: Route = {
  method: 'GET',
  path: '/health',
  handler: (_req, res) => {
    const uptime_s = Math.floor(process.uptime());
    res.statusCode = 200;
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ status: 'ok', uptime_s }));
  },
};
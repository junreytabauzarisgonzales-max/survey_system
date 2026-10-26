import http from 'node:http';
import path from 'node:path';
import dotenv from 'dotenv';
import handler from '../api/live.js';

dotenv.config({ path: path.resolve('.env.local') });

const port = Number(process.env.REALTIME_SEAL_PORT || 8790);
const server = http.createServer((request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || '127.0.0.1'}`);
  if (url.pathname !== '/api/live') {
    response.statusCode = 404;
    response.end(JSON.stringify({ error: 'Not found' }));
    return;
  }
  handler(request, response).catch(() => {
    response.statusCode = 503;
    response.end(JSON.stringify({ error: 'Live results are unavailable' }));
  });
});

server.listen(port, '127.0.0.1', () => {
  console.log(`Realtime seal server listening on http://127.0.0.1:${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

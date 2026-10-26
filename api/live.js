import { createHash } from 'node:crypto';
import { createRealtime, rawSql } from '@neon/realtime/server';
import pg from 'pg';

const { Pool } = pg;

function connectionString() {
  const url = process.env.DATABASE_URL || '';
  return url.replace(/([?&])channel_binding=require&?/i, '$1').replace(/[?&]$/, '');
}

function databaseName() {
  try {
    return new URL(process.env.DATABASE_URL).pathname.replace(/^\//, '');
  } catch {
    return '';
  }
}

let pool;
let realtime;

function shared() {
  if (!pool) {
    pool = new Pool({ connectionString: connectionString(), max: 2 });
    pool.on('error', () => {});
  }
  if (!realtime) {
    if (!process.env.NEON_REALTIME_SECRET || !databaseName()) return null;
    realtime = createRealtime({ secret: process.env.NEON_REALTIME_SECRET, db: databaseName() });
  }
  return { pool, realtime };
}

function reply(response, status, body) {
  response.statusCode = status;
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.setHeader('Cache-Control', 'no-store');
  response.end(JSON.stringify(body));
}

export default async function handler(request, response) {
  if (request.method !== 'GET') return reply(response, 405, { error: 'Method not allowed' });
  const clients = shared();
  if (!clients) return reply(response, 503, { error: 'Realtime is not configured' });
  const url = new URL(request.url, 'http://localhost');
  const project = url.searchParams.get('project') || '';
  if (!/^[0-9a-f-]{36}$/i.test(project)) return reply(response, 400, { error: 'A valid project ID is required' });

  const token = String(request.headers.authorization || '').replace(/^Bearer\s+/i, '');
  if (!token) return reply(response, 401, { error: 'Sign in required' });
  const tokenHash = createHash('sha256').update(token).digest('hex');
  const now = new Date().toISOString();

  try {
    const session = await clients.pool.query(
      'SELECT u.id,u.admin FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires>$2 AND u.active=1',
      [tokenHash, now],
    );
    const user = session.rows[0];
    if (!user) return reply(response, 401, { error: 'Sign in required' });
    const access = await clients.pool.query(
      'SELECT p.id FROM projects p LEFT JOIN memberships m ON m.project_id=p.id AND m.user_id=$2 WHERE p.id=$1 AND ($3::boolean OR m.user_id IS NOT NULL)',
      [project, user.id, Boolean(user.admin)],
    );
    if (!access.rows.length) return reply(response, 403, { error: 'Project access denied' });

    const sealed = await clients.realtime.seal({
      query: rawSql(
        'SELECT i.project_id, COUNT(*)::text AS response_count, MAX(i.updated_at) AS latest_at FROM interviews i WHERE i.project_id = $1 GROUP BY i.project_id',
        [project],
      ),
    });
    return reply(response, 200, sealed);
  } catch {
    return reply(response, 503, { error: 'Live results are unavailable' });
  }
}

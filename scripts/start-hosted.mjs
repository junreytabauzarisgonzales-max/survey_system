import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve('.env.local') });

const python = process.env.PYTHON
  || (fs.existsSync(path.resolve('.venv/Scripts/python.exe')) ? path.resolve('.venv/Scripts/python.exe') : 'python');
const realtimePort = process.env.REALTIME_SEAL_PORT || '8790';
const appPort = process.env.PORT || '8765';

const children = [];
function start(command, args, env) {
  const child = spawn(command, args, { stdio: 'inherit', env });
  children.push(child);
  child.on('exit', code => {
    if (code && code !== 0) {
      console.error(`${path.basename(command)} exited with code ${code}`);
      stop(code);
    }
  });
  return child;
}

function stop(code = 0) {
  for (const child of children) {
    if (!child.killed) child.kill();
  }
  process.exit(code);
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => stop(0));
}

start(process.execPath, ['scripts/realtime-server.mjs'], {
  ...process.env,
  REALTIME_SEAL_PORT: realtimePort,
});

start(python, ['-m', 'backend.serve_hosted'], {
  ...process.env,
  AUTO_MIGRATE: process.env.AUTO_MIGRATE || '1',
  HOST: process.env.HOST || '127.0.0.1',
  PORT: appPort,
  REALTIME_SEAL_URL: `http://127.0.0.1:${realtimePort}`,
});

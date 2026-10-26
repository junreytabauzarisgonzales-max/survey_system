import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {copyFile, mkdir, open, readFile, stat, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const web = fileURLToPath(new URL('../', import.meta.url));
const root = path.dirname(web);
const destination = path.join(web, 'public', 'releases');
const {version} = JSON.parse(await readFile(path.join(web, 'package.json'), 'utf8'));
await mkdir(destination, {recursive:true});

async function exists(file) {
  try { return (await stat(file)).isFile(); }
  catch (error) { if (error.code === 'ENOENT') return false; throw error; }
}

async function prepare(platform, filename, candidates, environment, kind) {
  if (process.env[environment]) {
    const url = new URL(process.env[environment]);
    if (url.protocol !== 'https:' || url.username || url.password || !url.pathname.toLowerCase().endsWith(path.extname(filename))) {
      throw new Error(`${environment} must be a public HTTPS URL to a ${path.extname(filename)} file.`);
    }
    return {platform, filename, url:url.href, kind, version, bytes:null, sha256:null};
  }
  let source;
  for (const candidate of candidates) {
    if (await exists(candidate)) { source = candidate; break; }
  }
  if (!source) return {platform, filename, url:null, kind, version, bytes:null, sha256:null};
  const file = await open(source, 'r');
  const signature = Buffer.alloc(4);
  try { await file.read(signature, 0, 4, 0); } finally { await file.close(); }
  if (filename.endsWith('.exe') ? signature.toString('ascii', 0, 2) !== 'MZ' : !signature.equals(Buffer.from([0x50,0x4b,0x03,0x04]))) {
    throw new Error(`Invalid ${platform} package: ${source}`);
  }
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(source)) hash.update(chunk);
  const target = path.join(destination, filename);
  if (path.resolve(source) !== path.resolve(target)) await copyFile(source, target);
  return {platform, filename, url:`/releases/${filename}`, kind, version, bytes:(await stat(target)).size, sha256:hash.digest('hex')};
}

const windows = await prepare('windows', 'StudentSurveyCreator-Windows.exe', [
  path.join(root, 'dist', 'StudentSurveyCreator-Windows.exe'),
  path.join(destination, 'StudentSurveyCreator-Windows.exe'),
], 'WINDOWS_DOWNLOAD_URL', 'standalone');
const android = await prepare('android', 'StudentSurveyCreator-Android.apk', [
  path.join(root, 'mobile', 'build', 'app', 'outputs', 'flutter-apk', 'app-debug.apk'),
  path.join(destination, 'StudentSurveyCreator-Android.apk'),
  path.join(destination, 'app-debug.apk'),
], 'ANDROID_DOWNLOAD_URL', 'development');

if (process.env.REQUIRE_DOWNLOADS === '1' && (!windows.url || !android.url)) {
  throw new Error('Both Windows EXE and Android APK packages are required for this build. Supply the files or their HTTPS download URLs.');
}
await writeFile(path.join(destination, 'downloads.json'), JSON.stringify({version, windows, android}, null, 2) + '\n');
for (const release of [windows, android]) console.log(`${release.platform}: ${release.url || 'package not supplied — download shown as unavailable'}`);

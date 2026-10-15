import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'bytepleat-ui-smoke-'));
const fixtureDir = path.join(tempRoot, 'fixture');
fs.mkdirSync(fixtureDir);
const fixture = path.join(fixtureDir, 'sample.zip');
const createFixture = path.join(fixtureDir, 'startup-create.txt');
const startupAction = process.env.BYTEPLEAT_STARTUP_ACTION || 'open';
if (!['create', 'extract', 'open'].includes(startupAction)) throw new Error(`Unsupported startup action: ${startupAction}`);
const startupPath = startupAction === 'create' ? createFixture : fixture;
const appBinaryPath = process.env.BYTEPLEAT_APP_BINARY || path.join(repo, 'desktop/src-tauri/target/debug/bytepleat-desktop');

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) { c ^= b; for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1)); }
  return (c ^ 0xffffffff) >>> 0;
}
function makeZip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const [name, value] of entries) {
    const n = Buffer.from(name), data = Buffer.from(value), crc = crc32(data);
    const local = Buffer.alloc(30 + n.length);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt32LE(0, 6);
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22); local.writeUInt16LE(n.length, 26); n.copy(local, 30);
    locals.push(local, data);
    const central = Buffer.alloc(46 + n.length);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16); central.writeUInt32LE(data.length, 20); central.writeUInt32LE(data.length, 24); central.writeUInt16LE(n.length, 28); central.writeUInt32LE(offset, 42); n.copy(central, 46);
    centrals.push(central); offset += local.length + data.length;
  }
  const centralBytes = Buffer.concat(centrals), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralBytes.length, 12); end.writeUInt32LE(offset, 16);
  fs.writeFileSync(fixture, Buffer.concat([...locals, centralBytes, end]));
}
makeZip([['keep.txt', 'selected fixture payload\n'], ['skip.txt', 'unselected fixture payload\n']]);
fs.writeFileSync(createFixture, 'created from a real startup argument\n');
fs.mkdirSync(process.env.BYTEPLEAT_SCREENSHOT_DIR || path.join(os.tmpdir(), 'bytepleat-ui-screenshots'), { recursive: true });

export const config = {
  runner: 'local', specs: [process.env.BYTEPLEAT_STARTUP_ARGS_ONLY ? './specs/startup-args.spec.js' : './specs/native-smoke.spec.js'], maxInstances: 1,
  framework: 'mocha', reporters: ['spec'],
  services: [['@wdio/tauri-service', { appBinaryPath, appArgs: [`--${startupAction}`, '--', startupPath], driverProvider: 'embedded', embeddedPort: 4445 }]],
  capabilities: [{ browserName: 'wry' }],
  mochaOpts: { timeout: 120000 },
  baseUrl: 'tauri://localhost',
  outputDir: path.join(tempRoot, 'wdio-logs'),
  onComplete(exitCode) {
    const dest = path.resolve(process.env.BYTEPLEAT_SCREENSHOT_DIR || path.join(os.tmpdir(), 'bytepleat-ui-screenshots'));
    const screenshots = process.env.BYTEPLEAT_STARTUP_ARGS_ONLY
      ? []
      : ['01-native-inspect.png', '02-selective-extract-review.png'];
    const reportName = process.env.BYTEPLEAT_STARTUP_ARGS_ONLY
      ? `bytepleat-startup-args-${startupAction}.json`
      : 'bytepleat-ui-smoke-results.json';
    fs.writeFileSync(path.join(dest, reportName), JSON.stringify({
      appBinaryPath, fixture: path.basename(fixture), startupAction, startupPath: path.basename(startupPath), platform: process.platform,
      driverProvider: 'embedded', screenshots,
      screenshotFilesPresent: screenshots.filter(name => fs.existsSync(path.join(dest, name))),
      fixtureGeneratedInOsTemp: true, wdioExitCode: exitCode
    }, null, 2) + '\n');
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
};

export { fixture, startupAction, startupPath };

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { fixture } from '../wdio.conf.js';

const screenshots = path.resolve(process.env.BYTEPLEAT_SCREENSHOT_DIR || path.join(os.tmpdir(), 'bytepleat-ui-screenshots'));
const crc32Table = Uint32Array.from({ length: 256 }, (_, value) => {
  let crc = value;
  for (let bit = 0; bit < 8; bit++) crc = (crc & 1) ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  return crc >>> 0;
});
function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = (crc >>> 8) ^ crc32Table[(crc ^ byte) & 0xff];
  return (crc ^ 0xffffffff) >>> 0;
}
const invoke = async (command, args) => {
  const result = await browser.executeAsync(({ command, args }, done) => {
    window.__TAURI__.core.invoke(command, args).then(done, error => done({ invokeError: String(error) }));
  }, { command, args });
  if (result?.invokeError) throw new Error(result.invokeError);
  return result;
};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitJob(id) {
  for (let i = 0; i < 240; i++) {
    const jobs = await invoke('jobs');
    const job = jobs.find(item => item.id === id);
    if (job && ['completed', 'failed', 'cancelled'].includes(job.state)) return job;
    await pause(250);
  }
  throw new Error(`Timed out waiting for native job ${id}`);
}

function writeSlowExtractionZip(archivePath) {
  // A highly compressible, deterministic 512 MiB member keeps the fixture
  // small while making mid-decode cancellation observable on fast machines.
  const name = Buffer.from('payload.bin');
  const payload = Buffer.alloc(512 * 1024 * 1024);
  const compressed = zlib.deflateRawSync(payload, { level: 1 });
  const crc = typeof zlib.crc32 === 'function' ? zlib.crc32(payload) : crc32(payload);
  const local = Buffer.alloc(30 + name.length);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(8, 8);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(compressed.length, 18);
  local.writeUInt32LE(payload.length, 22);
  local.writeUInt16LE(name.length, 26);
  name.copy(local, 30);

  const central = Buffer.alloc(46 + name.length);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(8, 10);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(compressed.length, 20);
  central.writeUInt32LE(payload.length, 24);
  central.writeUInt16LE(name.length, 28);
  name.copy(central, 46);

  const centralOffset = local.length + compressed.length;
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(1, 8);
  end.writeUInt16LE(1, 10);
  end.writeUInt32LE(central.length, 12);
  end.writeUInt32LE(centralOffset, 16);
  fs.writeFileSync(archivePath, Buffer.concat([local, compressed, central, end]));
}

describe('Bytepleat native Tauri smoke', () => {
  it('inspects a generated ZIP in the real webview and captures an actual app screenshot', async () => {
    await $('#run-job').click();
    await $('#entry-list [data-entry]').waitForExist({ timeout: 30000 });
    const entryText = await $('#entry-list').getText();
    assert.match(entryText, /keep\.txt/);
    assert.match(entryText, /skip\.txt/);
    await browser.saveScreenshot(path.join(screenshots, '01-native-inspect.png'));
    const entry = await $('#entry-list [data-entry="0"]');
    console.info('Native smoke: selecting keep.txt');
    await entry.scrollIntoView({ block: 'center', inline: 'nearest' });
    await entry.click();
    await browser.waitUntil(() => entry.isSelected(), {
      timeout: 10000, timeoutMsg: 'keep.txt checkbox was not selected after the WebDriver click'
    });
    const extractSelected = await $('#extract-selected');
    await extractSelected.waitForEnabled({
      timeout: 10000, timeoutMsg: 'Extract selected did not enable after the checkbox change'
    });
    // The embedded driver can return from a button click without invoking its
    // handler. Scroll, then activate the real DOM button in the WebView.
    console.info('Native smoke: scrolling to and clicking Extract selected');
    await extractSelected.scrollIntoView({ block: 'center', inline: 'nearest' });
    const reviewState = await browser.execute(() => {
      document.querySelector('#extract-selected').click();
      return {
        hidden: document.querySelector('#selected-review').hidden,
        selectedEntryText: document.querySelector('#review-list').innerText
      };
    });
    assert.equal(reviewState.hidden, false, 'Selected extraction review remained hidden after the DOM click');
    assert.match(reviewState.selectedEntryText, /keep\.txt/);
    console.info('Native smoke: waiting for selected extraction review');
    const review = await $('#selected-review');
    await review.waitForDisplayed({
      timeout: 10000, timeoutMsg: 'Selected extraction review did not appear after clicking Extract selected'
    });
    await review.scrollIntoView({ block: 'center', inline: 'nearest' });
    assert.match(await $('#review-list').getText(), /keep\.txt/);
    await browser.saveScreenshot(path.join(screenshots, '02-selective-extract-review.png'));
  });

  it('runs native create and selected extraction, preserving existing output', async () => {
    const source = path.join(path.dirname(fixture), 'created-source.txt');
    const skipped = path.join(path.dirname(fixture), 'skipped-source.txt');
    const archive = path.join(path.dirname(fixture), 'created-by-bytepleat.zip');
    const output = path.join(path.dirname(fixture), 'extract-destination');
    fs.writeFileSync(source, 'created by the native UI smoke\n');
    fs.writeFileSync(skipped, 'not selected for extraction\n');
    fs.mkdirSync(output);
    const createId = await invoke('start_job', { request: { action: 'create', inputs: [source, skipped], destination: archive, format: 'zip', selected_entries: [], max_output_bytes: 1048576 } });
    const created = await waitJob(createId);
    assert.equal(created.state, 'completed');
    const listing = await invoke('inspect_archive', { path: archive });
    assert.ok(listing.entries.map(entry => entry.name).includes('created-source.txt'));

    const selected = ['created-source.txt'];
    const extractId = await invoke('start_job', { request: { action: 'extract', inputs: [archive], destination: path.join(output, 'selected'), format: null, selected_entries: selected, max_output_bytes: 1048576 } });
    const extracted = await waitJob(extractId);
    assert.equal(extracted.state, 'completed');
    assert.equal(fs.readFileSync(path.join(output, 'selected', 'created-source.txt'), 'utf8'), 'created by the native UI smoke\n');
    assert.equal(fs.existsSync(path.join(output, 'selected', 'skipped-source.txt')), false);

    fs.writeFileSync(path.join(output, 'occupied'), 'preserve this file');
    const collisionId = await invoke('start_job', { request: { action: 'extract', inputs: [archive], destination: path.join(output, 'occupied'), format: null, selected_entries: [], max_output_bytes: 1048576 } });
    const collision = await waitJob(collisionId);
    assert.equal(collision.state, 'failed');
    assert.equal(fs.readFileSync(path.join(output, 'occupied'), 'utf8'), 'preserve this file');
  });

  it('cancels a real extraction after partial staging and preserves the archive', async function () {
    this.timeout(120000);
    const archive = path.join(path.dirname(fixture), 'cancel-mid-extraction.zip');
    const destinationParent = path.join(path.dirname(fixture), 'cancel-output-parent');
    const destination = path.join(destinationParent, 'cancelled-output');
    fs.mkdirSync(destinationParent, { recursive: true });
    writeSlowExtractionZip(archive);
    const originalDigest = crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex');
    const before = new Set(fs.readdirSync(destinationParent));

    const id = await invoke('start_job', { request: {
      action: 'extract', inputs: [archive], destination, format: null,
      selected_entries: [], max_output_bytes: 1073741824
    } });

    let stagePath;
    await browser.waitUntil(() => {
      for (const name of fs.readdirSync(destinationParent)) {
        if (before.has(name)) continue;
        const candidate = path.join(destinationParent, name);
        try {
          for (const entry of fs.readdirSync(candidate, { withFileTypes: true })) {
            if (!entry.isDirectory() || !entry.name.startsWith('.bytepleat-extract-')) continue;
            const partial = path.join(candidate, entry.name, 'payload.bin');
            if (fs.statSync(partial).size > 0) {
              stagePath = candidate;
              return true;
            }
          }
        } catch { /* The worker has not created its staged payload yet. */ }
      }
      return false;
    }, {
      timeout: 30000,
      interval: 25,
      timeoutMsg: 'Extraction did not produce a partial private-stage payload within 30 seconds'
    });

    const cancelControl = await $(`[data-job="${id}"][data-action="cancel"]`);
    await cancelControl.waitForDisplayed({
      timeout: 10000,
      timeoutMsg: 'The active extraction did not show its Cancel control'
    });
    await cancelControl.waitForEnabled({
      timeout: 10000,
      timeoutMsg: 'The active extraction Cancel control was disabled'
    });
    const clicked = await browser.execute(({ id }) => {
      const button = [...document.querySelectorAll('[data-action="cancel"]')]
        .find(item => item.dataset.job === id);
      if (!button || button.disabled || button.hidden) return false;
      button.click();
      return true;
    }, { id });
    assert.equal(clicked, true, 'The visible Cancel control should receive the DOM click');
    await browser.waitUntil(async () => {
      const job = (await invoke('jobs')).find(item => item.id === id);
      return job && ['cancelling', 'cancelled'].includes(job.state);
    }, {
      timeout: 10000,
      interval: 25,
      timeoutMsg: 'Clicking the visible Cancel control did not request native cancellation'
    });
    const cancelled = await waitJob(id);
    assert.equal(cancelled.state, 'cancelled');
    await browser.waitUntil(() => !fs.existsSync(stagePath), {
      timeout: 10000,
      interval: 25,
      timeoutMsg: 'The private extraction stage remained after the cancelled job finished'
    });
    assert.equal(fs.existsSync(destination), false, 'Cancelled extraction must not publish its output');
    assert.equal(
      crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex'),
      originalDigest,
      'Cancellation must preserve the input archive byte-for-byte'
    );
  });
});

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fixture } from '../wdio.conf.js';

const screenshots = path.resolve(process.env.BYTEPLEAT_SCREENSHOT_DIR || path.join(os.tmpdir(), 'bytepleat-ui-screenshots'));
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

describe('Bytepleat native Tauri smoke', () => {
  it('inspects a generated ZIP in the real webview and captures an actual app screenshot', async () => {
    await $('#run-job').click();
    await $('#entry-list [data-entry]').waitForExist({ timeout: 30000 });
    await expect($('#entry-list')).toHaveTextContaining('keep.txt');
    await expect($('#entry-list')).toHaveTextContaining('skip.txt');
    await browser.saveScreenshot(path.join(screenshots, '01-native-inspect.png'));
    await $('#entry-list [data-entry="0"]').click();
    await $('#extract-selected').click();
    await expect($('#selected-review')).toBeDisplayed();
    await expect($('#review-list')).toHaveTextContaining('keep.txt');
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
    await expect(created.state).toBe('completed');
    const listing = await invoke('inspect_archive', { path: archive });
    await expect(listing.entries.map(entry => entry.name)).toContain('created-source.txt');

    const selected = ['created-source.txt'];
    const extractId = await invoke('start_job', { request: { action: 'extract', inputs: [archive], destination: path.join(output, 'selected'), format: null, selected_entries: selected, max_output_bytes: 1048576 } });
    const extracted = await waitJob(extractId);
    await expect(extracted.state).toBe('completed');
    await expect(fs.readFileSync(path.join(output, 'selected', 'created-source.txt'), 'utf8')).toBe('created by the native UI smoke\n');
    await expect(fs.existsSync(path.join(output, 'selected', 'skipped-source.txt'))).toBe(false);

    fs.writeFileSync(path.join(output, 'occupied'), 'preserve this file');
    const collisionId = await invoke('start_job', { request: { action: 'extract', inputs: [archive], destination: path.join(output, 'occupied'), format: null, selected_entries: [], max_output_bytes: 1048576 } });
    const collision = await waitJob(collisionId);
    await expect(collision.state).toBe('failed');
    await expect(fs.readFileSync(path.join(output, 'occupied'), 'utf8')).toBe('preserve this file');
  });
});

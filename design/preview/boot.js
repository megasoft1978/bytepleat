// Preview harness for desktop/ui (not shipped). Mocks window.__TAURI__ with canned data and drives
// the real UI into one state: /design/preview/?state=<name>&theme=light|dark|system[&open=history]
const q = new URLSearchParams(location.search);
const state = q.get('state') || 'empty';
const theme = q.get('theme') || 'light';
try { if (theme === 'system') localStorage.removeItem('bytepleat-theme'); else localStorage.setItem('bytepleat-theme', theme); } catch { /* ignore */ }

const wait = ms => new Promise(r => setTimeout(r, ms));
const $ = s => document.querySelector(s);
const HOME = '/Users/alex';
const FILES = [`${HOME}/project/report.pdf`, `${HOME}/project/photos`, `${HOME}/project/notes.md`];
const ARCHIVE = `${HOME}/Downloads/photos.7z`;

function bigListing(total, shown) {
  const entries = [];
  const dirs = ['photos/2024/', 'photos/2023/', 'photos/2022/raw/'];
  for (let i = 0; i < shown; i++) {
    const dir = dirs[Math.floor(i / 1700) % dirs.length];
    if (i % 400 === 0) entries.push({ name: dir, size: 0, is_dir: true });
    else entries.push({ name: `${dir}IMG_${String(i).padStart(4, '0')}.jpg`, size: 2_400_000 + (i * 7919) % 1_400_000, is_dir: false });
  }
  return { format: '7z', entries, total_entries: total, truncated: total > shown, total_bytes: 1_100_000_000, integrity_validated: false };
}
const smallListing = { format: '7z', total_entries: 6, truncated: false, total_bytes: 9_812_400, integrity_validated: false, entries: [
  { name: 'photos/', size: 0, is_dir: true },
  { name: 'photos/IMG_0001.jpg', size: 3_100_000, is_dir: false },
  { name: 'photos/IMG_0002.jpg', size: 2_900_000, is_dir: false },
  { name: 'photos/IMG_0003.jpg', size: 3_400_000, is_dir: false },
  { name: 'notes.md', size: 4_100, is_dir: false },
  { name: 'readme.txt', size: 1_200, is_dir: false }
] };

const OLD_JOBS = [
  { id: 'h1', action: 'extract', phase: 'Complete', state: 'completed', processed_bytes: 1, total_bytes: 1, message: 'Complete', output: `${HOME}/Downloads/invoices-extracted`, error: null },
  { id: 'h2', action: 'create', phase: 'Cancelled', state: 'cancelled', processed_bytes: 0, total_bytes: null, message: 'Cancelled', output: null, error: null },
  { id: 'h3', action: 'create', phase: 'Complete', state: 'completed', processed_bytes: 1, total_bytes: 1, message: 'Complete', output: `${HOME}/Desktop/backup-2024.tar.zst`, error: null },
  { id: 'h4', action: 'inspect', phase: 'Complete', state: 'completed', processed_bytes: 1, total_bytes: 1, message: 'Complete', output: null, error: null }
];

// Per-state setup. final: what the started job turns into after `after` ms.
const S = {
  empty: {},
  'empty-extract': { drive: async () => $('#tab-extract').click() },
  'empty-inspect': { drive: async () => $('#tab-open').click() },
  dragover: { drive: async () => { dragCb?.({ payload: { type: 'over' } }); } },
  files: { initial: { action: 'create', paths: FILES }, drive: async () => { $('#choose-destination').click(); } },
  format: { initial: { action: 'create', paths: FILES }, drive: async () => { $('#choose-destination').click(); await wait(50); const r = document.querySelector('input[value="tar.zst"]'); r.click(); r.focus(); } },
  running: { initial: { action: 'create', paths: FILES }, final: null, run: true },
  'running-unknown': { initial: { action: 'create', paths: FILES }, final: null, run: true, unknown: true },
  fold: { initial: { action: 'create', paths: FILES }, final: null, run: true, pauseAt: 420 },
  success: { initial: { action: 'create', paths: FILES }, run: true, final: { state: 'completed', output: `${HOME}/Desktop/project.zip` } },
  'success-extract': { initial: { action: 'extract', paths: [ARCHIVE] }, run: true, final: { state: 'completed', output: `${HOME}/Downloads/photos-extracted` } },
  error: { initial: { action: 'create', paths: FILES }, run: true, final: { state: 'failed', error: 'Permission denied (os error 13) while creating /Volumes/Shared/project.zip.bytepleat-tmp' }, openDetails: true },
  cancelled: { initial: { action: 'create', paths: FILES }, run: true, final: { state: 'cancelled' } },
  inspect: { initial: { action: 'open', paths: [ARCHIVE] }, listing: bigListing(12408, 5000), drive: async () => { $('#run-job').click(); await wait(300); [...document.querySelectorAll('#entry-list [data-entry]')].slice(1, 4).forEach(b => b.click()); } },
  'inspect-small': { initial: { action: 'open', paths: [ARCHIVE] }, listing: smallListing, drive: async () => { $('#run-job').click(); } },
  review: { initial: { action: 'open', paths: [ARCHIVE] }, listing: smallListing, drive: async () => { $('#run-job').click(); await wait(300); [...document.querySelectorAll('#entry-list [data-entry]')].slice(1, 4).forEach(b => b.click()); $('#extract-selected').click(); await wait(50); $('#choose-destination').click(); } },
  'empty-selection': { initial: { action: 'open', paths: [ARCHIVE] }, listing: smallListing, drive: async () => { $('#run-job').click(); await wait(300); $('#extract-selected').click(); } },
  multiple: { initial: { action: 'open', paths: [`${HOME}/Downloads/photos.zip`, `${HOME}/Downloads/backup.7z`, `${HOME}/Downloads/logs.tar.zst`] } },
  history: { initial: { action: 'create', paths: FILES }, jobs: OLD_JOBS, drive: async () => { $('#choose-destination').click(); if (!matchMedia('(min-width: 1200px)').matches) $('#history-toggle').click(); } }
};
const scenario = S[state] || S.empty;

let started = null;
let dragCb = null;
const listeners = {};
const responses = {
  // Resolve after the first jobs poll, as a later 'selection' event would, so earlier jobs do not cover the chosen files.
  initial_selection: async () => { await wait(150); return scenario.initial || { action: 'create', paths: [], error: null }; },
  choose_inputs: () => FILES,
  choose_input_directory: () => `${HOME}/project/photos`,
  choose_output: ({ format }) => `${HOME}/Desktop/project.${format}`,
  choose_directory: () => `${HOME}/Downloads`,
  inspect_archive: async () => { await wait(120); return scenario.listing || smallListing; },
  start_job: ({ request }) => { started = { at: Date.now(), request, id: 'j9' }; return 'j9'; },
  cancel_job: () => true,
  open_destination: () => true,
  jobs: () => {
    const old = scenario.jobs || (scenario.run ? OLD_JOBS : []);
    if (!started) return old;
    const running = Date.now() - started.at < 900 || !scenario.final;
    const base = { id: started.id, action: started.request.action, phase: 'writing', processed_bytes: 412_000_000, total_bytes: scenario.unknown ? null : 1_100_000_000, message: 'Writing', output: null, error: null };
    const job = running ? { ...base, state: 'running' } : { ...base, phase: 'Complete', message: scenario.final.error || 'Complete', ...scenario.final };
    return [job, ...old];
  }
};
window.__TAURI__ = {
  core: { invoke: async (cmd, args = {}) => { const fn = responses[cmd]; if (!fn) throw new Error(`mock: no ${cmd}`); return fn(args); } },
  event: { listen: async (name, cb) => { listeners[name] = cb; return () => {}; } },
  webviewWindow: { getCurrentWebviewWindow: () => ({ onDragDropEvent: cb => { dragCb = cb; } }) }
};
// Clipboard is unavailable on http:// in some browsers; keep Copy buttons harmless.
if (!navigator.clipboard) navigator.clipboard = { writeText: async () => {} };

const html = await (await fetch('/desktop/ui/index.html')).text();
const doc = new DOMParser().parseFromString(html, 'text/html');
const loads = [];
doc.head.querySelectorAll('link').forEach(l => { const n = l.cloneNode(); if (n.rel === 'stylesheet') loads.push(new Promise(r => { n.onload = r; n.onerror = r; })); document.head.append(n); });
doc.body.querySelectorAll('script').forEach(s => s.remove());
document.body.innerHTML = doc.body.innerHTML;
await Promise.all(loads);
// Headless Chrome's virtual time does not advance CSS transitions reliably, so screenshots freeze mid-transition.
// Disable CSS motion here (the fold/unfold use WAAPI and are paused or finished explicitly below).
if (!q.has('motion')) { const st = document.createElement('style'); st.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}'; document.head.append(st); }
await import('/desktop/ui/app.js');
await document.fonts.ready;
await wait(300);
if (scenario.run) {
  $('#choose-destination').click();
  await wait(60);
  $('#run-job').click();
  if (scenario.pauseAt) { await wait(20); const t = Number(q.get('t') || scenario.pauseAt); document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; }); }
}
await scenario.drive?.();
if (scenario.openDetails) { await wait(1300); document.querySelector('#job-now details')?.setAttribute('open', ''); }
if (q.get('focus') === 'tabs') $('#tab-extract').focus();
if (!scenario.pauseAt) { await wait(1500); document.getAnimations().forEach(a => { try { a.finish(); } catch { a.cancel(); } }); }
document.documentElement.dataset.previewReady = state;

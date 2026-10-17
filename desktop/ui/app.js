const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const native = Boolean(window.__TAURI__?.core?.invoke);
const invoke = native ? window.__TAURI__.core.invoke : async () => { throw new Error('Native desktop backend required'); };
const listen = native ? window.__TAURI__.event.listen : async () => () => {};
let mode = 'create';
let selected = [];
let destination = null;
let currentJobs = [];
let lastJobsFingerprint = null;
let pollHandle = null;
let selectedEntries = [];
let selectiveExtraction = false;
let inspectionRequest = 0;
let inspectionInFlight = false;
let listingCache = null;
// The newest finished job is shown on the sheet until the user moves on (new selection, mode change, or an outcome action).
let dismissedJob = null;
const lastJobStates = new Map();
const inspectNames = new Map();
const jobRequests = new Map();
const ARCHIVE_EXT = /\.(zip|7z|tar\.(zst|gz|lz4))$/i;
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const PLATFORM = /Mac/i.test(navigator.platform || navigator.userAgent) ? 'mac' : /Win/i.test(navigator.platform || navigator.userAgent) ? 'win' : 'other';
const SHOW_LABEL = { mac: 'Show in Finder', win: 'Show in File Explorer', other: 'Show in folder' }[PLATFORM];
const BUSY_REASON = 'A job is running. Cancel it to change things.';

const NO_DESTINATION = 'Not chosen yet';
function showDestination(value){const el=$('#destination-path');el.textContent=value||NO_DESTINATION;el.title=value||'';el.classList.toggle('is-empty',!value);}
const THEME_KEY = 'bytepleat-theme';
// The same words are used for the tab, heading, button, job title and completion message.
const MODES = {
  create: { title: 'Create an archive', hint: 'Pack files or folders into one new archive. Your originals stay put.', inputTitle: 'Choose what to archive', inputHint: 'Archive output is capped at 1 GiB.', dropTitle: 'Drop files or folders here', dropSub: 'Nothing leaves this device. Nothing is overwritten.', destTitle: 'Save to', destHint: 'Choose where the finished archive will go.', destStep: '', run: 'Create archive', fine: 'Source files stay in place. An existing file is never replaced.', aside: 'Files are copied into the archive. Originals are never moved or removed.' },
  extract: { title: 'Extract an archive', hint: 'Unpack one archive into a new folder. Existing files and folders are never overwritten.', inputTitle: 'Choose an archive to extract', inputHint: 'Extracted size is capped at 1 GiB, and archives at 100,000 entries.', dropTitle: 'Drop an archive here', dropSub: 'ZIP, 7z, tar.zst, tar.gz and tar.lz4.', destTitle: 'Into', destHint: 'Bytepleat adds a new folder here for the extracted files.', destStep: '', run: 'Extract archive', fine: 'The archive stays in place. An existing folder is never overwritten.', aside: 'Files are unpacked in a temporary folder and moved into place only after everything succeeds.' },
  open: { title: 'Inspect an archive', hint: 'See what is inside an archive without extracting it. Listing does not check file contents.', inputTitle: 'Choose an archive to inspect', inputHint: 'The list shows up to 5,000 entries; archives can hold up to 100,000.', dropTitle: 'Drop an archive to see what is inside', dropSub: 'Inspecting only reads the archive. Nothing is extracted.', destTitle: '', destHint: '', destStep: '', run: 'Inspect archive', fine: 'Nothing is extracted to your folders, and the archive is not changed.', aside: 'Listing does not check file contents. A compressed tar has to be fully unpacked to a temporary folder to list it; that folder is deleted afterwards.' }
};
const JOB_LABEL = { create: 'Create archive', extract: 'Extract archive', inspect: 'Inspect archive' };
const STATE_LABEL = { queued: 'Queued', running: 'Running', cancelling: 'Stopping…', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
const DONE_VERB = { create: 'Created', extract: 'Extracted', inspect: 'Inspected' };
const isActive = job => ['queued', 'running', 'cancelling'].includes(job.state);

const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const basename = path => path.replace(/[\\/]$/, '').split(/[\\/]/).pop() || path;
const isTar = path => /\.tar\.(zst|gz|lz4)$/i.test(path);
const extractedName = path => `${basename(path).replace(/\.(tar\.(?:zst|gz|lz4)|zip|7z)$/i, '')}-extracted`;
const pathSeparator = path => (/^[A-Za-z]:[\\/]|^\\\\/.test(path) || (path.includes('\\') && !path.includes('/'))) ? '\\' : '/';
const extractTarget = () => `${destination.replace(/[\\/]$/, '')}/${extractedName(selected[0])}`;
const extractTargetDisplay = () => `${destination.replace(/[\\/]+$/, '')}${pathSeparator(destination)}${extractedName(selected[0])}`;
const num = n => Number(n).toLocaleString();
const REVIEW_STATUS = 'Review the chosen entries, then choose a destination folder.';
const multiArchiveMessage = count => `${count} archives were selected. Choose exactly one archive; nothing was processed.`;

const ICON = {
  check: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  minus: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M4 8h8" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>',
  alert: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.75v4M8 10.9v.1" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>',
  info: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 7.25v4M8 4.9v.1" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>',
  dot: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="3" fill="currentColor"/></svg>',
  remove: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  file: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path d="M4 1.75h5.25L12.25 4.75v9.5H4z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M9 1.75v3.25h3.25" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/></svg>',
  mark: '<svg viewBox="0 0 32 32" width="28" height="28" fill="currentColor" aria-hidden="true" focusable="false"><polygon points="3 6 9.5 9.5 9.5 22.5 3 26" fill-opacity=".95"/><polygon points="9.5 9.5 16 6 16 26 9.5 22.5" fill-opacity=".45"/><polygon points="16 6 22.5 9.5 22.5 22.5 16 26" fill-opacity=".95"/><polygon points="22.5 9.5 29 6 29 26 22.5 22.5" fill-opacity=".45"/></svg>'
};

function status(message, error=false, extra={}) {
  const el = $('#status-message');
  el.textContent = message;
  el.classList.toggle('is-error', Boolean(error && message));
  el.setAttribute('aria-live', error ? 'assertive' : 'polite');
  if (extra.detail && extra.detail !== message) {
    const d = document.createElement('details'); d.className = 'status-detail';
    const sm = document.createElement('summary'); sm.textContent = 'Technical details';
    const pre = document.createElement('pre'); pre.textContent = extra.detail;
    d.append(sm, pre); el.append(d);
  }
  if (extra.retry) {
    const b = document.createElement('button'); b.type = 'button'; b.id = 'status-retry'; b.className = 'button button-secondary button-small status-retry'; b.textContent = 'Try again';
    b.addEventListener('click', extra.retry); el.append(b);
  }
}
// Turn a raw backend error into one plain sentence; the raw text stays available as secondary detail.
function friendlyError(raw) {
  const text = String(raw?.message ?? raw ?? '').replace(/^Error:\s*/, '');
  const rules = [
    [/already exists|exists|occupied|overwrit/i, 'That name is already taken. Bytepleat never overwrites files, so choose a different name or folder.'],
    [/limit|exceed|too large|too many|1 GiB|100,?000/i, 'This is larger than Bytepleat can handle safely. Nothing was created.'],
    [/password|encrypt|rar|zip64|unsupported|not supported/i, 'This archive uses a feature Bytepleat does not support yet.'],
    [/permission|denied|read-only|access/i, 'Bytepleat was not allowed to read or write there. Choose another location.'],
    [/not found|no such file|missing/i, 'A file or folder could not be found. It may have been moved or deleted.'],
    [/utf-?8/i, 'One of the chosen paths has characters Bytepleat cannot handle, so nothing was processed.'],
    [/corrupt|invalid|malformed|truncated|checksum|crc/i, 'The archive looks damaged or is not a valid archive.'],
    [/cancel/i, 'The job was cancelled.']
  ];
  const hit = rules.find(([re]) => re.test(text));
  return { summary: hit ? hit[1] : 'Something went wrong. Your originals were not changed.', detail: text };
}
function statusError(error, retry) {
  const f = friendlyError(error);
  status(f.summary, true, { detail: f.detail, retry });
}
function selectionAlert(message) {
  const el = $('#selection-alert');
  el.innerHTML = message ? `${ICON.alert}<span>${esc(message)}</span>` : '';
  el.hidden = !message;
}
function showMultiNotice(count) {
  const el = $('#multi-notice');
  if (!el) return;
  if (!count) { el.hidden = true; el.replaceChildren(); return; }
  el.hidden = false;
  el.innerHTML = `${ICON.info}<div><p class="notice-title">${esc(multiArchiveMessage(count))}</p><p class="caption">Bytepleat opens one archive at a time. Remove the extra ones, or open a different one.</p></div>`;
  $('#announce').textContent = multiArchiveMessage(count);
}
function resetInspection() {
  inspectionRequest++;
  if(inspectionInFlight)status('');
  inspectionInFlight=false;
  selectedEntries=[]; selectiveExtraction=false;
  $('#archive-inspection').hidden=true;
  $('#inspection-summary').textContent='';
  $('#entry-list').replaceChildren();
  $('#entry-cap').hidden=true; $('#entry-cap').replaceChildren();
  $('#drop-zone').classList.remove('show-listing');
  selectionAlert('');
  renderReview();
}
function updateDestinationNote(override) {
  const note = $('#destination-note');
  if (override) note.textContent = override;
  else if (mode === 'extract' && destination && selected.length === 1 && selectiveExtraction && selectedEntries.length) note.textContent = `Extracts ${num(selectedEntries.length)} ${entryNoun(selectedEntries)} into a new folder: ${extractTargetDisplay()}. If that folder already exists, the job stops instead of replacing anything.`;
  else if (mode === 'extract' && destination && selected.length === 1) note.textContent = `Extracts into a new folder: ${extractTargetDisplay()}. If that folder already exists, the job stops instead of replacing anything.`;
  else if (mode === 'extract' && selected.length === 1) note.textContent = `Creates a new folder named “${extractedName(selected[0])}” inside the folder you choose.`;
  else if (mode === 'extract') note.textContent = 'Creates a new folder named after the archive plus “-extracted” inside the folder you choose.';
  else if (mode === 'create') note.textContent = 'If a file already exists there, the job stops instead of replacing it.';
  else note.textContent = '';
}
function dismissOutcome() {
  const job = currentJobs[0];
  if (job && !isActive(job)) dismissedJob = job.id;
  renderJobNow(job);
}
function showSelection(paths, append=false) {
  const singleArchive = mode==='extract'||mode==='open';
  const incoming = paths;
  selected = singleArchive ? [...incoming] : [...(append?selected:[]), ...incoming];
  resetInspection();
  dismissOutcome();
  status('');
  const host=$('#selection');
  if (!selected.length) { host.innerHTML='<div class="selection-empty">Nothing selected yet.</div>'; }
  else host.innerHTML=(singleArchive?'<div id="multi-notice" class="sheet-notice" hidden></div>':'')+selected.map((path,i)=>`<div class="selected-item"><span class="file-icon">${ICON.file}</span><span class="file-details"><strong>${esc(basename(path))}</strong><small title="${esc(path)}">${esc(path)}</small></span><button class="remove-item" type="button" data-remove="${i}" aria-label="Remove ${esc(basename(path))} from the selection" title="Remove from the selection">${ICON.remove}</button></div>`).join('');
  host.querySelectorAll('[data-remove]').forEach(btn=>btn.addEventListener('click',()=>{const i=Number(btn.dataset.remove);selected.splice(i,1);showSelection(selected);updateRunState();const rows=$$('#selection [data-remove]');(rows[Math.min(i,rows.length-1)]||$('#browse-inputs')).focus();}));
  if(singleArchive&&selected.length>1)showMultiNotice(selected.length);
  $('#drop-zone').classList.toggle('has-selection',selected.length>0);
  updateRunState();
  updateDestinationNote();
}
function runHint(busy, unsupportedMulti, emptyExtract) {
  if (!native) return 'Open the Bytepleat desktop app to run this.';
  if (busy) return BUSY_REASON;
  if (inspectionInFlight) return 'Reading the archive listing…';
  if (!selected.length) return mode==='create' ? 'Choose what to archive first.' : 'Choose an archive first.';
  if (unsupportedMulti) return 'Choose exactly one archive.';
  if (emptyExtract) return 'Select at least one entry to extract.';
  if (mode!=='open' && !destination) return mode==='create' ? 'Choose where to save the archive.' : 'Choose a destination folder.';
  if (mode==='create') return 'Ready. Your originals stay in place.';
  if (mode==='extract') return 'Ready. Files go into a new folder.';
  return '';
}
let dirNames = new Set();
function entryNoun(names) {
  const one = names.length === 1;
  return names.some(name => dirNames.has(name)) ? (one ? 'entry' : 'entries') : (one ? 'file' : 'files');
}
function updateEntryHint() {
  $('#entry-hint').textContent = $('#archive-inspection').hidden ? '' : selectedEntries.length
    ? `Choose Extract to pick a destination folder. Bytepleat reads the whole archive first, then keeps only these.`
    : 'Tick the entries you want, then choose Extract. To extract everything, use Extract everything.';
}
let counterTimer = null;
function updateEntryCounter() {
  const boxes = $$('#entry-list [data-entry]');
  const all = $('#select-all');
  const total = boxes.length;
  const chosen = selectedEntries.length;
  $('#select-all-label').textContent = `Select all listed (${num(total)})`;
  $('#entry-counter').textContent = `${num(chosen)} of ${num(total)} chosen`;
  all.checked = total > 0 && chosen === total;
  all.indeterminate = chosen > 0 && chosen < total;
  clearTimeout(counterTimer);
  if (!$('#archive-inspection').hidden) counterTimer = setTimeout(() => { $('#announce').textContent = `${num(chosen)} of ${num(total)} chosen`; }, 500);
}
function updateSelectionNote() {
  const note = $('#selection-note');
  const text = mode==='open' && selected.length===1 && isTar(selected[0]) && $('#archive-inspection').hidden ? 'Compressed tar: listing unpacks the whole archive to a temporary folder, which is deleted afterwards. Extracting selected entries later reads it again.' : '';
  note.textContent = text; note.hidden = !text;
}
function renderReview() {
  const show = mode==='extract' && selectiveExtraction && selectedEntries.length>0;
  $('#selected-review').hidden = !show;
  $('#drop-zone').classList.toggle('show-review', show);
  if (!show) { $('#review-list').replaceChildren(); return; }
  $('#review-title').textContent = `Choose what to extract from ${basename(selected[0])}`;
  $('#review-summary').textContent = `${num(selectedEntries.length)} ${selectedEntries.length===1?'entry':'entries'} chosen`;
  $('#review-list').innerHTML = selectedEntries.map(name=>`<li><span class="review-check" aria-hidden="true">${ICON.check}</span><span class="entry-name">${entryNameHtml(name)}</span></li>`).join('');
}
function startSelectiveExtract(archive, entries) {
  // setMode clears the listing; keep the cache so Change selection can restore it without re-reading the archive.
  const cache = listingCache;
  setMode('extract'); showSelection([archive]);
  listingCache = cache; selectedEntries = entries; selectiveExtraction = true;
  renderReview(); updateRunState(); updateDestinationNote();
  status('');
  $('#announce').textContent=REVIEW_STATUS;
  $('#review-title').focus();
}
function updateRunState() {
  const hasInput=selected.length>0;
  const listed=mode==='open'&&!$('#archive-inspection').hidden;
  $('#format-section').hidden=mode!=='create';
  $('#destination-section').hidden=mode==='open';
  $('#run-fineprint').hidden=!hasInput||listed||mode!=='open';
  $('#band-note').hidden=mode!=='open';
  const busy=currentJobs.some(isActive);
  const unsupportedMulti=(mode==='open'||mode==='extract')&&selected.length>1;
  const emptyExtract=mode==='extract'&&selectiveExtraction&&selectedEntries.length===0;
  $('#run-job').disabled=!native || busy || inspectionInFlight || selected.length===0 || unsupportedMulti || emptyExtract || (mode!=='open'&&!destination);
  $('#run-job').title=unsupportedMulti?'Select one archive at a time':emptyExtract?'Select at least one entry to extract':inspectionInFlight?'Reading archive listing…':busy?'One archive job can run at a time':'';
  $('#run-hint').textContent=runHint(busy,unsupportedMulti,emptyExtract);
  $('#selection-count').textContent=selected.length?(mode==='create'?`${num(selected.length)} ${selected.length===1?'item':'items'}`:`${num(selected.length)} ${selected.length===1?'archive':'archives'}`):'';
  // Extract stays enabled with nothing ticked so pressing it can explain why nothing started.
  $('#extract-selected').disabled=!native||busy;
  $('#extract-selected').hidden=!listed;
  $('#extract-selected').textContent=selectedEntries.length?`Extract ${num(selectedEntries.length)} ${entryNoun(selectedEntries)}…`:'Extract selected…';
  $('#extract-all').hidden=!listed;
  const runText=listed?'Inspect again':mode==='extract'&&selectiveExtraction&&selectedEntries.length?`Extract ${num(selectedEntries.length)} ${entryNoun(selectedEntries)}`:MODES[mode].run;
  $('#run-label').textContent=runText;
  $('#run-job').classList.toggle('is-secondary',listed);
  $('#extract-selected').classList.toggle('button-primary',listed);
  $('#extract-selected').classList.toggle('button-secondary',!listed);
  $$('.mode-tab').forEach(tab=>{if(busy){tab.setAttribute('aria-disabled','true');tab.title=BUSY_REASON;}else{tab.removeAttribute('aria-disabled');tab.title='';}});
  $$('#browse-inputs,#browse-folder,#browse-open,#add-files,#add-folder,#open-different,#choose-destination').forEach(b=>{if(busy)b.setAttribute('aria-disabled','true');else b.removeAttribute('aria-disabled');});
  if(selectedEntries.length)selectionAlert('');
  updateEntryHint(); updateEntryCounter(); updateSelectionNote();
}
function setMode(next) {
  mode=next; destination=null; showDestination(null);
  const text=MODES[mode];
  $$('.mode-tab').forEach(btn=>{const active=btn.dataset.mode===mode;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));btn.tabIndex=active?0:-1;});
  $('#workspace-panel').setAttribute('aria-labelledby',`tab-${mode}`);
  document.body.dataset.mode=mode;
  $('#view-label').textContent=text.title;
  $('#view-hint').textContent=text.hint;
  $('#input-title').textContent=text.inputTitle;
  $('#input-hint').textContent=text.inputHint;
  $('#drop-title').textContent=text.dropTitle;
  $('#drop-sub').textContent=text.dropSub;
  $('#browse-inputs').textContent=mode==='create'?'Choose files…':'Open archive…';
  $('#browse-folder').hidden=mode!=='create'; $('#browse-open').hidden=mode!=='create';
  $('#add-files').hidden=mode!=='create'; $('#add-folder').hidden=mode!=='create'; $('#clear-selection').hidden=mode!=='create'; $('#open-different').hidden=mode==='create';
    resetInspection();
  $('#destination-title').textContent=text.destTitle;
  $('#destination-hint').textContent=text.destHint;
  $('#destination-step').textContent=text.destStep;
  $('#run-label').textContent=text.run;
  $('#run-fineprint').textContent=text.fine;
  $('#aside-note').textContent=text.aside;
  showSelection([]); status('');
  const panel=$('#workspace-panel');panel.classList.remove('mode-enter');void panel.offsetWidth;panel.classList.add('mode-enter');
}
const isBusy = () => currentJobs.some(isActive);
const blocked = el => el?.getAttribute('aria-disabled') === 'true';
$$('.mode-tab').forEach(btn=>btn.addEventListener('click',()=>{if(blocked(btn)){$('#announce').textContent=BUSY_REASON;return;}setMode(btn.dataset.mode);}));
// Arrow keys move focus between tabs; Enter or Space selects, so browsing tabs never clears a selection.
$('.mode-tabs').addEventListener('keydown',e=>{const tabs=$$('.mode-tab');const i=tabs.indexOf(document.activeElement);if(i<0)return;const target={ArrowRight:(i+1)%tabs.length,ArrowLeft:(i+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1}[e.key];if(target===undefined)return;e.preventDefault();tabs[target].focus();});
$$('input[name="format"]').forEach(input=>input.addEventListener('change',()=>{$$('.format-option').forEach(el=>el.classList.toggle('selected',el.contains(input)&&input.checked));const desc=$('#format-desc');desc.textContent=input.dataset.desc||'';desc.classList.remove('is-fresh');void desc.offsetWidth;desc.classList.add('is-fresh');const hadDestination=Boolean(destination);destination=null;showDestination(null);updateDestinationNote(hadDestination?'The format changed, so choose the save location again.':'');updateRunState();}));
$('#browse-inputs').addEventListener('click',async e=>{if(blocked(e.currentTarget))return;if(!native){status('Open the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');showSelection(paths,true);}catch(e){statusError(e);}});
$('#browse-folder').addEventListener('click',async e=>{if(blocked(e.currentTarget))return;if(!native){status('Choosing a folder needs the Bytepleat desktop app.',true);return;}try{const path=await invoke('choose_input_directory');if(path)showSelection([path],true);}catch(e){statusError(e);}});
$('#add-files').addEventListener('click',()=>$('#browse-inputs').click());
$('#add-folder').addEventListener('click',()=>$('#browse-folder').click());
$('#open-different').addEventListener('click',()=>$('#browse-inputs').click());
$('#clear-selection').addEventListener('click',()=>{if(isBusy())return;showSelection([]);$('#browse-inputs').focus();});
// In Create, a lone archive (dropped or opened) is inspected rather than packed into another archive.
function routePaths(paths){if(mode==='create'&&!selected.length&&paths.length===1&&ARCHIVE_EXT.test(paths[0])){setMode('open');showSelection(paths);}else showSelection(paths,true);}
$('#browse-open').addEventListener('click',async e=>{if(blocked(e.currentTarget))return;if(!native){status('Open the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');if(paths?.length){setMode('open');showSelection(paths);}}catch(e){statusError(e);}});
$('#drop-zone').addEventListener('click',e=>{if(e.target.closest('button,input,label,a,summary,pre,.job-now,.archive-inspection,.selection-view'))return;if(selected.length)return;$('#browse-inputs').click();});
$('#choose-destination').addEventListener('click',async e=>{if(blocked(e.currentTarget))return;if(!native){status('Choosing a location needs the Bytepleat desktop app.',true);return;}try{const value=mode==='create'?await invoke('choose_output',{format:$$('input[name="format"]').find(i=>i.checked).value}):await invoke('choose_directory');if(value){destination=value;showDestination(value);updateDestinationNote();updateRunState();}}catch(e){statusError(e);}});
$('#run-job').addEventListener('click',async()=>{
  if(!native){status('This preview cannot run archive operations. Open the Bytepleat desktop app. Nothing was started.',true);return;}
  if((mode==='open'||mode==='extract')&&selected.length>1){showMultiNotice(selected.length);return;}
  if(mode==='extract'&&selectiveExtraction&&selectedEntries.length===0){selectionAlert('Choose at least one entry to extract. Nothing was started.');updateRunState();return;}
  if(mode==='open'&&inspectionInFlight)return;
  try {
    if(mode==='open'){resetInspection();const requestId=++inspectionRequest;listingCache=null;const archivePath=selected[0];inspectionInFlight=true;updateRunState();status(isTar(selected[0])?'Reading TAR archive; it has to be fully unpacked to list it…':'Reading archive listing…');try{const listing=await invoke('inspect_archive',{path:archivePath});if(requestId!==inspectionRequest||mode!=='open'||selected.length!==1||selected[0]!==archivePath)return;renderArchiveListing(listing);listingCache={path:archivePath,listing};status(`${listing.entries.length} of ${listing.total_entries} entries${listing.truncated?' (preview truncated)':''} · ${formatBytes(listing.total_bytes)} · listing only; contents have not been checked.`);}catch(error){if(requestId===inspectionRequest)statusError(error,()=>$('#run-job').click());}finally{if(requestId===inspectionRequest){inspectionInFlight=false;updateRunState();}}return;}
    const format=$$('input[name="format"]').find(i=>i.checked)?.value;
    const target=mode==='extract'?extractTarget():destination;
    const request={action:mode==='create'?'create':'extract',inputs:selected.map(path=>path),destination:target,format:mode==='create'?format:null,selected_entries:mode==='extract'?[...selectedEntries]:[],selective:mode==='extract'&&selectiveExtraction,max_output_bytes:1073741824};
    if(mode==='create')playFold();
    const jobId=await invoke('start_job',{request});if(jobId!=null)jobRequests.set(String(jobId),request);status(`${MODES[mode].run} started.`);await refreshJobs();
  } catch(error){statusError(error,()=>$('#run-job').click());}
});
function entryNameHtml(name){const trimmed=name.replace(/\/$/,'');const cut=trimmed.lastIndexOf('/');const dir=cut>=0?name.slice(0,cut+1):'';const base=cut>=0?name.slice(cut+1):name;return `${dir?`<span class="entry-dir">${esc(dir)}</span>`:''}${esc(base)}`;}
function renderArchiveListing(listing,preselected=[]){
  const section=$('#archive-inspection');section.hidden=false;$('#drop-zone').classList.add('show-listing');const total=listing.total_entries??listing.entries.length;const shown=Math.min(listing.entries.length,5000);
  const archive=selected[0]?basename(selected[0]):'Archive';
  $('#inspection-title').textContent=archive;
  $('#inspection-summary').textContent=`${listing.format?`${listing.format} · `:''}${num(total)} ${total===1?'entry':'entries'} · ${formatBytes(listing.total_bytes)} unpacked${listing.truncated?' · preview limited':''}`;
  dirNames=new Set(listing.entries.filter(entry=>entry.is_dir).map(entry=>entry.name));
  selectedEntries=listing.entries.slice(0,shown).map(entry=>entry.name).filter(name=>preselected.includes(name));
  const host=$('#entry-list');host.innerHTML=listing.entries.slice(0,shown).map((entry,index)=>`<label class="entry-row"><input type="checkbox" data-entry="${index}"${selectedEntries.includes(entry.name)?' checked':''}><span class="entry-name">${entryNameHtml(entry.name)}</span><span class="entry-size">${entry.is_dir?'Folder':formatBytes(entry.size)}</span></label>`).join('') || '<p class="selection-empty">No entries listed.</p>';
  const cap=$('#entry-cap');
  if(total>shown){cap.className='cap-note';cap.innerHTML=`${ICON.info}<div><p class="entry-limit">Showing the first ${num(shown)} of ${num(total)} entries. Only listed entries can be chosen for extraction. To get everything, extract the whole archive.</p><p class="caption">For the full list, run <code>bytepleat info ${esc(archive)} --json</code> <button type="button" class="button-text" data-copy="bytepleat info ${esc(archive)} --json">Copy</button></p></div>`;}
  else{cap.className='cap-note is-quiet';cap.innerHTML=`<p class="caption">Showing all ${num(shown)} ${shown===1?'entry':'entries'}.</p>`;}
  cap.hidden=false;
  host.querySelectorAll('[data-entry]').forEach(box=>box.addEventListener('change',()=>{const entry=listing.entries[Number(box.dataset.entry)].name;if(box.checked){selectedEntries.push(entry);}else{selectedEntries=selectedEntries.filter(name=>name!==entry);}updateRunState();}));
  $('#select-all').onchange=()=>{const all=$('#select-all').checked;selectedEntries=all?listing.entries.slice(0,shown).map(entry=>entry.name):[];host.querySelectorAll('[data-entry]').forEach(box=>{box.checked=all;});updateRunState();};
  $('#extract-selected').onclick=()=>{if(selected.length!==1)return;if(selectedEntries.length===0){selectionAlert('Choose at least one entry to extract. Nothing was started.');$('#select-all').focus();return;}startSelectiveExtract(selected[0],[...selectedEntries]);};
  updateRunState();
}
$('#extract-all').addEventListener('click',()=>{if(selected.length!==1)return;const archive=selected[0];setMode('extract');showSelection([archive]);$('#choose-destination').focus();});
$('#review-change').addEventListener('click',()=>{
  const archive=selected[0];const entries=[...selectedEntries];const cached=listingCache?.path===archive?listingCache.listing:null;
  setMode('open');showSelection([archive]);
  if(cached){renderArchiveListing(cached,entries);status('Showing the listing from your earlier inspection. Inspect again to refresh it.');$('#inspection-title').focus();}
  else status('Inspect the archive again to change which entries are chosen.');
});
$('#review-clear').addEventListener('click',()=>{selectedEntries=[];selectiveExtraction=false;renderReview();updateRunState();updateDestinationNote();status('The whole archive will be extracted. Choose a destination folder, then extract.');$('#choose-destination').focus();});
function formatBytes(n){if(n===0)return '0 B';if(!n)return 'size unavailable';const units=['B','KB','MB','GB','TB'];let u=0,x=n;while(x>=1000&&u<units.length-1){x/=1000;u++;}return `${x.toFixed(u?1:0)} ${units[u]}`;}

function jobName(job){
  const request=jobRequests.get(String(job.id));
  if(job.output)return basename(job.output);
  if(request)return basename(request.action==='create'?request.destination:request.inputs[0]);
  if(inspectNames.has(job.id))return inspectNames.get(job.id);
  return '';
}
function jobSubject(job){
  const request=jobRequests.get(String(job.id));
  if(request)return basename(request.action==='create'?request.destination:request.inputs[0]);
  if(inspectNames.has(job.id))return inspectNames.get(job.id);
  return job.output?basename(job.output):'';
}
function jobProgress(job){
  if(!isActive(job))return '';
  const label=JOB_LABEL[job.action]||'Job';
  const determinate=job.state==='running'&&job.total_bytes>0&&!['compressing','decoding','starting'].includes(job.phase);
  if(!determinate){const soFar=job.state==='cancelling'?'Stopping…':job.processed_bytes>0?`${formatBytes(job.processed_bytes)} so far`:(job.message||'Working…');return `<div class="progress-track is-indeterminate" role="progressbar" aria-label="${esc(label)} progress" aria-valuetext="${esc(soFar)}"><span></span></div><p class="progress-caption">${esc(soFar)}</p>`;}
  const percent=Math.min(100,Math.floor(job.processed_bytes/job.total_bytes*100));
  const caption=`${formatBytes(job.processed_bytes)} of ${formatBytes(job.total_bytes)}`;
  return `<div class="progress-track" role="progressbar" aria-label="${esc(label)} progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" aria-valuetext="${percent}%, ${esc(caption)}"><span style="width:${percent}%"></span></div><p class="progress-caption">${percent}% · ${esc(caption)}</p>`;
}
function jobAssurance(job){
  if(job.state==='completed')return job.action==='inspect'?'Listing only. File contents have not been checked.':job.action==='extract'?'The archive itself was not changed.':'Your originals were not changed.';
  if(job.state==='failed')return job.action==='extract'?'Nothing was extracted. The archive itself was not changed.':'Nothing was saved and your originals are untouched.';
  if(job.state==='cancelled')return job.action==='extract'?'Nothing was extracted. The staging folder was removed.':'Nothing was saved. The temporary file was removed, and your originals are untouched.';
  return '';
}
function jobActionButton(job,className){
  if(job.state==='running'||job.state==='queued')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel">Cancel</button>`;
  if(job.state==='cancelling')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel" disabled>Stopping…</button>`;
  if(job.state==='completed'&&job.action!=='inspect')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="open">${SHOW_LABEL}</button>`;
  if(job.state==='failed'&&jobRequests.has(String(job.id)))return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="retry">Try again</button>`;
  return '';
}
function outcomeShown(job){return Boolean(job&&job.action!=='inspect'&&(isActive(job)||job.id!==dismissedJob));}
function renderJobBand(job){
  const band=$('#job-band');const active=Boolean(job&&isActive(job));
  document.body.classList.toggle('is-running',active);
  if(!active){band.hidden=true;band.replaceChildren();return;}
  band.hidden=false;
  band.innerHTML=`<div class="job-band-progress">${jobProgress(job)}</div>${jobActionButton(job,'button button-secondary job-cancel')}`;
}
function renderJobNow(job){
  const host=$('#job-now');
  renderJobBand(job);
  const show=outcomeShown(job);
  $('#drop-zone').classList.toggle('show-job',show);
  document.body.classList.toggle('show-job',show);
  document.body.classList.toggle('show-outcome',show&&!isActive(job));
  if(!show){host.hidden=true;host.className='job-now';host.replaceChildren();return;}
  const subject=jobSubject(job)||'the archive';
  const name=jobName(job)||subject;
  const stateChip=`<span class="job-state">${esc(STATE_LABEL[job.state]||job.state)}</span>`;
  let body='';
  if(isActive(job)){
    const title=job.action==='extract'?`Extracting ${subject}`:job.action==='inspect'?`Reading ${subject}`:`Creating ${subject}`;
    const line=job.action==='extract'?'Extracting into a staging folder first. Nothing appears in the destination until it is complete.':`Writing to a temporary file. It becomes ${subject} when done.`;
    body=`<div class="job-glyph is-running">${ICON.mark}</div><div class="job-text"><h3 class="job-title">${esc(title)}</h3>${stateChip}<p class="job-line">${esc(line)}</p></div>`;
  } else if(job.state==='completed'){
    const title=job.action==='extract'?`Extracted to ${name}`:`${name} is ready`;
    const path=job.output?`<p class="job-output"><code class="path" title="${esc(job.output)}">${esc(job.output)}</code><button type="button" class="button-text" data-copy="${esc(job.output)}">Copy path</button></p>`:'';
    const again=job.action==='extract'?'Extract another':'Create another';
    body=`<div class="job-glyph is-done">${ICON.mark}</div><div class="job-text"><h3 class="job-title">${esc(title)}</h3>${stateChip}<p class="job-line">${esc(jobAssurance(job))}</p>${path}<div class="job-actions">${jobActionButton(job,'button button-primary')}<button type="button" class="button-text" data-outcome="another">${again}</button></div></div>`;
  } else if(job.state==='failed'){
    const friendly=friendlyError(job.error||job.message);
    const title=job.action==='extract'?`Could not extract ${subject}`:`Could not create ${subject}`;
    const relocate=/taken|not allowed|larger/.test(friendly.summary)?`<button type="button" class="button button-primary" data-outcome="relocate">Choose another location…</button>`:'';
    const details=friendly.detail&&friendly.detail!==friendly.summary?`<details class="job-detail"><summary>Technical details</summary><pre>${esc(friendly.detail)}</pre><button type="button" class="button-text" data-copy="${esc(friendly.detail)}">Copy details</button></details>`:'';
    body=`<div class="job-glyph is-error">${ICON.alert}</div><div class="job-text"><h3 class="job-title">${esc(title)}</h3>${stateChip}<p class="job-error">${esc(friendly.summary)}</p><p class="job-line">${esc(jobAssurance(job))}</p><div class="job-actions">${relocate}${jobActionButton(job,relocate?'button button-secondary':'button button-primary')}<button type="button" class="button-text" data-outcome="close">Close</button></div>${details}</div>`;
  } else {
    const again=jobRequests.has(String(job.id))?`<button class="button button-primary" type="button" data-job="${esc(job.id)}" data-action="retry">Start again</button>`:'';
    body=`<div class="job-glyph is-cancelled">${ICON.minus}</div><div class="job-text"><h3 class="job-title">Cancelled</h3>${stateChip}<p class="job-line">${esc(jobAssurance(job))}</p><div class="job-actions">${again}<button type="button" class="button-text" data-outcome="change">${job.action==='extract'?'Change archive':'Change files'}</button></div></div>`;
  }
  host.hidden=false;
  host.className=`job-now state-${job.state} action-${esc(job.action)}`;
  host.innerHTML=body;
}
function renderJobHistory(jobs){
  const host=$('#job-list');
  if(!jobs.length){host.innerHTML='<p class="empty-history">Your jobs will appear here. History stays on this device.</p>';return;}
  host.innerHTML=jobs.map((job,index)=>{
    const button=(index>0||(!isActive(job)&&!outcomeShown(job)))?jobActionButton(job,'button-text'):'';
    const verb=job.state==='completed'?(DONE_VERB[job.action]||'Completed'):STATE_LABEL[job.state]||job.state;
    const fact=job.state==='cancelled'?(job.action==='extract'?'nothing extracted':job.action==='inspect'?'nothing read':'nothing saved'):'';
    const icon=job.state==='completed'?ICON.check:job.state==='failed'?ICON.alert:job.state==='cancelled'?ICON.minus:ICON.dot;
    const detail=job.state==='failed'?`<small class="job-item-detail">${esc(friendlyError(job.error||job.message).summary)}</small>`:'';
    const name=jobName(job)||JOB_LABEL[job.action]||job.action;
    return `<div class="job-item state-${esc(job.state)}"><span class="job-item-icon">${icon}</span><div class="job-item-text"><strong title="${esc(job.output||name)}">${esc(name)}</strong><small>${esc([verb,fact].filter(Boolean).join(' · '))}</small>${detail}${button?`<div class="job-actions">${button}</div>`:''}</div></div>`;
  }).join('');
}
function announceJobChanges(jobs){
  jobs.forEach(job=>{
    const previous=lastJobStates.get(job.id);
    lastJobStates.set(job.id,job.state);
    if(previous&&previous!==job.state&&!isActive(job)){
      $('#announce').textContent=`${JOB_LABEL[job.action]||job.action}: ${STATE_LABEL[job.state]||job.state}.`;
      if(job===jobs[0]&&job.state==='completed'&&job.action==='extract')playUnfold(job);
      if(job===jobs[0]&&job.action!=='inspect')requestAnimationFrame(()=>$('#job-now [data-action="open"],#job-now [data-action="retry"],#job-now .button-primary')?.focus());
    }
    if(!previous&&isActive(job)&&job===jobs[0]&&job.action!=='inspect')requestAnimationFrame(()=>$('#job-band [data-action="cancel"]')?.focus());
  });
}
function renderJobs(jobs){
  // inspect_archive does not return a job id; remember which archive a newly seen inspect job is reading.
  jobs.forEach(job=>{if(job.action==='inspect'&&!lastJobStates.has(job.id)&&!inspectNames.has(job.id)&&inspectionInFlight&&selected[0])inspectNames.set(job.id,basename(selected[0]));});
  currentJobs=jobs;updateRunState();const fingerprint=JSON.stringify(jobs);if(fingerprint===lastJobsFingerprint)return;lastJobsFingerprint=fingerprint;
  // Progress updates replace the markup; put keyboard focus back on the same control afterwards.
  const focused=document.activeElement?.closest?.('[data-job]');const focusKey=focused?[focused.dataset.job,focused.dataset.action]:null;
  renderJobNow(jobs[0]);
  renderJobHistory(jobs);
  announceJobChanges(jobs);
  if(focusKey){const next=$$('[data-job]').find(el=>el.dataset.job===focusKey[0]&&el.dataset.action===focusKey[1]&&!el.disabled);next?.focus();}
}
document.addEventListener('click',async event=>{
  const btn=event.target.closest('[data-job]');if(!btn||btn.disabled)return;
  try{if(btn.dataset.action==='cancel')await invoke('cancel_job',{id:btn.dataset.job});else if(btn.dataset.action==='retry'){const request=jobRequests.get(btn.dataset.job);if(request){const id=await invoke('start_job',{request});if(id!=null)jobRequests.set(String(id),request);}}else await invoke('open_destination',{id:btn.dataset.job});await refreshJobs();}catch(e){statusError(e);}
});
// Outcome actions only change what the sheet shows; nothing here talks to the backend.
document.addEventListener('click',event=>{
  const copy=event.target.closest('[data-copy]');
  if(copy){const label=copy.textContent;Promise.resolve().then(()=>navigator.clipboard.writeText(copy.dataset.copy)).then(()=>{copy.textContent='Copied';setTimeout(()=>{copy.textContent=label;},2000);},()=>{copy.textContent='Select the text to copy it';setTimeout(()=>{copy.textContent=label;},2000);});return;}
  const action=event.target.closest('[data-outcome]')?.dataset.outcome;if(!action)return;
  const job=currentJobs[0];dismissedJob=job?.id??null;renderJobNow(job);renderJobHistory(currentJobs);
  if(action==='another')showSelection([]);
  if(action==='relocate')$('#choose-destination').click();
  if(action==='change')(mode==='create'?$('#add-files'):$('#open-different')).focus();
  if(action==='another'||action==='close')$('#browse-inputs').focus();
});
async function refreshJobs(){if(!native)return;try{renderJobs(await invoke('jobs'));}catch(e){statusError(e);}}
async function receivePaths(action,paths,error){if(error){showSelection([]);statusError(error);return;}if(!paths?.length)return;setMode(action==='create'?'create':action==='extract'?'extract':'open');showSelection(paths);if(action!=='create'&&paths.length>1)showMultiNotice(paths.length);}

// Signature motion. Both run on a detached overlay of cloned rows, so they never delay or block the real state underneath.
function foldLayer(rect){const layer=document.createElement('div');layer.className='fold-layer';layer.setAttribute('aria-hidden','true');Object.assign(layer.style,{left:`${rect.left}px`,top:`${rect.top}px`,width:`${rect.width}px`,height:`${rect.height}px`});document.body.append(layer);return layer;}
function playFold(){
  if(reduceMotion.matches||typeof Element.prototype.animate!=='function')return;
  const rows=$$('#selection .selected-item');if(!rows.length)return;
  const sheet=$('#drop-zone').getBoundingClientRect();const band=$('#band').getBoundingClientRect();
  const layer=foldLayer(sheet);const visible=rows.slice(0,8);const faces=[...visible];
  $('#run-job').animate([{transform:'scale(1)'},{transform:'scale(.98)'},{transform:'scale(1)'}],{duration:160,easing:'ease-out'});
  $('.mode-tabs').animate([{opacity:1},{opacity:.55},{opacity:1}],{duration:700,easing:'ease-out'});
  const first=visible[0].getBoundingClientRect();
  const extra=rows.length>8;
  const items=faces.map(row=>({rect:row.getBoundingClientRect(),html:row.querySelector('.file-details')?.outerHTML||''}));
  if(extra){const last=items[items.length-1].rect;items.push({rect:{top:last.top+last.height,left:last.left,width:last.width,height:last.height},html:''});}
  const squeeze=Math.cos(64*Math.PI/180);
  items.forEach((item,i)=>{
    const face=document.createElement('div');face.className=`fold-face ${i%2?'is-shade':'is-lit'}`;face.innerHTML=`<div class="fold-face-text">${item.html}</div>`;
    Object.assign(face.style,{top:`${item.rect.top-sheet.top}px`,left:`${item.rect.left-sheet.left}px`,width:`${item.rect.width}px`,height:`${item.rect.height}px`,transformOrigin:i%2?'50% 100%':'50% 0%'});
    layer.append(face);
    const targetTop=(first.top-sheet.top)+i*item.rect.height*squeeze-(i%2?item.rect.height*(1-squeeze):0);
    const dy=targetTop-(item.rect.top-sheet.top);
    face.animate([{transform:'translateY(0) rotateX(0deg)',backgroundColor:'var(--color-surface)'},{transform:`translateY(${dy}px) rotateX(${i%2?-64:64}deg)`,backgroundColor:i%2?'var(--color-fold-shade)':'var(--color-fold-light)'}],{duration:520,delay:80,easing:'cubic-bezier(0.65,0,0.25,1)',fill:'both'});
    face.firstElementChild.animate([{opacity:1},{opacity:0}],{duration:160,delay:80,fill:'both'});
  });
  // FLIP landing: the folded stack moves into the action band, where the pleated progress strip takes over.
  const stackHeight=items.length*first.height*squeeze;
  const dx=(band.left+24)-sheet.left;const dy=(band.top+12)-(first.top);
  const sx=Math.max(.2,(band.width-180)/first.width);const sy=Math.max(.2,40/Math.max(stackHeight,1));
  const land=layer.animate([{transform:'none',opacity:1},{transform:`translate(${dx}px,${dy}px) scale(${sx},${sy})`,opacity:.0}],{duration:250,delay:600,easing:'cubic-bezier(0,0,0,1)',fill:'both'});
  layer.style.transformOrigin='0 0';
  land.finished.then(()=>layer.remove(),()=>layer.remove());
}
function playUnfold(job){
  if(reduceMotion.matches||typeof Element.prototype.animate!=='function')return;
  const sheet=$('#drop-zone').getBoundingClientRect();const band=$('#band').getBoundingClientRect();
  const request=jobRequests.get(String(job.id));
  const names=[...new Set((request?.selected_entries||[]).map(name=>name.split('/')[0]))].slice(0,8);
  const count=names.length||5;const rowH=36;const top=24;
  const layer=foldLayer(sheet);layer.style.transformOrigin='0 0';
  const squeeze=Math.cos(64*Math.PI/180);
  layer.animate([{transform:`translate(${band.left+24-sheet.left}px,${band.top+12-sheet.top-top}px) scale(${Math.max(.2,(band.width-180)/(sheet.width-48))},.4)`,opacity:.4},{transform:'none',opacity:1}],{duration:250,easing:'cubic-bezier(0,0,0,1)',fill:'both'});
  for(let i=0;i<count;i++){
    const face=document.createElement('div');face.className=`fold-face ${i%2?'is-shade':'is-lit'}`;
    face.innerHTML=`<div class="fold-face-text"><div class="file-details"><strong>${esc(names[i]||'')}</strong></div></div>`;
    Object.assign(face.style,{top:`${top+i*rowH}px`,left:'24px',width:`${sheet.width-48}px`,height:`${rowH}px`,transformOrigin:i%2?'50% 100%':'50% 0%'});
    layer.append(face);
    const dy=(top+i*rowH*squeeze-(i%2?rowH*(1-squeeze):0))-(top+i*rowH);
    face.animate([{transform:`translateY(${dy}px) rotateX(${i%2?-64:64}deg)`,backgroundColor:i%2?'var(--color-fold-shade)':'var(--color-fold-light)'},{transform:'translateY(0) rotateX(0deg)',backgroundColor:'var(--color-surface)'}],{duration:520,delay:200,easing:'cubic-bezier(0.65,0,0.25,1)',fill:'both'});
    face.firstElementChild.animate([{opacity:0},{opacity:names[i]?1:0}],{duration:160,delay:560,fill:'both'});
  }
  const out=layer.animate([{opacity:1},{opacity:0}],{duration:167,delay:900,fill:'both'});
  out.finished.then(()=>layer.remove(),()=>layer.remove());
}

// History: a persistent panel at 1200px and wider, a drawer below that.
const wideQuery=window.matchMedia('(min-width: 1200px)');
function setHistory(open,{restoreFocus=true}={}){
  const app=$('#app');const was=app.classList.contains('history-open');
  app.classList.toggle('history-open',open);
  $('#history-toggle').setAttribute('aria-expanded',String(open));
  $('#history-scrim').hidden=!open;
  $('#history').inert=!wideQuery.matches&&!open;
  if(open)$('#history-close').focus();else if(was&&restoreFocus)$('#history-toggle').focus();
}
$('#history-toggle').addEventListener('click',()=>setHistory(!$('#app').classList.contains('history-open')));
$('#history-close').addEventListener('click',()=>setHistory(false));
$('#history-scrim').addEventListener('click',()=>setHistory(false));
wideQuery.addEventListener?.('change',()=>setHistory(false,{restoreFocus:false}));
setHistory(false,{restoreFocus:false});

const formatsDialog=$('#formats-dialog');
$('#formats-open').addEventListener('click',()=>{if(typeof formatsDialog.showModal==='function')formatsDialog.showModal();else formatsDialog.setAttribute('open','');$('#formats-close').focus();});
$('#formats-close').addEventListener('click',()=>{if(typeof formatsDialog.close==='function')formatsDialog.close();else formatsDialog.removeAttribute('open');$('#formats-open').focus();});

// Keyboard map from the design system: Cmd on macOS, Ctrl elsewhere.
document.addEventListener('keydown',e=>{
  const mod=PLATFORM==='mac'?e.metaKey:e.ctrlKey;
  if(e.key==='Escape'){
    if(formatsDialog.open)return;
    if($('#app').classList.contains('history-open')){e.preventDefault();setHistory(false);return;}
    const cancel=$('#job-band [data-action="cancel"]');if(cancel&&!cancel.disabled){e.preventDefault();cancel.click();}
    return;
  }
  if(!mod||e.altKey)return;
  const tabKey={'1':'create','2':'extract','3':'open'}[e.key];
  if(tabKey){e.preventDefault();const tab=$(`#tab-${tabKey}`);if(!blocked(tab)&&mode!==tabKey){setMode(tabKey);}tab.focus();return;}
  if(e.key==='Enter'){e.preventDefault();const primary=!$('#extract-selected').hidden?$('#extract-selected'):$('#run-job');if(!primary.disabled)primary.click();return;}
  if(e.key.toLowerCase()==='o'){e.preventDefault();(e.shiftKey&&mode==='create'?$('#browse-folder'):$('#browse-inputs')).click();return;}
  if(e.key.toLowerCase()==='y'&&!wideQuery.matches){e.preventDefault();setHistory(!$('#app').classList.contains('history-open'));}
});

if(native){
  $('#native-notice').hidden=true;
  listen('selection',event=>receivePaths(event.payload.action,event.payload.paths,event.payload.error));
  listen('jobs-changed',refreshJobs);
  invoke('initial_selection').then(selection=>receivePaths(selection.action,selection.paths,selection.error)).catch(e=>statusError(e));
  const win=window.__TAURI__.webviewWindow.getCurrentWebviewWindow();
  win.onDragDropEvent(event=>{const payload=event.payload;if(payload.type==='over'||payload.type==='enter')$('#drop-zone').classList.add('drag-over');else{$('#drop-zone').classList.remove('drag-over');if(payload.type==='drop')routePaths(payload.paths);}});
  refreshJobs();pollHandle=setInterval(refreshJobs,250);
} else {
  $('#native-notice').hidden=false;
  $('#browse-inputs').disabled=true;$('#browse-folder').disabled=true;$('#choose-destination').disabled=true;
}
// Appearance cycles System, Light, Dark. System removes the override so the OS setting applies.
const THEMES=['system','light','dark'];
let themePref='system';
const darkQuery=window.matchMedia('(prefers-color-scheme: dark)');
// data-theme always holds the resolved light/dark value so the stylesheet needs one dark token block.
function resolveTheme(){document.documentElement.dataset.theme=themePref==='system'?(darkQuery.matches?'dark':'light'):themePref;}
darkQuery.addEventListener?.('change',()=>{if(themePref==='system')resolveTheme();});
function currentTheme(){return themePref;}
function applyTheme(theme,persist){
  themePref=theme;resolveTheme();
  const name=theme[0].toUpperCase()+theme.slice(1);
  $('#theme-label').textContent=name;
  if(persist){try{if(theme==='system')localStorage.removeItem(THEME_KEY);else localStorage.setItem(THEME_KEY,theme);}catch{/* storage unavailable; the choice lasts for this session */}}
}
function toggleTheme(){applyTheme(THEMES[(THEMES.indexOf(currentTheme())+1)%THEMES.length],true);}
let savedTheme=null;try{savedTheme=localStorage.getItem(THEME_KEY);}catch{/* ignore */}
applyTheme(THEMES.includes(savedTheme)?savedTheme:'system',false);
$('#theme-toggle').addEventListener('click',toggleTheme);
setMode('create');
window.addEventListener('beforeunload',()=>{if(pollHandle)clearInterval(pollHandle);});

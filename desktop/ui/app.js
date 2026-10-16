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
const lastJobStates = new Map();
const jobRequests = new Map();
const ARCHIVE_EXT = /\.(zip|7z|tar\.(zst|gz|lz4))$/i;

const NO_DESTINATION = 'No location chosen yet.';
function showDestination(value){const el=$('#destination-path');el.textContent=value||NO_DESTINATION;el.classList.toggle('is-empty',!value);}
const THEME_KEY = 'bytepleat-theme';
// The same words are used for the tab, heading, button, job title and completion message.
const MODES = {
  create: { title: 'Create an archive', hint: 'Pack files or folders into a new archive. Your originals stay where they are.', inputTitle: 'Choose what to archive', inputHint: 'Select files or folders from your device. Archive output is capped at 1 GiB.', dropTitle: 'Drop files to compress, or an archive to inspect', dropSub: 'or choose them with the buttons here', destTitle: 'Save archive as', destHint: 'Choose where the finished archive will go.', destStep: '3', run: 'Create archive', fine: 'Source files stay in place. An existing file is never replaced.', aside: 'Files are copied into the archive. Originals are never moved or removed.' },
  extract: { title: 'Extract an archive', hint: 'Unpack one archive into a new folder. Existing files and folders are never overwritten.', inputTitle: 'Choose an archive to extract', inputHint: 'Select one ZIP, 7z or compressed tar archive. Extracted size is capped at 1 GiB, and archives at 100,000 entries.', dropTitle: 'Drop an archive here', dropSub: 'or choose it with the button here', destTitle: 'Choose a destination', destHint: 'Bytepleat adds a new folder here for the extracted files.', destStep: '2', run: 'Extract archive', fine: 'The archive stays in place. An existing folder is never overwritten.', aside: 'Files are unpacked in a temporary folder and moved into place only after everything succeeds.' },
  open: { title: 'Inspect an archive', hint: 'See what is inside an archive without extracting it. Listing does not check file contents.', inputTitle: 'Choose an archive to inspect', inputHint: 'Select one ZIP, 7z or compressed tar archive. The entry limit is 100,000; the list previews up to 5,000.', dropTitle: 'Drop an archive here', dropSub: 'or choose it with the button here', destTitle: '', destHint: '', destStep: '2', run: 'Inspect archive', fine: 'Nothing is extracted to your folders, and the archive is not changed.', aside: 'Listing does not check file contents. A compressed tar has to be fully unpacked to a temporary folder to list it; that folder is deleted afterwards.' }
};
const JOB_LABEL = { create: 'Create archive', extract: 'Extract archive', inspect: 'Inspect archive' };
const STATE_LABEL = { queued: 'Queued', running: 'Running', cancelling: 'Stopping…', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
const isActive = job => ['queued', 'running', 'cancelling'].includes(job.state);

const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const basename = path => path.replace(/[\\/]$/, '').split(/[\\/]/).pop() || path;
const isTar = path => /\.tar\.(zst|gz|lz4)$/i.test(path);
const extractedName = path => `${basename(path).replace(/\.(tar\.(?:zst|gz|lz4)|zip|7z)$/i, '')}-extracted`;
const pathSeparator = path => (/^[A-Za-z]:[\\/]|^\\\\/.test(path) || (path.includes('\\') && !path.includes('/'))) ? '\\' : '/';
const extractTarget = () => `${destination.replace(/[\\/]$/, '')}/${extractedName(selected[0])}`;
const extractTargetDisplay = () => `${destination.replace(/[\\/]+$/, '')}${pathSeparator(destination)}${extractedName(selected[0])}`;
const REVIEW_STATUS = 'Review the chosen entries, then choose a destination folder.';
const multiArchiveMessage = count => `${count} archives were selected. Choose exactly one archive; nothing was processed.`;
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
    const b = document.createElement('button'); b.type = 'button'; b.id = 'status-retry'; b.className = 'button button-secondary status-retry'; b.textContent = 'Retry';
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
function resetInspection() {
  inspectionRequest++;
  if(inspectionInFlight)status('');
  inspectionInFlight=false;
  selectedEntries=[]; selectiveExtraction=false;
  $('#archive-inspection').hidden=true;
  $('#inspection-summary').textContent='';
  $('#entry-list').replaceChildren();
  renderReview();
}
function updateDestinationNote(override) {
  const note = $('#destination-note');
  if (override) note.textContent = override;
  else if (mode === 'extract' && destination && selected.length === 1) note.textContent = `Extracts into a new folder: ${extractTargetDisplay()}. If it already exists, the job stops.`;
  else if (mode === 'extract' && selected.length === 1) note.textContent = `Creates a new folder named “${extractedName(selected[0])}” inside the folder you choose.`;
  else if (mode === 'extract') note.textContent = 'Creates a new folder named after the archive plus “-extracted” inside the folder you choose.';
  else if (mode === 'create') note.textContent = 'If a file already exists there, the job stops instead of replacing it.';
  else note.textContent = '';
}
function showSelection(paths, append=false) {
  const singleArchive = mode==='extract'||mode==='open';
  const incoming = paths;
  selected = singleArchive ? [...incoming] : [...(append?selected:[]), ...incoming];
  resetInspection();
  if(singleArchive&&selected.length>1)status(multiArchiveMessage(selected.length),true);
  else status('');
  const host=$('#selection');
  if (!selected.length) { host.innerHTML='<div class="selection-empty">Nothing selected yet.</div>'; }
  else host.innerHTML=selected.map((path,i)=>`<div class="selected-item"><span class="file-details"><strong>${esc(basename(path))}</strong><small title="${esc(path)}">${esc(path)}</small></span><button class="remove-item" type="button" data-remove="${i}" aria-label="Remove ${esc(basename(path))} from the selection">Remove</button></div>`).join('');
  host.querySelectorAll('[data-remove]').forEach(btn=>btn.addEventListener('click',()=>{selected.splice(Number(btn.dataset.remove),1);showSelection(selected);updateRunState();}));
  updateRunState();
  updateDestinationNote();
}
function runHint(busy, unsupportedMulti, emptyExtract) {
  if (!native) return 'Open the Bytepleat desktop app to run this.';
  if (busy) return 'A job is running. Wait for it to finish or cancel it.';
  if (inspectionInFlight) return 'Reading the archive listing…';
  if (!selected.length) return mode==='create' ? 'Choose what to archive to continue.' : 'Choose an archive to continue.';
  if (unsupportedMulti) return 'Choose exactly one archive.';
  if (emptyExtract) return 'Select at least one entry to extract.';
  if (mode!=='open' && !destination) return mode==='create' ? 'Choose where to save the archive.' : 'Choose a destination folder.';
  if (mode==='create') return 'Ready. Your originals stay in place.';
  if (mode==='extract') return selectiveExtraction ? `Ready. Extracts ${selectedEntries.length} chosen ${selectedEntries.length===1?'entry':'entries'} into a new folder.` : 'Ready. Files go into a new folder.';
  return $('#archive-inspection').hidden ? 'Ready. Nothing is extracted.' : 'Listing shown above. Tick entries to extract them, or inspect again to refresh it.';
}
function updateEntryHint() {
  $('#entry-hint').textContent = selectedEntries.length
    ? `${selectedEntries.length} selected. Choose Extract selected to pick a destination folder. Bytepleat reads the whole archive first, then keeps only these.`
    : 'No entries ticked yet. Tick the entries you want, then choose Extract selected. To extract everything, use the Extract tab.';
}
function updateSelectionNote() {
  const note = $('#selection-note');
  const text = mode==='open' && selected.length===1 && isTar(selected[0]) ? 'Compressed tar: listing unpacks the whole archive to a temporary folder, which is deleted afterwards. Extracting selected entries later reads it again.' : '';
  note.textContent = text; note.hidden = !text;
}
function renderReview() {
  const show = mode==='extract' && selectiveExtraction && selectedEntries.length>0;
  $('#selected-review').hidden = !show;
  if (!show) { $('#review-list').replaceChildren(); return; }
  $('#review-summary').textContent = `${selectedEntries.length} ${selectedEntries.length===1?'entry':'entries'} from ${basename(selected[0])}`;
  $('#review-list').innerHTML = selectedEntries.map(name=>`<li>${esc(name)}</li>`).join('');
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
function updateRunState() { const hasInput=selected.length>0; $('#format-section').hidden=mode!=='create'||!hasInput; $('#destination-section').hidden=mode==='open'||!hasInput; $('.run-row').hidden=!hasInput; $('#run-fineprint').hidden=!hasInput; const busy=currentJobs.some(isActive); const unsupportedMulti=(mode==='open'||mode==='extract')&&selected.length>1; const emptyExtract=mode==='extract'&&selectiveExtraction&&selectedEntries.length===0; $('#run-job').disabled=!native || busy || inspectionInFlight || selected.length===0 || unsupportedMulti || emptyExtract || (mode!=='open'&&!destination); $('#run-job').title=unsupportedMulti?'Select one archive at a time':emptyExtract?'Select at least one entry to extract':inspectionInFlight?'Reading archive listing…':busy?'One archive job can run at a time':''; $('#run-hint').textContent=runHint(busy,unsupportedMulti,emptyExtract); $('#selection-count').textContent=selected.length?(mode==='create'?`${selected.length} ${selected.length===1?'item':'items'} selected`:`${selected.length} ${selected.length===1?'archive':'archives'} selected`):''; $('#extract-selected').disabled=selectedEntries.length===0; const listed=mode==='open'&&!$('#archive-inspection').hidden; $('#run-label').textContent=listed?'Inspect again':MODES[mode].run; $('#run-job').classList.toggle('is-secondary',listed); $('#extract-selected').classList.toggle('button-primary',listed); $('#extract-selected').classList.toggle('button-secondary',!listed); updateEntryHint(); updateSelectionNote(); }
function setMode(next) {
  mode=next; destination=null; showDestination(null);
  const text=MODES[mode];
  $$('.mode-tab').forEach(btn=>{const active=btn.dataset.mode===mode;btn.classList.toggle('active',active);btn.setAttribute('aria-selected',String(active));btn.tabIndex=active?0:-1;});
  $('#workspace-panel').setAttribute('aria-labelledby',`tab-${mode}`);
  $('#view-label').textContent=text.title;
  $('#view-hint').textContent=text.hint;
  $('#input-title').textContent=text.inputTitle;
  $('#input-hint').textContent=text.inputHint;
  $('#drop-title').textContent=text.dropTitle;
  $('#drop-sub').textContent=text.dropSub;
  $('#browse-inputs').textContent=mode==='create'?'Choose files…':'Choose archive…';
  $('#browse-folder').hidden=mode!=='create'; $('#browse-open').hidden=mode!=='create';
    resetInspection();
  $('#destination-title').textContent=text.destTitle;
  $('#destination-hint').textContent=text.destHint;
  $('#destination-step').textContent=text.destStep;
  $('#run-label').textContent=text.run;
  $('#run-fineprint').textContent=text.fine;
  $('#aside-note').textContent=text.aside;
  showSelection([]); status('');
}
$$('.mode-tab').forEach(btn=>btn.addEventListener('click',()=>setMode(btn.dataset.mode)));
// Arrow keys move focus between tabs; Enter or Space selects, so browsing tabs never clears a selection.
$('.mode-tabs').addEventListener('keydown',e=>{const tabs=$$('.mode-tab');const i=tabs.indexOf(document.activeElement);if(i<0)return;const target={ArrowRight:(i+1)%tabs.length,ArrowLeft:(i+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1}[e.key];if(target===undefined)return;e.preventDefault();tabs[target].focus();});
$$('input[name="format"]').forEach(input=>input.addEventListener('change',()=>{$$('.format-option').forEach(el=>el.classList.toggle('selected',el.contains(input)&&input.checked));const hadDestination=Boolean(destination);destination=null;showDestination(null);updateDestinationNote(hadDestination?'The format changed, so choose the save location again.':'');updateRunState();}));
$('#browse-inputs').addEventListener('click',async()=>{if(!native){status('Open the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');showSelection(paths,true);}catch(e){statusError(e);}});
$('#browse-folder').addEventListener('click',async()=>{if(!native){status('Choosing a folder needs the Bytepleat desktop app.',true);return;}try{const path=await invoke('choose_input_directory');if(path)showSelection([path],true);}catch(e){statusError(e);}});
// In Create, a lone archive (dropped or opened) is inspected rather than packed into another archive.
function routePaths(paths){if(mode==='create'&&!selected.length&&paths.length===1&&ARCHIVE_EXT.test(paths[0])){setMode('open');showSelection(paths);}else showSelection(paths,true);}
$('#browse-open').addEventListener('click',async()=>{if(!native){status('Open the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');if(paths?.length){setMode('open');showSelection(paths);}}catch(e){statusError(e);}});
$('#drop-zone').addEventListener('click',e=>{if(e.target.closest('button'))return;$('#browse-inputs').click();});
$('#choose-destination').addEventListener('click',async()=>{if(!native){status('Choosing a location needs the Bytepleat desktop app.',true);return;}try{const value=mode==='create'?await invoke('choose_output',{format:$$('input[name="format"]').find(i=>i.checked).value}):await invoke('choose_directory');if(value){destination=value;showDestination(value);updateDestinationNote();updateRunState();}}catch(e){statusError(e);}});
$('#run-job').addEventListener('click',async()=>{
  if(!native){status('This preview cannot run archive operations. Open the Bytepleat desktop app. Nothing was started.',true);return;}
  if((mode==='open'||mode==='extract')&&selected.length>1){status(multiArchiveMessage(selected.length),true);return;}
  if(mode==='extract'&&selectiveExtraction&&selectedEntries.length===0){status('Select at least one entry to extract. No archive operation was started.',true);updateRunState();return;}
  if(mode==='open'&&inspectionInFlight)return;
  try {
    if(mode==='open'){resetInspection();const requestId=++inspectionRequest;listingCache=null;const archivePath=selected[0];inspectionInFlight=true;updateRunState();status(isTar(selected[0])?'Reading TAR archive; it has to be fully unpacked to list it…':'Reading archive listing…');try{const listing=await invoke('inspect_archive',{path:archivePath});if(requestId!==inspectionRequest||mode!=='open'||selected.length!==1||selected[0]!==archivePath)return;renderArchiveListing(listing);listingCache={path:archivePath,listing};status(`${listing.entries.length} of ${listing.total_entries} entries${listing.truncated?' (preview truncated)':''} · ${formatBytes(listing.total_bytes)} · listing only; contents have not been checked.`);}catch(error){if(requestId===inspectionRequest)statusError(error,()=>$('#run-job').click());}finally{if(requestId===inspectionRequest){inspectionInFlight=false;updateRunState();}}return;}
    const format=$$('input[name="format"]').find(i=>i.checked)?.value;
    const target=mode==='extract'?extractTarget():destination;
    const request={action:mode==='create'?'create':'extract',inputs:selected.map(path=>path),destination:target,format:mode==='create'?format:null,selected_entries:mode==='extract'?[...selectedEntries]:[],selective:mode==='extract'&&selectiveExtraction,max_output_bytes:1073741824};
    const jobId=await invoke('start_job',{request});if(jobId!=null)jobRequests.set(String(jobId),request);status(`${MODES[mode].run} started.`);await refreshJobs();
  } catch(error){statusError(error,()=>$('#run-job').click());}
});
function renderArchiveListing(listing,preselected=[]){
  const section=$('#archive-inspection');section.hidden=false;const total=listing.total_entries??listing.entries.length;const shown=Math.min(listing.entries.length,5000);$('#inspection-summary').textContent=`Showing ${shown} of ${total} ${total===1?'entry':'entries'} · ${formatBytes(listing.total_bytes)}${listing.truncated?' · preview limited':''}`;
  selectedEntries=listing.entries.slice(0,shown).map(entry=>entry.name).filter(name=>preselected.includes(name));
  const host=$('#entry-list');host.innerHTML=listing.entries.slice(0,shown).map((entry,index)=>`<label class="entry-row"><input type="checkbox" data-entry="${index}"${selectedEntries.includes(entry.name)?' checked':''}><span class="entry-name">${esc(entry.name)}</span><span class="entry-size">${entry.is_dir?'Folder':formatBytes(entry.size)}</span></label>`).join('') || '<p class="selection-empty">No entries listed.</p>';
  if(total>shown){const note=document.createElement('p');note.className='entry-limit';note.textContent=`Showing ${shown} of ${total} entries. Only listed entries can be selected for extraction.`;host.append(note);}
  host.querySelectorAll('[data-entry]').forEach(box=>box.addEventListener('change',()=>{const entry=listing.entries[Number(box.dataset.entry)].name;if(box.checked){selectedEntries.push(entry);}else{selectedEntries=selectedEntries.filter(name=>name!==entry);}updateRunState();}));
  $('#extract-selected').onclick=()=>{if(selected.length!==1||selectedEntries.length===0)return;startSelectiveExtract(selected[0],[...selectedEntries]);};
  updateRunState();
}
$('#review-change').addEventListener('click',()=>{
  const archive=selected[0];const entries=[...selectedEntries];const cached=listingCache?.path===archive?listingCache.listing:null;
  setMode('open');showSelection([archive]);
  if(cached){renderArchiveListing(cached,entries);status('Showing the listing from your earlier inspection. Inspect again to refresh it.');$('#inspection-title').focus();}
  else status('Inspect the archive again to change which entries are chosen.');
});
$('#review-clear').addEventListener('click',()=>{selectedEntries=[];selectiveExtraction=false;renderReview();updateRunState();updateDestinationNote();status('The whole archive will be extracted. Choose a destination folder, then extract.');$('#choose-destination').focus();});
function formatBytes(n){if(n===0)return '0 B';if(!n)return 'size unavailable';const units=['B','KB','MB','GB','TB'];let u=0,x=n;while(x>=1000&&u<units.length-1){x/=1000;u++;}return `${x.toFixed(u?1:0)} ${units[u]}`;}

function jobProgress(job){
  if(!isActive(job))return '';
  const label=JOB_LABEL[job.action]||'Job';
  const determinate=job.state==='running'&&job.total_bytes>0&&!['compressing','decoding','starting'].includes(job.phase);
  if(!determinate)return `<div class="progress-track is-indeterminate" role="progressbar" aria-label="${esc(label)} progress" aria-valuetext="${job.state==='cancelling'?'Stopping':'Working'}"><span></span></div>`;
  const percent=Math.min(100,Math.floor(job.processed_bytes/job.total_bytes*100));
  const caption=`${formatBytes(job.processed_bytes)} of ${formatBytes(job.total_bytes)}`;
  return `<div class="progress-track" role="progressbar" aria-label="${esc(label)} progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" aria-valuetext="${percent}%, ${esc(caption)}"><span style="width:${percent}%"></span></div><p class="progress-caption">${percent}% · ${esc(caption)}</p>`;
}
function jobAssurance(job){
  if(job.state==='completed')return job.action==='inspect'?'Listing only. File contents have not been checked.':'Your originals were not changed.';
  if(job.state==='failed')return 'Your originals were not changed. Check the message above, then try again or adjust your choices.';
  if(job.state==='cancelled')return 'Stopped before finishing. Your originals were not changed.';
  return '';
}
function jobActionButton(job,className){
  if(job.state==='running'||job.state==='queued')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel">Cancel</button>`;
  if(job.state==='cancelling')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel" disabled>Stopping…</button>`;
  if(job.state==='completed'&&job.action!=='inspect')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="open">Show in folder</button>`;
  if(job.state==='failed'&&jobRequests.has(String(job.id)))return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="retry">Retry</button>`;
  return '';
}
function renderJobNow(job){
  const host=$('#job-now');
  if(!job){host.hidden=true;host.className='job-now';host.replaceChildren();return;}
  const label=JOB_LABEL[job.action]||job.action;
  const message=job.message&&job.message!==job.error?`<p class="job-message">${esc(job.message)}</p>`:'';
  const friendly=job.error?friendlyError(job.error):null;
  const error=friendly?`<p class="job-error">${esc(friendly.summary)}</p>${friendly.detail&&friendly.detail!==friendly.summary?`<details class="job-detail"><summary>Technical details</summary><pre>${esc(friendly.detail)}</pre></details>`:''}`:'';
  const output=job.state==='completed'&&job.output?`<p class="job-output"><span class="job-output-label">${job.action==='extract'?'Extracted to':'Saved to'}</span>${esc(job.output)}</p>`:'';
  const assurance=jobAssurance(job);
  const button=jobActionButton(job,'button button-secondary');
  host.hidden=false;
  host.className=`job-now state-${job.state}`;
  host.innerHTML=`<h3 class="job-title">${esc(label)} <span class="job-state">${esc(STATE_LABEL[job.state]||job.state)}</span></h3>${message}${jobProgress(job)}${error}${output}${assurance?`<p class="job-assurance">${esc(assurance)}</p>`:''}${button?`<div class="job-actions">${button}</div>`:''}`;
}
function renderJobHistory(jobs){
  const host=$('#job-list');
  if(!jobs.length){host.innerHTML='<p class="empty-history">Your archive jobs will appear here.</p>';return;}
  host.innerHTML=jobs.map((job,index)=>{
    const button=index>0?jobActionButton(job,'button button-quiet'):'';
    const detail=(job.error&&friendlyError(job.error).summary)||job.message||STATE_LABEL[job.state]||job.state;
    return `<div class="job-item state-${esc(job.state)}"><strong>${esc(JOB_LABEL[job.action]||job.action)} · ${esc(STATE_LABEL[job.state]||job.state)}</strong><small>${esc(detail)}</small>${button?`<div class="job-actions">${button}</div>`:''}</div>`;
  }).join('');
}
function announceJobChanges(jobs){
  jobs.forEach(job=>{
    const previous=lastJobStates.get(job.id);
    lastJobStates.set(job.id,job.state);
    if(previous&&previous!==job.state&&!isActive(job))$('#announce').textContent=`${JOB_LABEL[job.action]||job.action}: ${STATE_LABEL[job.state]||job.state}.`;
  });
}
function renderJobs(jobs){
  currentJobs=jobs;updateRunState();const fingerprint=JSON.stringify(jobs);if(fingerprint===lastJobsFingerprint)return;lastJobsFingerprint=fingerprint;
  // Progress updates replace the markup; put keyboard focus back on the same control afterwards.
  const focused=document.activeElement?.closest?.('[data-job]');const focusKey=focused?[focused.dataset.job,focused.dataset.action]:null;
  announceJobChanges(jobs);
  renderJobNow(jobs[0]);
  renderJobHistory(jobs);
  if(focusKey){const next=$$('[data-job]').find(el=>el.dataset.job===focusKey[0]&&el.dataset.action===focusKey[1]&&!el.disabled);next?.focus();}
}
document.addEventListener('click',async event=>{
  const btn=event.target.closest('[data-job]');if(!btn||btn.disabled)return;
  try{if(btn.dataset.action==='cancel')await invoke('cancel_job',{id:btn.dataset.job});else if(btn.dataset.action==='retry'){const request=jobRequests.get(btn.dataset.job);if(request){const id=await invoke('start_job',{request});if(id!=null)jobRequests.set(String(id),request);}}else await invoke('open_destination',{id:btn.dataset.job});await refreshJobs();}catch(e){statusError(e);}
});
async function refreshJobs(){if(!native)return;try{renderJobs(await invoke('jobs'));}catch(e){statusError(e);}}
async function receivePaths(action,paths,error){if(error){showSelection([]);statusError(error);return;}if(!paths?.length)return;setMode(action==='create'?'create':action==='extract'?'extract':'open');showSelection(paths);if(action!=='create'&&paths.length>1)status(multiArchiveMessage(paths.length),true);}
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

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
const lastJobStates = new Map();

const NO_DESTINATION = 'No location chosen yet.';
const THEME_KEY = 'bytepleat-theme';
// The same words are used for the tab, heading, button, job title and completion message.
const MODES = {
  create: { title: 'Create an archive', hint: 'Pack files or folders into a new archive. Your originals stay where they are.', inputTitle: 'Choose what to archive', inputHint: 'Select files or folders from your device.', dropTitle: 'Drop files or a folder here', dropSub: 'or choose them with the system file dialog', destTitle: 'Save archive as', destHint: 'Choose where the finished archive will go.', destStep: '3', run: 'Create archive' },
  extract: { title: 'Extract an archive', hint: 'Unpack one archive into a new folder. Existing files and folders are never overwritten.', inputTitle: 'Choose an archive to extract', inputHint: 'Select one ZIP, 7z or compressed tar archive.', dropTitle: 'Drop an archive here', dropSub: 'or choose it with the system file dialog', destTitle: 'Extract to folder', destHint: 'Choose the folder that will hold the new extracted folder.', destStep: '2', run: 'Extract archive' },
  open: { title: 'Inspect an archive', hint: 'See what is inside an archive without extracting it. Listing does not check file contents.', inputTitle: 'Choose an archive to inspect', inputHint: 'Select one ZIP, 7z or compressed tar archive.', dropTitle: 'Drop an archive here', dropSub: 'or choose it with the system file dialog', destTitle: '', destHint: '', destStep: '2', run: 'Inspect archive' }
};
const JOB_LABEL = { create: 'Create archive', extract: 'Extract archive', inspect: 'Inspect archive' };
const STATE_LABEL = { queued: 'Queued', running: 'Running', cancelling: 'Stopping…', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
const isActive = job => ['queued', 'running', 'cancelling'].includes(job.state);

const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const basename = path => path.replace(/[\\/]$/, '').split(/[\\/]/).pop() || path;
const extractedName = path => `${basename(path).replace(/\.(tar\.(?:zst|gz|lz4)|zip|7z)$/i, '')}-extracted`;
const multiArchiveMessage = count => `${count} archives were selected. Choose exactly one archive; nothing was processed.`;
function status(message, error=false) {
  const el = $('#status-message');
  el.textContent = message;
  el.classList.toggle('is-error', Boolean(error && message));
  el.setAttribute('aria-live', error ? 'assertive' : 'polite');
}
function resetInspection() {
  inspectionRequest++;
  if(inspectionInFlight)status('');
  inspectionInFlight=false;
  selectedEntries=[]; selectiveExtraction=false;
  $('#archive-inspection').hidden=true;
  $('#inspection-summary').textContent='';
  $('#entry-list').replaceChildren();
}
function updateDestinationNote(override) {
  const note = $('#destination-note');
  if (override) note.textContent = override;
  else if (mode === 'extract' && destination && selected.length === 1) note.textContent = `Files go into a new folder named “${extractedName(selected[0])}”. If it already exists, the job stops.`;
  else if (mode === 'extract') note.textContent = 'A new folder named after the archive plus “-extracted” is created inside it.';
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
  if (!native) return 'Open Bytepleat Desktop to run this.';
  if (busy) return 'A job is running. Wait for it to finish or cancel it.';
  if (inspectionInFlight) return 'Reading the archive listing…';
  if (!selected.length) return mode==='create' ? 'Choose what to archive to continue.' : 'Choose an archive to continue.';
  if (unsupportedMulti) return 'Choose exactly one archive.';
  if (emptyExtract) return 'Select at least one entry to extract.';
  if (mode!=='open' && !destination) return mode==='create' ? 'Choose where to save the archive.' : 'Choose a destination folder.';
  return mode==='create' ? 'Ready. Your originals stay in place.' : mode==='extract' ? 'Ready. Files go into a new folder.' : 'Ready. Nothing is extracted.';
}
function updateRunState() { const busy=currentJobs.some(isActive); const unsupportedMulti=(mode==='open'||mode==='extract')&&selected.length>1; const emptyExtract=mode==='extract'&&selectiveExtraction&&selectedEntries.length===0; $('#run-job').disabled=!native || busy || inspectionInFlight || selected.length===0 || unsupportedMulti || emptyExtract || (mode!=='open'&&!destination); $('#run-job').title=unsupportedMulti?'Select one archive at a time':emptyExtract?'Select at least one entry to extract':inspectionInFlight?'Reading archive listing…':busy?'One archive job can run at a time':''; $('#run-hint').textContent=runHint(busy,unsupportedMulti,emptyExtract); $('#selection-count').textContent=selected.length?`${selected.length} ${selected.length===1?'item':'items'} selected`:''; $('#extract-selected').disabled=selectedEntries.length===0; }
function setMode(next) {
  mode=next; destination=null; $('#destination-path').textContent=NO_DESTINATION;
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
  $('#browse-folder').hidden=mode!=='create';
  $('#format-section').hidden=mode!=='create'; $('#destination-section').hidden=mode==='open';
  resetInspection();
  $('#destination-title').textContent=text.destTitle;
  $('#destination-hint').textContent=text.destHint;
  $('#destination-step').textContent=text.destStep;
  $('#run-label').textContent=text.run;
  showSelection([]); status('');
}
$$('.mode-tab').forEach(btn=>btn.addEventListener('click',()=>setMode(btn.dataset.mode)));
// Arrow keys move focus between tabs; Enter or Space selects, so browsing tabs never clears a selection.
$('.mode-tabs').addEventListener('keydown',e=>{const tabs=$$('.mode-tab');const i=tabs.indexOf(document.activeElement);if(i<0)return;const target={ArrowRight:(i+1)%tabs.length,ArrowLeft:(i+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1}[e.key];if(target===undefined)return;e.preventDefault();tabs[target].focus();});
$$('input[name="format"]').forEach(input=>input.addEventListener('change',()=>{$$('.format-option').forEach(el=>el.classList.toggle('selected',el.contains(input)&&input.checked));const hadDestination=Boolean(destination);destination=null;$('#destination-path').textContent=NO_DESTINATION;updateDestinationNote(hadDestination?'The format changed, so choose the save location again.':'');updateRunState();}));
$('#browse-inputs').addEventListener('click',async()=>{if(!native){status('Open this screen in the Bytepleat desktop app to browse files.',true);return;}try{const paths=await invoke('choose_inputs');showSelection(paths,true);}catch(e){status(String(e),true);}});
$('#browse-folder').addEventListener('click',async()=>{if(!native){status('Native folder access requires the desktop app.',true);return;}try{const path=await invoke('choose_input_directory');if(path)showSelection([path],true);}catch(e){status(String(e),true);}});
$('#drop-zone').addEventListener('click',e=>{if(e.target.closest('button'))return;$('#browse-inputs').click();});
$('#choose-destination').addEventListener('click',async()=>{if(!native){status('Native save and folder dialogs require the desktop app.',true);return;}try{const value=mode==='create'?await invoke('choose_output',{format:$$('input[name="format"]').find(i=>i.checked).value}):await invoke('choose_directory');if(value){destination=value;$('#destination-path').textContent=value;updateDestinationNote();updateRunState();}}catch(e){status(String(e),true);}});
$('#run-job').addEventListener('click',async()=>{
  if(!native){status('Native backend required. No archive operation was started.',true);return;}
  if((mode==='open'||mode==='extract')&&selected.length>1){status(multiArchiveMessage(selected.length),true);return;}
  if(mode==='extract'&&selectiveExtraction&&selectedEntries.length===0){status('Select at least one entry to extract. No archive operation was started.',true);updateRunState();return;}
  if(mode==='open'&&inspectionInFlight)return;
  try {
    if(mode==='open'){resetInspection();const isTar=/\.tar\.(zst|gz|lz4)$/i.test(selected[0]);const requestId=++inspectionRequest;const archivePath=selected[0];inspectionInFlight=true;updateRunState();status(isTar?'Reading TAR archive; listing fully decodes into private staging…':'Reading archive listing…');try{const listing=await invoke('inspect_archive',{path:archivePath});if(requestId!==inspectionRequest||mode!=='open'||selected.length!==1||selected[0]!==archivePath)return;renderArchiveListing(listing);status(`${listing.entries.length} of ${listing.total_entries} entries${listing.truncated?' (preview truncated)':''} · ${formatBytes(listing.total_bytes)} · listing only; contents have not been integrity-tested.`);}catch(error){if(requestId===inspectionRequest)status(String(error),true);}finally{if(requestId===inspectionRequest){inspectionInFlight=false;updateRunState();}}return;}
    const format=$$('input[name="format"]').find(i=>i.checked)?.value;
    const target=mode==='extract'?`${destination.replace(/[\\/]$/,'')}/${extractedName(selected[0])}`:destination;
    const request={action:mode==='create'?'create':'extract',inputs:selected.map(path=>path),destination:target,format:mode==='create'?format:null,selected_entries:mode==='extract'?[...selectedEntries]:[],max_output_bytes:1073741824};
    await invoke('start_job',{request});status(`${MODES[mode].run} started.`);await refreshJobs();
  } catch(error){status(String(error),true);}
});
function renderArchiveListing(listing){
  const section=$('#archive-inspection');section.hidden=false;const total=listing.total_entries??listing.entries.length;const shown=Math.min(listing.entries.length,5000);$('#inspection-summary').textContent=`Showing ${shown} of ${total} items · ${formatBytes(listing.total_bytes)}${listing.truncated?' · preview limited':''}`;
  const host=$('#entry-list');host.innerHTML=listing.entries.slice(0,shown).map((entry,index)=>`<label class="entry-row"><input type="checkbox" data-entry="${index}"><span class="entry-name">${esc(entry.name)}</span><span class="entry-size">${entry.is_dir?'Folder':formatBytes(entry.size)}</span></label>`).join('') || '<p class="selection-empty">No entries listed.</p>';
  if(total>shown){const note=document.createElement('p');note.className='entry-limit';note.textContent=`Showing ${shown} of ${total} entries. Only listed entries can be selected for extraction.`;host.append(note);}
  host.querySelectorAll('[data-entry]').forEach(box=>box.addEventListener('change',()=>{const entry=listing.entries[Number(box.dataset.entry)].name;if(box.checked){selectedEntries.push(entry);}else{selectedEntries=selectedEntries.filter(name=>name!==entry);}updateRunState();}));
  $('#extract-selected').onclick=()=>{if(!selected.length||selected.length!==1||selectedEntries.length===0)return;const entries=[...selectedEntries];const archive=selected[0];setMode('extract');showSelection([archive]);selectedEntries=entries;selectiveExtraction=true;updateRunState();status(`${entries.length} ${entries.length===1?'entry':'entries'} will be kept after the whole archive is decoded. Choose a destination folder, then extract.`);};
}
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
  if(job.state==='failed')return 'Your originals were not changed.';
  if(job.state==='cancelled')return 'Stopped before finishing. Your originals were not changed.';
  return '';
}
function jobActionButton(job,className){
  if(job.state==='running'||job.state==='queued')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel">Cancel</button>`;
  if(job.state==='cancelling')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="cancel" disabled>Stopping…</button>`;
  if(job.state==='completed'&&job.action!=='inspect')return `<button class="${className}" type="button" data-job="${esc(job.id)}" data-action="open">Open folder</button>`;
  return '';
}
function renderJobNow(job){
  const host=$('#job-now');
  if(!job){host.hidden=true;host.className='job-now';host.replaceChildren();return;}
  const label=JOB_LABEL[job.action]||job.action;
  const message=job.message&&job.message!==job.error?`<p class="job-message">${esc(job.message)}</p>`:'';
  const error=job.error?`<p class="job-error">${esc(job.error)}</p>`:'';
  const output=job.state==='completed'&&job.output?`<p class="job-output">${esc(job.output)}</p>`:'';
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
    const detail=job.error||job.message||STATE_LABEL[job.state]||job.state;
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
  try{if(btn.dataset.action==='cancel')await invoke('cancel_job',{id:btn.dataset.job});else await invoke('open_destination',{id:btn.dataset.job});await refreshJobs();}catch(e){status(String(e),true);}
});
async function refreshJobs(){if(!native)return;try{renderJobs(await invoke('jobs'));}catch(e){status(String(e),true);}}
async function receivePaths(action,paths,error){if(error){showSelection([]);status(error,true);return;}if(!paths?.length)return;setMode(action==='create'?'create':action==='extract'?'extract':'open');showSelection(paths);if(action!=='create'&&paths.length>1)status(multiArchiveMessage(paths.length),true);}
if(native){
  $('#native-notice').hidden=true;
  listen('selection',event=>receivePaths(event.payload.action,event.payload.paths,event.payload.error));
  listen('jobs-changed',refreshJobs);
  invoke('initial_selection').then(selection=>receivePaths(selection.action,selection.paths,selection.error)).catch(e=>status(String(e),true));
  const win=window.__TAURI__.webviewWindow.getCurrentWebviewWindow();
  win.onDragDropEvent(event=>{const payload=event.payload;if(payload.type==='over'||payload.type==='enter')$('#drop-zone').classList.add('drag-over');else{$('#drop-zone').classList.remove('drag-over');if(payload.type==='drop')showSelection(payload.paths,true);}});
  refreshJobs();pollHandle=setInterval(refreshJobs,250);
} else {
  $('#native-notice').hidden=false;
  $('#browse-inputs').disabled=true;$('#browse-folder').disabled=true;$('#choose-destination').disabled=true;
}
// Appearance cycles System, Light, Dark. System removes the override so the OS setting applies.
const THEMES=['system','light','dark'];
function currentTheme(){return document.documentElement.dataset.theme||'system';}
function applyTheme(theme,persist){
  const root=document.documentElement;
  if(theme==='system')delete root.dataset.theme;else root.dataset.theme=theme;
  const name=theme[0].toUpperCase()+theme.slice(1);
  $('#theme-label').textContent=name;
  $('#theme-toggle').setAttribute('aria-label',`Appearance: ${name}. Change appearance`);
  if(persist){try{if(theme==='system')localStorage.removeItem(THEME_KEY);else localStorage.setItem(THEME_KEY,theme);}catch{/* storage unavailable; the choice lasts for this session */}}
}
function toggleTheme(){applyTheme(THEMES[(THEMES.indexOf(currentTheme())+1)%THEMES.length],true);}
let savedTheme=null;try{savedTheme=localStorage.getItem(THEME_KEY);}catch{/* ignore */}
applyTheme(THEMES.includes(savedTheme)?savedTheme:'system',false);
$('#theme-toggle').addEventListener('click',toggleTheme);
setMode('create');
window.addEventListener('beforeunload',()=>{if(pollHandle)clearInterval(pollHandle);});

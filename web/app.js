const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="rig-token"]').content;
let state = null, pending = false, connected = false, previousPhase = '', lastHistory = 0;
const insertionLabels = {on_surface:'On surface',in_surface:'In surface',deep_into_surface:'Deep into surface'};
const phaseLabels = {idle:'IDLE',ready:'READY',taring:'TARING',starting:'STARTING',running:'RUNNING',stopped:'STOPPED',error:'CHECK RIG'};
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function controls() {
  const phase = state?.phase;
  $('tare').disabled = pending || !connected || !['idle','ready','error'].includes(phase);
  $('start').disabled = pending || !connected || phase !== 'ready' || !state?.tared;
  $('finish').disabled = pending || !connected || !['running','stopped'].includes(phase);
  $('torque-off').disabled = pending || !connected || ['taring','starting'].includes(phase);
  const speedAllowed = !pending && connected && !['taring','starting','stopped'].includes(phase);
  $('slower').disabled = !speedAllowed || state?.rpm <= 0.229;
  $('faster').disabled = !speedAllowed || state?.rpm >= 15.114;
  for (const id of ['material','angle','insertion','trial']) $(id).disabled = ['running','starting','stopped','taring'].includes(phase);
}
async function action(name, values={}) {
  pending = true; controls(); error('');
  try {
    const response = await fetch(`/api/${name}`, {method:'POST', headers:{'Content-Type':'application/json','X-Rig-Token':token},body:JSON.stringify(values)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Action failed');
    // Worker owns USB; leave time for it to take the command before polling.
    await new Promise(resolve => setTimeout(resolve,120));
    await poll();
  } catch (exc) { error(exc.message); }
  finally { pending = false; controls(); }
}
$('condition').addEventListener('submit', event => {
  event.preventDefault();
  if (!$('condition').reportValidity()) return;
  action('start', {material:$('material').value,needle_angle_deg:Number($('angle').value),
    engagement_level:$('insertion').value,trial_id:$('trial').value,notes:$('notes').value});
});
$('tare').addEventListener('click',()=>action('tare'));
$('torque-off').addEventListener('click',()=>action('torque_off'));
$('finish').addEventListener('click',()=>action('finish',{notes:$('notes').value,outcome:$('outcome').value}));
$('slower').addEventListener('click',()=>action('speed',{rpm:Math.max(0.229,state.rpm-0.5)}));
$('faster').addEventListener('click',()=>action('speed',{rpm:Math.min(15.114,state.rpm+0.5)}));
function chart(points, canvas=$('chart'), empty='Force trace appears when a test starts', positive=false, cursor=null) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = width*ratio; canvas.height = height*ratio;
  const ctx = canvas.getContext('2d'); ctx.scale(ratio,ratio);
  const left=40,right=8,top=10,bottom=20,w=width-left-right,h=height-top-bottom;
  let span=Math.max(0.05,...points.map(p=>Math.abs(p[1])))*1.15;
  const duration=Math.max(1,points.at(-1)?.[0] || 1);
  ctx.font='9px ui-monospace, monospace'; ctx.textAlign='right';
  const yOf=v=>positive?top+h-v/span*h:top+h/2-v/span*h/2;
  for (const v of (positive?[0,span/2,span]:[-span,0,span])) {
    const y=yOf(v);
    ctx.strokeStyle=v===0?'#c1d0c4':'#e8eee7';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();
    ctx.fillStyle='#879a8e';ctx.fillText(v.toFixed(2),left-8,y+3);
  }
  ctx.fillStyle='#879a8e';ctx.textAlign='left';ctx.fillText('0',left,height-3);
  ctx.textAlign='right';ctx.fillText(duration.toFixed(1),width-right,height-3);
  if (points.length>1) {
    ctx.strokeStyle='#236855';ctx.lineWidth=2;ctx.beginPath();
    points.forEach(([t,f],i)=>{const x=left+t/duration*w,y=yOf(f);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
    if (cursor!=null) {
      const x=left+cursor/duration*w;
      ctx.strokeStyle='#ad4936';ctx.lineWidth=1;ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+h);ctx.stroke();ctx.setLineDash([]);
      let best=points[0];for(const p of points)if(Math.abs(p[0]-cursor)<Math.abs(best[0]-cursor))best=p;
      ctx.fillStyle='#ad4936';ctx.beginPath();ctx.arc(left+best[0]/duration*w,yOf(best[1]),4,0,7);ctx.fill();
    }
  } else {
    ctx.fillStyle='#a0afa4';ctx.textAlign='center';ctx.fillText(empty,left+w/2,top+h/2-12);
  }
}
function cell(text, secondary='') {
  const td=document.createElement('td');td.textContent=text ?? '—';
  if(secondary){const small=document.createElement('small');small.textContent=secondary;td.append(small);}return td;
}
async function history() {
  const response=await fetch('/api/runs'); if(!response.ok)return;
  const rows=await response.json();$('log-count').textContent=`${rows.length} record${rows.length===1?'':'s'}`;
  fillRunSelect(rows);
  const body=$('runs');body.replaceChildren();
  if(!rows.length){const row=document.createElement('tr');const td=cell('Your completed tests will appear here.');td.colSpan=6;td.className='empty';row.append(td);body.append(row);return;}
  for(const run of rows){
    const row=document.createElement('tr');row.append(cell(run.trial || run.id,`${run.demo?'DEMO · ':''}${run.material}`),
      cell(run.angle==null?'—':`${run.angle}°`),cell(insertionLabels[run.insertion] || '—'),
      cell(run.peak==null?'—':`${run.peak.toFixed(3)} N`),
      cell((run.outcome || run.status || '').replaceAll('_',' '),(run.reason || '').replaceAll('_',' ')));
    const td=document.createElement('td'),plot=document.createElement('a'),link=document.createElement('a');plot.href='#run-viewer';plot.textContent='Plot';plot.addEventListener('click',()=>{$('run-select').value=run.id;showRun(run.id);});link.href=`/api/download/${encodeURIComponent(run.id)}`;link.textContent='Download ↗';td.append(plot,link);row.append(td);body.append(row);
  }
}
async function poll() {
  try {
    const response=await fetch('/api/state',{signal:AbortSignal.timeout(7000)});
    if(!response.ok)throw new Error('Server unavailable');
    state=await response.json();connected=true;
    $('connection').textContent=state.demo?'Demo · simulated rig':state.tared?`Sensor connected · ${state.uno_port || ''}`:state.uno_port?`Uno detected · ${state.uno_port}`:(state.uno_port_error || 'Looking for Uno…');
    $('dot').classList.toggle('active',state.tared);
    $('force').textContent=state.force_N==null?'—':state.force_N.toFixed(3);
    $('peak').textContent=`${state.peak_N.toFixed(3)} N`;
    $('elapsed').textContent=`${state.elapsed_s.toFixed(1)} s`;
    $('speed').textContent=`${state.rpm.toFixed(3)} rpm`;
    $('actual').textContent=state.actual_rpm==null?'— rpm':`${Math.abs(state.actual_rpm).toFixed(3)} rpm`;
    $('phase').textContent=phaseLabels[state.phase] || state.phase.toUpperCase();
    $('phase').classList.toggle('running',state.phase==='running');
    $('message').textContent=state.message;
    $('limits').textContent=`${state.limits.max_abs_sensor_force_N == null ? 'No force stop' : state.limits.max_abs_sensor_force_N + ' N'} · ${state.limits.max_motor_path_deg == null ? 'No travel stop' : state.limits.max_motor_path_deg + '°'} · ${state.limits.duration_s} s`;
    $('demo-label').textContent=state.demo?' / SIMULATED DEMO':'';
    chart(state.trace);
    if(previousPhase!==state.phase || Date.now()-lastHistory>3000){await history();lastHistory=Date.now();}
    previousPhase=state.phase;
  } catch(exc){connected=false;$('connection').textContent='Server connection lost';$('dot').classList.remove('active');error('Connection lost. Active tests stop if the page cannot reach the server.');}
  controls();
}
let viewed = null, cursorRow = null, tableBuilt = false;
function fillRunSelect(rows) {
  const select = $('run-select'), current = select.value, sig = rows.map(r => r.id).join();
  if (select.dataset.sig === sig) return;
  select.dataset.sig = sig; select.replaceChildren(new Option('Select a run…', ''));
  for (const r of rows) select.append(new Option(`${r.demo ? 'DEMO · ' : ''}${r.material || '—'} · ${r.angle == null ? '—' : r.angle + '°'} · trial ${r.trial || r.id}${r.peak == null ? '' : ` · ${r.peak.toFixed(2)} N`}`, r.id));
  select.value = current;
}
function drawViewer() {
  if (!viewed) return;
  const t = cursorRow == null ? null : viewed.table[cursorRow][0];
  chart(viewed.force, $('v-force'), 'No force samples in this run', false, t);
  chart(viewed.speed, $('v-speed'), 'No motor telemetry in this run', true, t);
}
async function showRun(id) {
  $('viewer-body').hidden = !id; viewed = null; cursorRow = null; tableBuilt = false;
  $('v-table').replaceChildren(); $('v-readout').textContent = 'Hover the plot or click a table row to read exact values.';
  if (!id) return;
  try {
    const response = await fetch(`/api/run/${encodeURIComponent(id)}`);
    const run = await response.json(); if (!response.ok) throw new Error(run.error || 'Could not load run');
    if ($('run-select').value !== id) return;
    viewed = run;
    $('v-peak').textContent = `${run.peak_N.toFixed(3)} N @ ${run.peak_t_s.toFixed(2)} s`;
    $('v-mean').textContent = `${run.mean_abs_N.toFixed(3)} N`;
    $('v-duration').textContent = `${run.duration_s.toFixed(2)} s`;
    $('v-samples').textContent = run.samples;
    $('v-rate').textContent = run.rate_hz == null ? '—' : `${run.rate_hz.toFixed(1)} Hz`;
    const lag = run.host_duration_s && run.duration_s && run.host_duration_s > run.duration_s * 1.1;
    $('v-info').textContent = [run.material, run.angle == null ? null : `${run.angle}°`, run.insertion && insertionLabels[run.insertion], run.reason && run.reason.replaceAll('_',' '), run.notes]
      .filter(Boolean).join(' · ') + (lag ? ` · WARNING: PC clock spans ${run.host_duration_s.toFixed(1)} s but the sensor only ${run.duration_s.toFixed(1)} s; the log was truncated by a serial backlog (older runs).` : '');
    drawViewer();
    if (!$('v-table-wrap').hidden) buildTable();
  } catch (exc) { error(exc.message); }
}
const fmt = (v, d) => v == null ? '—' : v.toFixed(d);
function buildTable() {
  if (!viewed || tableBuilt) return; tableBuilt = true;
  const body = $('v-table'), frag = document.createDocumentFragment();
  viewed.table.forEach((r, i) => {
    const tr = document.createElement('tr'); tr.dataset.i = i;
    [fmt(r[0],3), r[1] == null ? '—' : r[1], r[2] == null ? '—' : r[2], fmt(r[3],4), fmt(r[4],2), fmt(r[5],1)].forEach(text => { const td = document.createElement('td'); td.textContent = text; tr.append(td); });
    frag.append(tr);
  });
  body.append(frag);
}
function selectRow(i, scroll) {
  if (!viewed || !viewed.table.length) return;
  cursorRow = i; const r = viewed.table[i];
  $('v-readout').textContent = `t = ${r[0].toFixed(3)} s · force = ${fmt(r[3],4)} N · motor speed = ${fmt(r[4],2)} rpm · sample ${r[1] ?? '—'}`;
  const body = $('v-table');
  body.querySelector('tr.sel')?.classList.remove('sel');
  const tr = body.children[i];
  if (tr) { tr.classList.add('sel'); if (scroll) { const wrap = $('v-table-wrap'); wrap.scrollTop = tr.offsetTop - wrap.clientHeight / 2; } }
  drawViewer();
}
function nearestRow(t) {
  const tab = viewed.table; let lo = 0, hi = tab.length - 1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (tab[mid][0] < t) lo = mid + 1; else hi = mid; }
  return lo > 0 && Math.abs(tab[lo-1][0] - t) < Math.abs(tab[lo][0] - t) ? lo - 1 : lo;
}
for (const id of ['v-force', 'v-speed']) {
  const canvas = $(id); canvas.classList.add('hov');
  canvas.addEventListener('mousemove', event => {
    if (!viewed || !viewed.table.length) return;
    const rect = canvas.getBoundingClientRect(), left = 40, right = 8, w = rect.width - left - right;
    const duration = Math.max(1, viewed.force.at(-1)?.[0] || 1);
    const t = Math.min(duration, Math.max(0, (event.clientX - rect.left - left) / w * duration));
    selectRow(nearestRow(t), !$('v-table-wrap').hidden);
  });
}
$('v-toggle').addEventListener('click', () => {
  const wrap = $('v-table-wrap'); wrap.hidden = !wrap.hidden;
  $('v-toggle').textContent = wrap.hidden ? 'Show data table' : 'Hide data table';
  if (!wrap.hidden) { buildTable(); if (cursorRow != null) selectRow(cursorRow, true); }
});
$('v-table').addEventListener('click', event => { const tr = event.target.closest('tr'); if (tr) selectRow(Number(tr.dataset.i), false); });
$('run-select').addEventListener('change', event => showRun(event.target.value));
window.addEventListener('resize',()=>{chart(state?.trace || []);drawViewer();});
async function cycle(){await poll();setTimeout(cycle,250);}cycle();

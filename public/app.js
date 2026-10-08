const $ = s => document.querySelector(s);
const nf = (n, digits = 1) => Number(n).toLocaleString('vi-VN', {maximumFractionDigits: digits});
const money = n => nf(n, 0) + ' ₫';
const day = d => d.split('-').reverse().join('/');
const escapeHTML = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function localNow() { const parts = Object.fromEntries(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value])); return {day:`${parts.year}-${parts.month}-${parts.day}`,time:`${parts.hour}:${parts.minute}`}; }
let state = {vehicles:[],logs:[],prices:[],fuel_types:[],sync:{}}, selected = localStorage.getItem('vehicle') || '';
let editing = null, activeQuote = null, quoteGeneration = 0, saving = false;
async function request(path, data) {
  const res = await fetch('/api/' + path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body = await res.json(); if (!res.ok) throw new Error(body.error || 'Không thể tải dữ liệu.'); return body;
}
async function api(path,data) {state=await request(path,data);}
function fuelName(id){return state.fuel_types.find(f=>f.id===id)?.name||id||'';}
function priceSource(value){if(value==='manual')return 'Nhập thủ công';try{return new URL(value).hostname;}catch{return 'Nguồn giá';}}
function activeVehicle(){return state.vehicles.find(v=>v.id===selected);}
function distanceLabel(l) {return l.is_baseline ? '<span class="badge">Mốc bắt đầu</span>' : l.odometer_km === null ? '<span class="muted">Chưa có ODO</span>' : l.distance_km === null ? '<span class="badge">Mốc ODO đầu</span>' : `${nf(l.distance_km)} km<small class="cell-sub">Từ ${day(l.distance_from_date)}</small>`;}
function actionButtons(l){return `<button data-edit="${l.id}" aria-label="Sửa lần đổ ${day(l.refueled_on)}">Sửa</button><button data-delete="${l.id}" aria-label="Xóa lần đổ ${day(l.refueled_on)}">Xóa</button>`;}
function render() {
  if(!state.vehicles.some(v=>v.id===selected)) selected=state.vehicles[0]?.id||'';
  localStorage.setItem('vehicle',selected);
  $('#vehicle').innerHTML=state.vehicles.length?state.vehicles.map(v=>`<option value="${v.id}" ${v.id===selected?'selected':''}>${escapeHTML(v.name)}${v.license_plate?' · '+escapeHTML(v.license_plate):''}</option>`).join(''):'<option>Thêm xe để bắt đầu</option>';
  $('#edit-vehicle').disabled=!selected;
  const v=activeVehicle(), logs=state.logs.filter(l=>l.vehicle_id===selected);
  $('#vehicle-fuel').textContent=v?`${fuelName(v.default_fuel_type_id)} · ${v.city} · Vùng ${v.price_zone}`:'E10 RON 95-III · Đà Nẵng';
  const now=localNow(), cutoff=`${now.day}T${now.time}+07:00`;
  const applicable=state.prices.filter(p=>p.fuel_type_id===(v?.default_fuel_type_id||'F1')&&p.price_zone===(v?.price_zone||1)&&p.effective_at<=cutoff);
  const price=applicable[0];
  $('#current-price').textContent=price?money(price.unit_price_vnd_per_liter)+'/lít':'Chưa có giá';
  $('#price-date').textContent=price?'Từ '+price.effective_at.slice(11,16)+' · '+day(price.effective_at.slice(0,10)):'';
  $('#sync-status').textContent=state.sync.price_sync_error||(state.sync.price_sync_at?'Đã kiểm tra '+new Date(state.sync.price_sync_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Đang chờ cập nhật giá từ Petrolimex');
  $('#cost').textContent=money(logs.reduce((s,l)=>s+l.total_cost_vnd,0));
  $('#distance').textContent=nf(logs.reduce((s,l)=>s+(l.distance_km||0),0))+' km';
  $('#volume').textContent=nf(logs.reduce((s,l)=>s+Number(l.volume_liters),0),2)+' lít';
  $('#count').textContent=logs.length;
  $('#period').textContent=logs.length?day(logs[0].refueled_on)+' – '+day(logs.at(-1).refueled_on):'Chưa có dữ liệu';
  $('#empty').hidden=!!logs.length;
  $('#vehicle-note').textContent=`Dung tích bình ${v?.tank_capacity_liters||4} lít. Số lít đổ thêm không phải lượng xăng còn trong bình.`;
  $('#rows').innerHTML=[...logs].reverse().map(l=>`<tr><td>${day(l.refueled_on)}${l.refueled_time?`<small class="cell-sub">${l.refueled_time}</small>`:''}<small class="cell-sub">${escapeHTML(fuelName(l.fuel_type_id))}</small>${l.notes?`<small class="cell-sub">${escapeHTML(l.notes)}</small>`:''}</td><td>${l.odometer_km===null?'—':nf(l.odometer_km)}</td><td>${money(l.total_cost_vnd)}</td><td>${nf(l.unit_price_vnd_per_liter,0)}</td><td>${nf(l.volume_liters,2)}</td><td>${distanceLabel(l)}</td><td>${actionButtons(l)}</td></tr>`).join('');
  $('#cards').innerHTML=[...logs].reverse().map(l=>`<article class="log-card"><div class="card-top"><span>${day(l.refueled_on)} <small>${l.refueled_time||''}</small></span><strong>${money(l.total_cost_vnd)}</strong></div><div class="card-metrics"><div><small>Đổ thêm</small><b>${nf(l.volume_liters,2)} lít</b></div><div><small>ODO</small><b>${l.odometer_km===null?'—':nf(l.odometer_km)} km</b></div><div><small>Quãng đường</small><b>${distanceLabel(l)}</b></div></div>${l.notes?`<p>${escapeHTML(l.notes)}</p>`:''}<div class="card-bottom"><small>${escapeHTML(fuelName(l.fuel_type_id))} / ${money(l.unit_price_vnd_per_liter)}/lít</small><div>${actionButtons(l)}</div></div></article>`).join('');
  renderPrices();
}
function populateFuels(){document.querySelectorAll('.fuel-options').forEach(s=>{const old=s.value;s.innerHTML=state.fuel_types.map(f=>`<option value="${f.id}">${escapeHTML(f.name)}</option>`).join('');if(state.fuel_types.some(f=>f.id===old))s.value=old;});}
$('#vehicle').onchange=e=>{selected=e.target.value;render();};
function openVehicle(edit=false){const f=$('#vehicle-form');f.reset();f.elements.id.value='';populateFuels();if(edit){const v=activeVehicle();for(const[k,value]of Object.entries(v))if(f.elements.namedItem(k))f.elements.namedItem(k).value=value??'';}$('#vehicle-title').textContent=edit?'Cài đặt xe':'Thêm xe';$('#vehicle-form .form-error').textContent='';$('#vehicle-dialog').showModal();}
$('#add-vehicle').onclick=()=>openVehicle();$('#edit-vehicle').onclick=()=>openVehicle(true);
document.querySelectorAll('.close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
function openLog(log) {
  if(!selected)return openVehicle();editing=log||null;
  const f=$('#log-form');populateFuels();f.reset();f.elements.id.value='';f.elements.odo_source.value='manual';
  const now=localNow();f.elements.refueled_on.value=now.day;f.elements.refueled_time.value=now.time;
  if(log){for(const[k,v]of Object.entries(log))if(f.elements.namedItem(k))f.elements.namedItem(k).value=v??'';}else f.elements.fuel_type_id.value=activeVehicle().default_fuel_type_id;
  $('#form-title').textContent=log?'Sửa lần đổ':'Thêm lần đổ';$('#log-vehicle').textContent=activeVehicle().name;
  $('#log-form .form-error').textContent='';$('#log-dialog').showModal();updateQuote();updateDistance();
}
$('#add-log').onclick=()=>openLog();
function preservedQuote(){const f=$('#log-form').elements;return editing&&editing.vehicle_id===selected&&editing.refueled_on===f.refueled_on.value&&(editing.refueled_time||'')===f.refueled_time.value&&editing.fuel_type_id===f.fuel_type_id.value;}
async function updateQuote(){
  const generation=++quoteGeneration,f=$('#log-form').elements;activeQuote=null;$('#quote-status').textContent='Đang tra giá…';updateLiters();
  if(preservedQuote()){activeQuote={price:{unit_price_vnd_per_liter:Number(editing.unit_price_vnd_per_liter)},needs_time:false,message:'Đơn giá đã lưu của lần đổ này.'};updateLiters();return;}
  if(!f.refueled_on.value)return;
  try{const q=await request('quote?'+new URLSearchParams({vehicle_id:selected,refueled_on:f.refueled_on.value,refueled_time:f.refueled_time.value,fuel_type_id:f.fuel_type_id.value}));if(generation!==quoteGeneration)return;activeQuote=q;updateLiters();}catch(e){if(generation===quoteGeneration){$('#quote-status').textContent=e.message;$('#save-log').disabled=true;}}
}
function updateLiters(){
  const amount=Number($('#log-form').elements.total_cost_vnd.value),p=activeQuote?.price;
  $('#liters-preview').textContent=p&&amount>0&&!activeQuote.needs_time?nf(amount/p.unit_price_vnd_per_liter,2)+' lít':'— lít';
  $('#quote-price').textContent=p?money(p.unit_price_vnd_per_liter)+'/lít':'Chưa có đơn giá';
  if(activeQuote)$('#quote-status').textContent=activeQuote.message||(p?`Giá ${priceSource(p.source_url)} · vùng ${p.price_zone} · từ ${p.effective_at.slice(11,16)} ${day(p.effective_at.slice(0,10))}`:'');
  $('#save-log').disabled=saving||!p||activeQuote.needs_time;
}
function updateDistance(){
  const f=$('#log-form').elements;
  if(f.odometer_km.value===''){$('#distance-preview').textContent='Có thể lưu trước, bổ sung ODO sau để tính quãng đường.';return;}
  const odo=Number(f.odometer_km.value), clock=f.refueled_time.value||'23:59';
  const earlier=state.logs.filter(l=>l.vehicle_id===selected&&l.id!==f.id.value&&l.odometer_km!==null&&(l.refueled_on<f.refueled_on.value||(l.refueled_on===f.refueled_on.value&&((l.refueled_time||'23:59')<clock||((l.refueled_time||'23:59')===clock&&l.odometer_km<=odo)))));
  $('#distance-preview').textContent=earlier.length?`${nf(odo-earlier.at(-1).odometer_km)} km từ mốc ODO ngày ${day(earlier.at(-1).refueled_on)}.`:'Mốc ODO đầu tiên — không tính quãng đường trước đó.';
}
$('#log-form').oninput=e=>{if(e.target.name==='refueled_on'){e.target.form.elements.refueled_time.value='';updateQuote();}if(e.target.name==='refueled_time')updateQuote();if(e.target.name==='odometer_km')e.target.form.elements.odo_source.value='manual';updateLiters();updateDistance();};
$('#log-form').onchange=e=>{if(e.target.name==='fuel_type_id')updateQuote();};
document.querySelectorAll('[data-amount]').forEach(b=>b.onclick=()=>{$('#log-form').elements.total_cost_vnd.value=b.dataset.amount;updateLiters();});
async function submitForm(event,endpoint,extra,dialog){
  event.preventDefault();const form=event.target,button=form.querySelector('[type=submit]');button.disabled=true;saving=true;
  try{const values=Object.fromEntries(new FormData(form));await api(endpoint,{...values,...extra});if(endpoint==='vehicles'&&!values.id)selected=state.vehicles.at(-1).id;render();if(dialog)$(dialog).close();if(endpoint==='prices'){$('#prices-status').textContent='Đã lưu giá theo thời điểm áp dụng.';if($('#log-dialog').open)await updateQuote();}$('#notice').textContent='Đã lưu dữ liệu.';form.querySelector('.form-error').textContent='';}
  catch(e){form.querySelector('.form-error').textContent=e.message;}finally{saving=false;button.disabled=false;if($('#log-dialog').open)updateLiters();}
}
$('#vehicle-form').onsubmit=e=>submitForm(e,'vehicles',{},'#vehicle-dialog');
$('#log-form').onsubmit=e=>submitForm(e,'logs',{vehicle_id:selected},'#log-dialog');
$('#price-form').onsubmit=e=>submitForm(e,'prices',{},null);
async function logAction(e){const edit=e.target.closest('[data-edit]'),del=e.target.closest('[data-delete]');if(edit)openLog(state.logs.find(l=>l.id===edit.dataset.edit));if(del&&confirm('Xóa lần đổ này? Mốc bắt đầu và quãng đường sẽ được tính lại.')){try{await api('logs/delete',{id:del.dataset.delete});render();$('#notice').textContent='Đã xóa lần đổ.';}catch(e){$('#notice').textContent=e.message;}}}
$('#rows').onclick=logAction;$('#cards').onclick=logAction;
$('#sample').onclick=async()=>{$('#sample').disabled=true;try{await api('sample',{});selected=state.vehicles.at(-1).id;render();$('#notice').textContent='Đã thêm 14 lần đổ từ ảnh. Giá mẫu chỉ thuộc các lần đổ này.';}catch(e){$('#notice').textContent=e.message;}finally{$('#sample').disabled=false;}};
function renderPrices(){const v=activeVehicle();const fuelId=(($('#log-dialog').open?$('#log-form').elements.fuel_type_id.value:v?.default_fuel_type_id)||'F1');const rows=state.prices.filter(p=>p.fuel_type_id===fuelId&&p.price_zone===(v?.price_zone||1));$('#price-list').innerHTML=rows.length?rows.map(p=>`<div class="price-item"><div><b>${money(p.unit_price_vnd_per_liter)}/lít</b><small>${escapeHTML(fuelName(p.fuel_type_id))} · Vùng ${p.price_zone}</small></div><div><span>${day(p.effective_at.slice(0,10))} · ${p.effective_at.slice(11,16)}</span><small>${escapeHTML(priceSource(p.source_url))}</small></div></div>`).join(''):'<p>Chưa có giá đã lưu cho loại xăng và vùng này.</p>';}
function openPrices(){populateFuels();const f=$('#price-form'),v=activeVehicle(),now=localNow();f.elements.fuel_type_id.value=($('#log-dialog').open?$('#log-form').elements.fuel_type_id.value:v?.default_fuel_type_id)||'F1';f.elements.price_zone.value=v?.price_zone||1;f.elements.effective_at.value=($('#log-dialog').open?$('#log-form').elements.refueled_on.value:now.day)+'T00:00';$('#prices-status').textContent=state.sync.price_sync_error||'';renderPrices();$('#prices-dialog').showModal();if($('#log-dialog').open&&!activeQuote?.price)$('#manual-price').open=true;}
$('#prices-open').onclick=openPrices;$('#log-prices').onclick=openPrices;
$('#sync-prices').onclick=async()=>{const b=$('#sync-prices');b.disabled=true;$('#prices-status').textContent='Đang đọc bảng giá Petrolimex…';try{await api('prices/sync',{});render();$('#prices-status').textContent='Đã cập nhật giá từ bảng thanh bên Petrolimex.';if($('#log-dialog').open)await updateQuote();}catch(e){$('#prices-status').textContent=e.message;}finally{b.disabled=false;}};
$('#export').onclick=()=>{const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));a.href=url;a.download='fuel-data.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
api('state').then(()=>{populateFuels();render();}).catch(e=>{$('#notice').textContent='Không thể tải dữ liệu: '+e.message;});
setInterval(async()=>{if(document.hidden||document.querySelector('dialog[open]'))return;try{await api('state');render();}catch{}},30000);

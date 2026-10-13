const $ = s => document.querySelector(s);
const nf = (n, digits = 1) => Number(n).toLocaleString('vi-VN', {maximumFractionDigits: digits});
const money = n => nf(n, 0) + ' ₫';
const day = d => d.split('-').reverse().join('/');
const escapeHTML = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function localNow() { const parts = Object.fromEntries(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value])); return {day:`${parts.year}-${parts.month}-${parts.day}`,time:`${parts.hour}:${parts.minute}`}; }
let state = {vehicles:[],logs:[],prices:[],fuel_types:[],sync:{}}, selected = localStorage.getItem('vehicle') || '';
let editing = null, activeQuote = null, quoteGeneration = 0, saving = false;
let authConfig=null,authMode='login',session=readSession(),quoteWasChanged=false;
function readSession(){try{return JSON.parse(localStorage.getItem('fuel-auth-session')||'null');}catch{return null;}}
function saveSession(value){session=value?.access_token?{...value,expires_at:value.expires_at||Math.floor(Date.now()/1000)+(value.expires_in||3600)}:null;if(session)localStorage.setItem('fuel-auth-session',JSON.stringify(session));else localStorage.removeItem('fuel-auth-session');}
function viParse(value,kind='decimal'){
  const raw=String(value??'').trim().replace(/\s/g,'');if(!raw)return '';
  const parts=raw.split(',');if(parts.length>2||(parts.length===2&&kind==='integer')||(parts.length===2&&!/^\d*$/.test(parts[1])))return NaN;
  const whole=parts[0],validWhole=whole.includes('.')?/^[+-]?\d{1,3}(?:\.\d{3})+$/.test(whole):/^[+-]?\d+$/.test(whole);if(!validWhole)return NaN;
  const normalized=whole.replace(/\./g,'')+(parts.length===2?'.'+parts[1]:'');const n=Number(normalized);
  return Number.isFinite(n)&&(kind!=='integer'||Number.isInteger(n))?n:NaN;
}
function viFormat(n,kind='decimal'){
  if(n===''||n===null||n===undefined)return '';const digits=kind==='integer'||kind==='money'?0:kind==='odo'?1:kind==='liters'?3:3;
  return Number(n).toLocaleString('vi-VN',{maximumFractionDigits:digits,minimumFractionDigits:0});
}
function inputValue(input){return viParse(input.value,input.dataset.number||'decimal');}
function formValues(form){const values=Object.fromEntries(new FormData(form));for(const input of form.querySelectorAll('[data-number]')){if(!input.value.trim())continue;const value=inputValue(input);if(!Number.isFinite(value))throw new Error(`Kiểm tra lại giá trị “${input.name}” theo định dạng 1.234,5.`);values[input.name]=String(value);}return values;}
async function request(path, data) {
  const send=()=>{const headers={};if(data!==undefined)headers['Content-Type']='application/json';if(session?.access_token)headers.Authorization='Bearer '+session.access_token;return fetch('/api/'+path,data===undefined?{headers}:{method:'POST',headers,body:JSON.stringify(data)});};
  let res=await send();
  if(res.status===401&&session?.refresh_token&&await refreshSession())res=await send();
  const body=await res.json();if(!res.ok)throw new Error(body.error||'Không thể tải dữ liệu.');return body;
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
function openVehicle(edit=false){const f=$('#vehicle-form');f.reset();f.elements.id.value='';populateFuels();if(edit){const v=activeVehicle();for(const[k,value]of Object.entries(v))if(f.elements.namedItem(k))f.elements.namedItem(k).value=value??'';}for(const input of f.querySelectorAll('[data-number]')){const n=viParse(input.value,input.dataset.number);if(Number.isFinite(n))input.value=viFormat(n,input.dataset.number);}$('#vehicle-title').textContent=edit?'Cài đặt xe':'Thêm xe';$('#vehicle-form .form-error').textContent='';$('#vehicle-dialog').showModal();}
$('#add-vehicle').onclick=()=>openVehicle();$('#edit-vehicle').onclick=()=>openVehicle(true);
document.querySelectorAll('.close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
function openLog(log) {
  if(!selected)return openVehicle();editing=log||null;
  const f=$('#log-form');populateFuels();f.reset();f.elements.id.value='';f.elements.odo_source.value='manual';
  const now=localNow();f.elements.refueled_on.value=now.day;f.elements.refueled_time.value=now.time;
  if(log){for(const[k,v]of Object.entries(log))if(f.elements.namedItem(k))f.elements.namedItem(k).value=v??'';f.elements.unit_price_vnd_per_liter.value=viFormat(log.unit_price_vnd_per_liter,'integer');f.elements.price_choice.value='preserve';$('#edit-price-label').hidden=false;$('#apply-quote').hidden=false;quoteWasChanged=false;}else{f.elements.fuel_type_id.value=activeVehicle().default_fuel_type_id;f.elements.price_choice.value='auto';$('#edit-price-label').hidden=true;$('#apply-quote').hidden=true;}
  for(const input of f.querySelectorAll('[data-number]')){const n=viParse(input.value,input.dataset.number);if(Number.isFinite(n))input.value=viFormat(n,input.dataset.number);}
  $('#form-title').textContent=log?'Sửa lần đổ':'Thêm lần đổ';$('#log-vehicle').textContent=activeVehicle().name;
  $('#log-form .form-error').textContent='';$('#log-dialog').showModal();updateQuote();updateDistance();
}
$('#add-log').onclick=()=>openLog();
async function updateQuote(){
  const generation=++quoteGeneration,f=$('#log-form').elements;activeQuote=null;$('#quote-status').textContent='Đang tra giá…';updateLiters();
  if(!f.refueled_on.value)return;
  try{const q=await request('quote?'+new URLSearchParams({vehicle_id:selected,refueled_on:f.refueled_on.value,refueled_time:f.refueled_time.value,fuel_type_id:f.fuel_type_id.value}));if(generation!==quoteGeneration)return;activeQuote=q;if(editing&&f.price_choice.value==='preserve')activeQuote.message=`Giữ nguyên đơn giá đã lưu ${money(viParse(f.unit_price_vnd_per_liter.value,'integer'))}/lít. Giá tra được dưới đây chỉ để tham khảo; bấm “Dùng giá tham khảo” nếu muốn áp dụng.`;updateLiters();}catch(e){if(generation===quoteGeneration){activeQuote={price:null,needs_time:false,message:e.message};$('#quote-status').textContent=e.message;updateLiters();}}
}
function updateLiters(){
  const f=$('#log-form').elements,amount=viParse(f.total_cost_vnd.value,'integer'),manualPrice=editing?viParse(f.unit_price_vnd_per_liter.value,'integer'):null,p=activeQuote?.price;
  const price=editing?manualPrice:p?.unit_price_vnd_per_liter;
  $('#liters-preview').textContent=Number.isFinite(amount)&&amount>0&&Number.isFinite(Number(price))&&Number(price)>0&&(!activeQuote?.needs_time||editing)?nf(amount/Number(price),2)+' lít':'— lít';
  $('#quote-price').textContent=p?money(p.unit_price_vnd_per_liter)+'/lít':'Chưa có đơn giá';
  if(activeQuote)$('#quote-status').textContent=activeQuote.message||(p?`Giá ${priceSource(p.source_url)} · vùng ${p.price_zone} · từ ${p.effective_at.slice(11,16)} ${day(p.effective_at.slice(0,10))}`:'');
  $('#save-log').disabled=saving||(!editing&&(!p||activeQuote?.needs_time))||(editing&&(!Number.isFinite(Number(price))||Number(price)<=0))||(editing&&f.price_choice.value==='reference'&&(!p||activeQuote?.needs_time));
}
function updateDistance(){
  const f=$('#log-form').elements;
  if(f.odometer_km.value===''){$('#distance-preview').textContent='Có thể lưu trước, bổ sung ODO sau để tính quãng đường.';return;}
  const odo=viParse(f.odometer_km.value,'decimal'),clock=f.refueled_time.value||'23:59';if(!Number.isFinite(odo)){$('#distance-preview').textContent='Nhập ODO theo định dạng 17.054,5 km.';return;}
  const earlier=state.logs.filter(l=>l.vehicle_id===selected&&l.id!==f.id.value&&l.odometer_km!==null&&(l.refueled_on<f.refueled_on.value||(l.refueled_on===f.refueled_on.value&&((l.refueled_time||'23:59')<clock||((l.refueled_time||'23:59')===clock&&l.odometer_km<=odo)))));
  $('#distance-preview').textContent=earlier.length?`${nf(odo-earlier.at(-1).odometer_km)} km từ mốc ODO ngày ${day(earlier.at(-1).refueled_on)}.`:'Mốc ODO đầu tiên — không tính quãng đường trước đó.';
}
$('#log-form').oninput=e=>{if(e.target.name==='refueled_on'){e.target.form.elements.refueled_time.value='';updateQuote();}if(e.target.name==='refueled_time')updateQuote();if(e.target.name==='fuel_type_id')updateQuote();if(e.target.name==='odometer_km')e.target.form.elements.odo_source.value='manual';if(e.target.name==='unit_price_vnd_per_liter'){quoteWasChanged=true;e.target.form.elements.price_choice.value='custom';}updateLiters();updateDistance();};
document.querySelectorAll('[data-number]').forEach(input=>{input.addEventListener('focus',()=>{const value=inputValue(input);if(Number.isFinite(value))input.value=String(value).replace('.',',');});input.addEventListener('blur',()=>{const value=inputValue(input);if(Number.isFinite(value))input.value=viFormat(value,input.dataset.number);});});
$('#log-form').onchange=e=>{if(e.target.name==='fuel_type_id')updateQuote();};
document.querySelectorAll('[data-amount]').forEach(b=>b.onclick=()=>{$('#log-form').elements.total_cost_vnd.value=viFormat(b.dataset.amount,'integer');updateLiters();});
async function submitForm(event,endpoint,extra,dialog){
  event.preventDefault();const form=event.target,button=form.querySelector('[type=submit]');button.disabled=true;saving=true;
  try{const values=formValues(form);await api(endpoint,{...values,...extra});if(endpoint==='vehicles'&&!values.id)selected=state.vehicles.at(-1).id;render();if(dialog)$(dialog).close();if(endpoint==='prices'){$('#prices-status').textContent='Đã lưu giá theo thời điểm áp dụng.';if($('#log-dialog').open)await updateQuote();}$('#notice').textContent='Đã lưu dữ liệu.';form.querySelector('.form-error').textContent='';}
  catch(e){form.querySelector('.form-error').textContent=e.message;}finally{saving=false;button.disabled=false;if($('#log-dialog').open)updateLiters();}
}
$('#vehicle-form').onsubmit=e=>submitForm(e,'vehicles',{},'#vehicle-dialog');
$('#log-form').onsubmit=e=>submitForm(e,'logs',{vehicle_id:selected},'#log-dialog');
$('#apply-quote').onclick=()=>{if(!activeQuote?.price||activeQuote.needs_time){$('#quote-status').textContent=activeQuote?.message||'Chưa có giá tham khảo hợp lệ.';return;}const f=$('#log-form').elements;f.unit_price_vnd_per_liter.value=viFormat(activeQuote.price.unit_price_vnd_per_liter,'integer');f.price_choice.value='reference';quoteWasChanged=true;updateLiters();};
$('#price-form').onsubmit=e=>submitForm(e,'prices',{},null);
async function logAction(e){const edit=e.target.closest('[data-edit]'),del=e.target.closest('[data-delete]');if(edit)openLog(state.logs.find(l=>l.id===edit.dataset.edit));if(del&&confirm('Xóa lần đổ này? Mốc bắt đầu và quãng đường sẽ được tính lại.')){try{await api('logs/delete',{id:del.dataset.delete});render();$('#notice').textContent='Đã xóa lần đổ.';}catch(e){$('#notice').textContent=e.message;}}}
$('#rows').onclick=logAction;$('#cards').onclick=logAction;
$('#sample').onclick=async()=>{$('#sample').disabled=true;try{await api('sample',{});selected=state.vehicles.at(-1).id;render();$('#notice').textContent='Đã thêm 14 lần đổ từ ảnh. Giá mẫu chỉ thuộc các lần đổ này.';}catch(e){$('#notice').textContent=e.message;}finally{$('#sample').disabled=false;}};
let showOlderPrices=false;
function renderPrices(){const v=activeVehicle(),fuelId=(($('#log-dialog').open?$('#log-form').elements.fuel_type_id.value:v?.default_fuel_type_id)||'F1'),rows=state.prices.filter(p=>p.fuel_type_id===fuelId&&p.price_zone===(v?.price_zone||1)),year=localNow().day.slice(0,4),start=year+'-01-01',thisYear=rows.filter(p=>p.effective_at.slice(0,10)>=start),previous=rows.find(p=>p.effective_at.slice(0,10)<start),visible=showOlderPrices?rows:[...thisYear,...(previous?[previous]:[])];
  $('#price-history-heading').textContent=`Các mốc giá đã lưu · ${showOlderPrices?'toàn bộ lịch sử':`01/01/${year} đến nay`}${previous&&!showOlderPrices&&thisYear.length?' · kèm giá gần nhất trước đầu năm':''}. Không có mốc nghĩa là app chưa có dữ liệu xác minh cho thời gian đó.`;
  const source=p=>p.source_url==='manual'?'<small>Nguồn: nhập thủ công</small>':`<small>Nguồn: <a href="${escapeHTML(p.source_url)}" target="_blank" rel="noopener">${escapeHTML(priceSource(p.source_url))}</a></small>`;
  $('#price-list').innerHTML=(visible.length?visible.map(p=>`<div class="price-item"><div><b>${money(p.unit_price_vnd_per_liter)}/lít</b><small>${escapeHTML(fuelName(p.fuel_type_id))} · Vùng ${p.price_zone}</small></div><div><span>${day(p.effective_at.slice(0,10))} · ${p.effective_at.slice(11,16)}</span>${source(p)}</div></div>`).join(''):`<p>Chưa có mốc giá xác minh từ đầu năm ${year} cho ${escapeHTML(fuelName(fuelId))}, vùng ${v?.price_zone||1}. Có thể đồng bộ giá hiện hành hoặc bổ sung giá lịch sử đã kiểm tra.</p>`)+(rows.some(p=>p.effective_at.slice(0,10)<start)?`<button type="button" class="text-button" id="toggle-older-prices">${showOlderPrices?'Thu gọn về năm hiện tại':'Xem tất cả mốc giá cũ'}</button>`:'');
  $('#toggle-older-prices')?.addEventListener('click',()=>{showOlderPrices=!showOlderPrices;renderPrices();});}
function openPrices(){populateFuels();const f=$('#price-form'),v=activeVehicle(),now=localNow();f.elements.fuel_type_id.value=($('#log-dialog').open?$('#log-form').elements.fuel_type_id.value:v?.default_fuel_type_id)||'F1';f.elements.price_zone.value=v?.price_zone||1;f.elements.effective_at.value=($('#log-dialog').open?$('#log-form').elements.refueled_on.value:now.day)+'T00:00';$('#prices-status').textContent=state.sync.price_sync_error||'';renderPrices();$('#prices-dialog').showModal();if($('#log-dialog').open&&!activeQuote?.price)$('#manual-price').open=true;}
$('#prices-open').onclick=openPrices;$('#log-prices').onclick=openPrices;
$('#sync-prices').onclick=async()=>{const b=$('#sync-prices');b.disabled=true;$('#prices-status').textContent='Đang đọc bảng giá Petrolimex…';try{await api('prices/sync',{});render();const run=state.price_sync_runs?.[0];$('#prices-status').textContent=run?`Đã kiểm tra Petrolimex: thêm ${nf(run.inserted_rows,0)}, đổi ${nf(run.changed_rows,0)}, giữ nguyên ${nf(run.unchanged_rows,0)} mức giá.`:'Đã cập nhật giá từ Petrolimex.';if($('#log-dialog').open&&!editing)await updateQuote();}catch(e){$('#prices-status').textContent=e.message;}finally{b.disabled=false;}};
$('#export').onclick=()=>{const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}));a.href=url;a.download='fuel-data.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
async function refreshSession(){if(!session?.refresh_token||!authConfig)return false;try{const result=await authCall('token?grant_type=refresh_token',{refresh_token:session.refresh_token});saveSession(result);return true;}catch{saveSession(null);return false;}}
async function authCall(path,body,token){const response=await fetch(authConfig.supabase_url+'/auth/v1/'+path,{method:'POST',headers:{apikey:authConfig.supabase_anon_key,'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify(body)});const result=await response.json().catch(()=>({}));if(!response.ok)throw new Error(result.msg||result.message||result.error_description||result.error||'Không thể xác thực tài khoản.');return result;}
function authMessage(value,error=false){const node=$('#auth-message');node.textContent=value;node.classList.toggle('error',error);}
function setAuthMode(mode){authMode=mode;const title={login:'Đăng nhập',signup:'Tạo tài khoản',recover:'Khôi phục mật khẩu'}[mode];$('#auth-title').textContent=title;$('#auth-description').textContent=mode==='signup'?'Tạo tài khoản để dữ liệu xe được lưu và đồng bộ an toàn.':mode==='recover'?'Nhập email để nhận liên kết đặt lại mật khẩu.':'Đăng nhập để xem và lưu dữ liệu xe của bạn.';$('#password-label').hidden=mode==='recover';$('#auth-form').elements.password.required=mode!=='recover';$('#auth-submit').textContent=title;$('#auth-message').textContent='';$('#recovery-form').hidden=true;$('#auth-form').hidden=false;document.querySelectorAll('[data-auth-mode]').forEach(b=>b.hidden=mode===b.dataset.authMode);}
async function startApp(){if(!session?.access_token){$('#app-shell').hidden=true;$('#auth-shell').hidden=false;return;}$('#auth-shell').hidden=true;$('#app-shell').hidden=false;$('#account-email').textContent=session.user?.email||'Tài khoản';try{await api('state');populateFuels();render();}catch(e){$('#app-shell').hidden=true;$('#auth-shell').hidden=false;authMessage(e.message,true);}}
$('#auth-form').onsubmit=async e=>{e.preventDefault();const values=Object.fromEntries(new FormData(e.target));$('#auth-submit').disabled=true;authMessage('Đang xử lý…');try{if(authMode==='recover'){await authCall('recover?'+new URLSearchParams({redirect_to:location.origin+'/'}),{email:values.email});authMessage('Nếu tài khoản tồn tại, email đặt lại mật khẩu sẽ được gửi.');return;}const result=authMode==='signup'?await authCall('signup',{email:values.email,password:values.password,options:{emailRedirectTo:location.origin+'/'}}):await authCall('token?grant_type=password',{email:values.email,password:values.password});if(result.access_token){saveSession(result);await startApp();authMessage('');}else authMessage('Kiểm tra email để xác nhận tài khoản, rồi đăng nhập.');}catch(error){authMessage(error.message,true);}finally{$('#auth-submit').disabled=false;}};
document.querySelectorAll('[data-auth-mode]').forEach(button=>button.onclick=()=>setAuthMode(button.dataset.authMode));
$('#recovery-form').onsubmit=async e=>{e.preventDefault();try{const result=await fetch(authConfig.supabase_url+'/auth/v1/user',{method:'PUT',headers:{apikey:authConfig.supabase_anon_key,Authorization:'Bearer '+session.access_token,'Content-Type':'application/json'},body:JSON.stringify({password:e.target.elements.password.value})});if(!result.ok)throw new Error('Không đổi được mật khẩu. Hãy mở lại liên kết khôi phục mới nhất.');history.replaceState(null,'',location.pathname);$('#recovery-form').hidden=true;$('#auth-form').hidden=false;saveSession(null);setAuthMode('login');authMessage('Mật khẩu đã được đổi. Hãy đăng nhập.');}catch(error){authMessage(error.message,true);}};
$('#logout').onclick=async()=>{try{await fetch(authConfig.supabase_url+'/auth/v1/logout',{method:'POST',headers:{apikey:authConfig.supabase_anon_key,Authorization:'Bearer '+session.access_token}});}catch{}saveSession(null);state={vehicles:[],logs:[],prices:[],fuel_types:[],sync:{}};startApp();};
async function bootstrap(){try{const response=await fetch('/api/config');authConfig=await response.json();if(!response.ok)throw new Error(authConfig.error||'Thiếu cấu hình đăng nhập.');if(authConfig.auth_enabled===false){session={access_token:'isolated-test-session',user:{email:'test@local'}};await startApp();return;}const fragment=new URLSearchParams(location.hash.slice(1));if(fragment.get('type')==='recovery'&&fragment.get('access_token')){saveSession({access_token:fragment.get('access_token'),refresh_token:fragment.get('refresh_token'),expires_in:Number(fragment.get('expires_in')||3600)});$('#auth-shell').hidden=false;$('#recovery-form').hidden=false;$('#auth-form').hidden=true;$('#auth-title').textContent='Đặt lại mật khẩu';$('#auth-description').textContent='Chọn mật khẩu mới cho tài khoản.';return;}if(session&&session.expires_at<Date.now()/1000+30)await refreshSession();await startApp();}catch(error){$('#auth-shell').hidden=false;$('#app-shell').hidden=true;authMessage(error.message,true);}}
bootstrap();
window.addEventListener('storage',event=>{if(event.key==='fuel-auth-session'){session=readSession();startApp();}});
setInterval(async()=>{if(document.hidden||document.querySelector('dialog[open]')||$('#app-shell').hidden)return;try{await api('state');render();}catch{}},60000);

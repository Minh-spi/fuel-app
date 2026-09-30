/* OCR stays in the browser; only a user-checked numeric ODO reaches the server. */
(() => {
  const dialog = document.querySelector('#camera-dialog');
  const canvas = document.querySelector('#crop-canvas');
  const ctx = canvas.getContext('2d');
  const status = document.querySelector('#ocr-status');
  let photo = null, selection = null, start = null, worker = null, epoch = 0, busy = false;
  const $ = s => document.querySelector(s);
  function draw() {
    if (!photo) return;
    ctx.drawImage(photo, 0, 0, canvas.width, canvas.height);
    if (selection) {
      const {x,y,w,h}=selection;
      ctx.fillStyle='#163a3155';ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(photo,x*photo.width/canvas.width,y*photo.height/canvas.height,w*photo.width/canvas.width,h*photo.height/canvas.height,x,y,w,h);
      ctx.strokeStyle='#5affbe';ctx.lineWidth=3;ctx.strokeRect(x,y,w,h);
    }
  }
  $('#camera-open').onclick=()=>{status.textContent='';dialog.showModal();};
  $('#take-photo').onclick=()=>$('#camera-file').click();
  $('#choose-photo').onclick=()=>$('#photo-file').click();
  function controls(disabled){busy=disabled;$('#read-odo').disabled=disabled;$('#take-photo').disabled=disabled;$('#choose-photo').disabled=disabled;$('#reset-crop').disabled=disabled;}
  async function loadPhoto(event) {
    const file=event.target.files[0];event.target.value='';if(!file)return;
    if(file.size>20*1024*1024){status.textContent='Ảnh quá lớn. Hãy chọn ảnh nhỏ hơn 20 MB.';return;}
    const generation=++epoch;const url=URL.createObjectURL(file);
    try{const img=new Image();img.src=url;await img.decode();if(generation!==epoch)return;photo=img;const scale=Math.min(1,1000/img.width,1000/img.height);canvas.width=Math.round(img.width*scale);canvas.height=Math.round(img.height*scale);selection=null;draw();$('#crop-area').hidden=false;$('#ocr-result').hidden=true;status.textContent='Ảnh đã sẵn sàng. Khoanh dãy số ODO rồi bấm Đọc số ODO.';}catch{status.textContent='Không mở được ảnh. Hãy thử ảnh JPEG hoặc PNG.';}finally{URL.revokeObjectURL(url);}
  }
  $('#camera-file').onchange=loadPhoto;$('#photo-file').onchange=loadPhoto;
  function point(e){const r=canvas.getBoundingClientRect();return{x:Math.max(0,Math.min(canvas.width,(e.clientX-r.left)*canvas.width/r.width)),y:Math.max(0,Math.min(canvas.height,(e.clientY-r.top)*canvas.height/r.height))};}
  canvas.onpointerdown=e=>{if(!photo||busy)return;start=point(e);canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(!start||busy)return;const p=point(e);selection={x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y)};draw();};
  canvas.onpointerup=()=>{start=null;if(selection&&(selection.w<8||selection.h<8))selection=null;draw();};
  canvas.onpointercancel=()=>{start=null;};
  $('#reset-crop').onclick=()=>{selection=null;draw();};
  function candidates(text){
    const matches=text.match(/\d(?:[\d., ]*\d)?/g)||[];const found=[];
    for(let raw of matches){raw=raw.replace(/\s/g,'');let value;
      if(/^\d{1,3}(?:[.,]\d{3})+(?:[.,]\d)?$/.test(raw)){const last=raw.match(/[.,](\d)$/);value=last?Number(raw.slice(0,-2).replace(/[.,]/g,'')+'.'+last[1]):Number(raw.replace(/[.,]/g,''));}
      else if(/^\d+(?:[.,]\d)?$/.test(raw))value=Number(raw.replace(',','.'));
      if(Number.isFinite(value)&&value>=0&&value<=9999999&&!found.includes(value))found.push(value);
    }
    return found.sort((a,b)=>String(b).length-String(a).length).slice(0,6);
  }
  async function loadLibrary(){
    if(window.Tesseract)return;
    await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/vendor/tesseract.min.js';script.onload=resolve;script.onerror=()=>{script.remove();reject(new Error('Chưa có bộ OCR. Chạy npm run setup:ocr trên máy chủ rồi thử lại.'));};document.head.append(script);});
  }
  $('#read-odo').onclick=async()=>{
    if(!photo||busy)return;const generation=++epoch;controls(true);$('#ocr-result').hidden=true;status.textContent='Đang khởi động bộ đọc ảnh…';let timeout, ownWorker;
    try{
      const job=(async()=>{
        await loadLibrary();if(generation!==epoch)return;
        const engine=await Tesseract.createWorker('eng',1,{workerPath:'/vendor/worker.min.js',corePath:'/vendor/core',langPath:'/vendor/lang',logger:m=>{if(generation===epoch&&m.status==='recognizing text')status.textContent=`Đang đọc số… ${Math.round(m.progress*100)}%`;}});
        if(generation!==epoch){await engine.terminate();return;}worker=engine;ownWorker=engine;
        await engine.setParameters({tessedit_char_whitelist:'0123456789., ',tessedit_pageseg_mode:'6'});
        const r=selection||{x:0,y:0,w:canvas.width,h:canvas.height};const input=document.createElement('canvas');
        const scale=Math.min(3,1800/r.w);input.width=Math.round(r.w*scale);input.height=Math.round(r.h*scale);
        const c=input.getContext('2d');c.fillStyle='white';c.fillRect(0,0,input.width,input.height);c.drawImage(photo,r.x*photo.width/canvas.width,r.y*photo.height/canvas.height,r.w*photo.width/canvas.width,r.h*photo.height/canvas.height,0,0,input.width,input.height);
        const result=await engine.recognize(input);if(generation!==epoch)return;
        const values=candidates(result.data.text);$('#ocr-result').hidden=false;$('#ocr-number').value=values[0]??'';
        $('#ocr-options').replaceChildren();for(const value of values.slice(1)){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=String(value);b.onclick=()=>$('#ocr-number').value=value;$('#ocr-options').append(b);}
        status.textContent=values.length?`Đã đọc ảnh${result.data.confidence<65?' · độ tin cậy thấp':''}. Hãy kiểm tra số bên dưới.`:'Chưa đọc rõ dãy số. Khoanh vùng nhỏ hơn, chụp lại hoặc nhập số bên dưới.';
      })();
      await Promise.race([job,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('Đọc ảnh mất quá lâu. Hãy chụp gần dãy số hơn hoặc nhập ODO bằng tay.')),45000);})]);
    }catch(e){if(generation===epoch)status.textContent=e.message||'Chưa đọc được ảnh. Bạn có thể nhập ODO bằng tay.';}
    finally{clearTimeout(timeout);if(generation===epoch){epoch++;controls(false);}if(ownWorker){await ownWorker.terminate();if(worker===ownWorker)worker=null;}}
  };
  $('#use-odo').onclick=()=>{const input=$('#ocr-number');if(!input.value||!input.reportValidity())return;const f=$('#log-form');f.elements.odometer_km.value=input.value;f.elements.odo_source.value='photo_confirmed';f.elements.odometer_km.dispatchEvent(new Event('change',{bubbles:true}));updateDistance();dialog.close();};
  dialog.addEventListener('close',()=>{epoch++;if(worker){worker.terminate();worker=null;}controls(false);photo=null;selection=null;ctx.clearRect(0,0,canvas.width,canvas.height);$('#crop-area').hidden=true;$('#ocr-result').hidden=true;});
})();

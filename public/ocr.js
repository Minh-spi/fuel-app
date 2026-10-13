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
  function controls(disabled){busy=disabled;$('#read-odo').disabled=disabled;$('#take-photo').disabled=disabled;$('#choose-photo').disabled=disabled;$('#rotate-photo').disabled=disabled;$('#reset-crop').disabled=disabled;}
  function displayPhoto(image){photo=image;const scale=Math.min(1,1000/image.width,1000/image.height);canvas.width=Math.round(image.width*scale);canvas.height=Math.round(image.height*scale);selection=null;draw();$('#crop-area').hidden=false;$('#ocr-result').hidden=true;status.textContent='Ảnh đã sẵn sàng. Khoanh sát cả dãy số ODO, gồm bánh số nhỏ cuối nếu có; tránh số trên đồng hồ tốc độ.';}
  async function loadPhoto(event) {
    const file=event.target.files[0];event.target.value='';if(!file)return;
    if(file.size>20*1024*1024){status.textContent='Ảnh quá lớn. Hãy chọn ảnh nhỏ hơn 20 MB.';return;}
    const generation=++epoch;const url=URL.createObjectURL(file);
    try{const img=new Image();img.src=url;await img.decode();if(generation!==epoch)return;displayPhoto(img);}catch{status.textContent='Không mở được ảnh. Hãy thử ảnh JPEG hoặc PNG.';}finally{URL.revokeObjectURL(url);}
  }
  $('#camera-file').onchange=loadPhoto;$('#photo-file').onchange=loadPhoto;
  $('#rotate-photo').onclick=()=>{if(!photo||busy)return;const rotated=document.createElement('canvas');rotated.width=photo.height;rotated.height=photo.width;const rctx=rotated.getContext('2d');rctx.translate(rotated.width/2,rotated.height/2);rctx.rotate(Math.PI/2);rctx.drawImage(photo,-photo.width/2,-photo.height/2);displayPhoto(rotated);};
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
      if(/^\d{6}$/.test(raw)){const tenths=Number(raw.slice(0,-1)+'.'+raw.slice(-1));if(tenths<=9999999&&!found.includes(tenths))found.push(tenths);}
    }
    return found.sort((a,b)=>String(b).length-String(a).length).slice(0,6);
  }
  function ranked(result,width,height){
    const scored=[];
    for(const word of result.data.words||[]){
      const raw=String(word.text||'').trim().replace(/\s/g,'');if(!/^\d[\d.,]*$/.test(raw))continue;
      const digits=(raw.match(/\d/g)||[]).length;if(digits<4)continue;
      const box=word.bbox||{},cx=((box.x0||0)+(box.x1||0))/2/width,cy=((box.y0||0)+(box.y1||0))/2/height;
      const center=1-Math.min(1,Math.abs(cx-.5)*1.5),lower=1-Math.min(1,Math.abs(cy-.62)*1.4);
      const position=center*.55+lower*.45,confidence=Number(word.confidence)||0;
      for(const value of candidates(raw))scored.push({value,confidence,position,digits,box,score:confidence+Math.min(digits,7)*5+position*11+(String(value).includes('.')?2:0)});
    }
    if(!scored.length)for(const value of candidates(result.data.text||'')){const digits=String(value).replace(/\D/g,'').length;if(digits>=4)scored.push({value,confidence:Number(result.data.confidence)||0,position:0,digits,box:null,score:(Number(result.data.confidence)||0)+Math.min(digits,7)*3});}
    return scored.sort((a,b)=>b.score-a.score).filter((r,i,a)=>a.findIndex(x=>x.value===r.value)===i);
  }
  function rotated(image,degrees){
    if(degrees===0)return image;const out=document.createElement('canvas'),swap=degrees%180!==0;out.width=swap?image.height:image.width;out.height=swap?image.width:image.height;
    const c=out.getContext('2d');c.translate(out.width/2,out.height/2);c.rotate(degrees*Math.PI/180);c.drawImage(image,-image.width/2,-image.height/2);return out;
  }
  async function loadLibrary(){
    if(window.Tesseract)return;
    await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/vendor/tesseract.min.js';script.onload=resolve;script.onerror=()=>{script.remove();reject(new Error('Thiếu tài sản OCR trên deployment. Hãy thêm thư mục public/vendor vào GitHub rồi triển khai lại.'));};document.head.append(script);});
  }
  $('#read-odo').onclick=async()=>{
    if(!photo||busy)return;const generation=++epoch;controls(true);$('#ocr-result').hidden=true;status.textContent='Đang khởi động bộ đọc ảnh…';let timeout, ownWorker;
    try{
      const job=(async()=>{
        await loadLibrary();if(generation!==epoch)return;
        const engine=await Tesseract.createWorker('eng',1,{workerPath:'/vendor/worker.min.js',corePath:'/vendor/core',langPath:'/vendor/lang',logger:m=>{if(generation===epoch&&m.status==='recognizing text')status.textContent=`Đang đọc số… ${Math.round(m.progress*100)}%`;}});
        if(generation!==epoch){await engine.terminate();return;}worker=engine;ownWorker=engine;
        await engine.setParameters({tessedit_char_whitelist:'0123456789., ',tessedit_pageseg_mode:'11'});
        let source=photo,input,first,rankedFirst=[];const angles=selection?[0]:[0,90,270,180];
        for(const angle of angles){
          source=rotated(photo,angle);const scale=Math.min(1,1800/Math.max(source.width,source.height));input=document.createElement('canvas');input.width=Math.max(1,Math.round(source.width*scale));input.height=Math.max(1,Math.round(source.height*scale));
          input.getContext('2d').drawImage(source,0,0,input.width,input.height);
          if(selection){const r=selection,cropped=document.createElement('canvas'),factor=Math.min(3,1800/r.w);cropped.width=Math.max(1,Math.round(r.w*factor));cropped.height=Math.max(1,Math.round(r.h*factor));const cc=cropped.getContext('2d');cc.fillStyle='white';cc.fillRect(0,0,cropped.width,cropped.height);cc.drawImage(source,r.x*source.width/canvas.width,r.y*source.height/canvas.height,r.w*source.width/canvas.width,r.h*source.height/canvas.height,0,0,cropped.width,cropped.height);input=cropped;source=angle?source:photo;}
          first=await engine.recognize(input);if(generation!==epoch)return;rankedFirst=ranked(first,input.width,input.height);
          if(selection||rankedFirst.some(item=>item.digits>=5&&item.confidence>=35))break;
        }
        if(!selection&&source!==photo){photo=source;displayPhoto(photo);}
        let focused=input;
        const target=rankedFirst[0]?.box;
        if(!selection&&target){const padX=Math.max(24,(target.x1-target.x0)*.35),padY=Math.max(18,(target.y1-target.y0)*.8),x=Math.max(0,target.x0-padX),y=Math.max(0,target.y0-padY),right=Math.min(input.width,target.x1+padX),bottom=Math.min(input.height,target.y1+padY);const roi=document.createElement('canvas');roi.width=Math.max(1,right-x);roi.height=Math.max(1,bottom-y);roi.getContext('2d').drawImage(input,x,y,roi.width,roi.height,0,0,roi.width,roi.height);focused=roi;}
        const enhanced=document.createElement('canvas');enhanced.width=focused.width;enhanced.height=focused.height;const ec=enhanced.getContext('2d');ec.filter='grayscale(1) contrast(1.5)';ec.drawImage(focused,0,0);
        await engine.setParameters({tessedit_char_whitelist:'0123456789., ',tessedit_pageseg_mode:'7'});const second=await engine.recognize(enhanced);if(generation!==epoch)return;
        const combined=[...rankedFirst,...ranked(second,enhanced.width,enhanced.height)],values=combined.sort((a,b)=>b.score-a.score).filter((r,i,a)=>a.findIndex(x=>x.value===r.value)===i).map(r=>r.value).slice(0,6),format=value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:1}).format(value),confidence=Math.max(Number(first.data.confidence)||0,Number(second.data.confidence)||0);$('#ocr-result').hidden=false;$('#ocr-number').value=values.length?format(values[0]):'';
        $('#ocr-options').replaceChildren();for(const value of values.slice(1)){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=format(value);b.onclick=()=>$('#ocr-number').value=format(value);$('#ocr-options').append(b);}
        status.textContent=values.length?`Đã tự tìm cụm số có dạng ODO${confidence<50?' · độ tin cậy thấp':''}. Hãy kiểm tra lại số và phần thập phân trước khi lưu.`:'Chưa tự tìm được ODO. Xoay ảnh hoặc khoanh sát hàng số để đọc lại.';
      })();
      await Promise.race([job,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('Đọc ảnh mất quá lâu. Hãy chụp gần dãy số hơn hoặc nhập ODO bằng tay.')),45000);})]);
    }catch(e){if(generation===epoch)status.textContent=e.message||'Chưa đọc được ảnh. Bạn có thể nhập ODO bằng tay.';}
    finally{clearTimeout(timeout);if(generation===epoch){epoch++;controls(false);}if(ownWorker){await ownWorker.terminate();if(worker===ownWorker)worker=null;}}
  };
  $('#use-odo').onclick=()=>{const input=$('#ocr-number');if(!input.value)return;const f=$('#log-form');f.elements.odometer_km.value=input.value;f.elements.odo_source.value='photo_confirmed';f.elements.odometer_km.dispatchEvent(new Event('input',{bubbles:true}));f.elements.odometer_km.blur();updateDistance();dialog.close();};
  dialog.addEventListener('close',()=>{epoch++;if(worker){worker.terminate();worker=null;}controls(false);photo=null;selection=null;ctx.clearRect(0,0,canvas.width,canvas.height);$('#crop-area').hidden=true;$('#ocr-result').hidden=true;});
})();

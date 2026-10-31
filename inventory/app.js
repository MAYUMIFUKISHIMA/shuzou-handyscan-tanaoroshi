const $=id=>document.getElementById(id);let sessions=[],token='',busy=false;let importData=null,previewKey=null;
const current=()=>sessions.find(s=>s.id===$('session').value);
function message(s){$('message').textContent=s;}
async function refresh(selected){const data=await requestJSON('/api');sessions=data.sessions;token=data.token;const old=selected||$('session').value;$('session').replaceChildren(...sessions.map(s=>new Option(s.id.slice(0,8)+' / '+s.state,s.id)));if(sessions.some(s=>s.id===old))$('session').value=old;render();}
function active(s,code,loc){const rs=s.records.filter(r=>r.code===code&&r.location===loc);const removed=new Set(rs.flatMap(r=>r.supersedes));return rs.filter(r=>!removed.has(r.id));}
function product(){const s=current(),item=s?.items.find(i=>i.code===$('code').value);$('product').textContent=item?item.name+' / 現在の記録: '+active(s,item.code,$('location').value).map(r=>r.quantity+' ('+r.device+')').join(', '):'商品番号を読み取るか入力してください';}
function render(){const s=current();$('held').replaceChildren(...(s?.held||[]).filter(x=>x.status==='open').map(x=>new Option(x.code+' / '+x.quantity+' / '+x.location,x.id)));const loc=$('location').value;$('location').replaceChildren(...(s?.locations||[]).map(x=>new Option(x,x)));if(s?.locations.includes(loc))$('location').value=loc;$('rows').replaceChildren();for(const r of s?.summary||[]){const tr=document.createElement('tr');for(const k of ['code','name','baseline','count','difference']){const td=document.createElement('td');td.textContent=r[k]??'未棚卸 / 競合';tr.append(td);}$('rows').append(tr);}$('state').textContent=s?`状態: ${s.state} / 完了区画: ${s.completed.join(', ')||'なし'}`:'棚卸を作成してください';$('audit').textContent=s?JSON.stringify({audit:s.audit,records:s.records,held:s.held,previous_results:s.previous_results},null,2):'';product();}
const pendingKey='inventory.pending.v1';
function pending(){const raw=localStorage.getItem(pendingKey);return raw?JSON.parse(raw):null;}
async function requestJSON(url,options={}){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
  try{const response=await fetch(url,{...options,signal:controller.signal});const result=await response.json();if(!response.ok){const error=Error(result.error||'操作に失敗しました');error.status=response.status;throw error;}return result;}
  finally{clearTimeout(timer);}
}
async function sendPending(){
  const body=pending();if(!body)throw Error('再送する操作はありません');
  try{
    const result=await requestJSON('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify(body)});
    await refresh(result.id);localStorage.removeItem(pendingKey);
    if(['receive','hold'].includes(body.action)){$('quantity').value='';$('code').value='';product();}
    if(body.action==='create')invalidate();
    return current();
  }catch(error){
    if(error.status===400){localStorage.removeItem(pendingKey);throw error;}
    throw Error('結果を確認できません。入力・送信内容を保持しました。「同じ操作を再送」を押してください。 '+error.message);
  }
}
async function post(action,payload=null){
  if(pending())throw Error('未確認の操作があります。先に同じ操作を再送してください');
  const s=current();const body={action,request_id:crypto.randomUUID(),actor:$('actor').value,...(action==='create'?payload:{id:s?.id,revision:s?.revision,payload})};
  localStorage.setItem(pendingKey,JSON.stringify(body));return sendPending();
}
function controls(){const waiting=!!pending();document.querySelectorAll('button').forEach(b=>b.disabled=busy||(waiting&&!['retry','reload'].includes(b.id)));$('create').disabled=busy||waiting||!previewKey;document.querySelectorAll('input,select').forEach(e=>e.disabled=busy||waiting);$('pending-status').textContent=waiting?'未確認の送信があります。内容はこのブラウザーに保存されています。新規操作の前に再送してください。':'';}
function bind(id,fn){$(id).onclick=async()=>{if(busy)return;busy=true;controls();message('');try{await fn();message('操作が完了しました');}catch(e){message(e.message);}finally{busy=false;controls();}};}
bind('retry',async()=>{await refresh();await sendPending();});
bind('reload',()=>refresh());
bind('reopen',async()=>{const reason=prompt('訂正理由を入力してください（出力前のみ）');if(reason)await post('reopen',{reason});});
function invalidate(){previewKey=null;$('create').disabled=true;$('preview-info').textContent='';$('preview-rows').replaceChildren();}
function mapping(){return {code:$('map-code').value,name:$('map-name').value,baseline:$('map-baseline').value};}
function signature(){return JSON.stringify({data:importData,columns:mapping()});}
async function importRequest(action,data){return requestJSON('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify({action,...data})});}
bind('inspect',async()=>{invalidate();importData=null;$('mapping').hidden=true;const f=$('file').files[0];if(!f)throw Error('CSVを選択してください');if(f.size>1000000)throw Error('試作では1MB以内です');const encoding=$('encoding').value;let binary='';for(const byte of new Uint8Array(await f.arrayBuffer()))binary+=String.fromCharCode(byte);const data={csv:btoa(binary),encoding,source_name:f.name};const result=await importRequest('inspect',data);if(f!==$('file').files[0]||encoding!==$('encoding').value)throw Error('設定が変わりました。列を再読み込みしてください');importData=data;for(const [key,defaultName] of Object.entries({code:'商品番号',name:'名称',baseline:'数量'})){const select=$('map-'+key);select.replaceChildren(new Option('選択してください',''),...result.headers.map(h=>new Option(h,h)));if(result.headers.includes(defaultName))select.value=defaultName;}$('mapping').hidden=false;});
bind('preview',async()=>{invalidate();if(!importData)throw Error('列を読み込んでください');const key=signature();const result=await importRequest('preview',{...importData,columns:mapping()});if(key!==signature())throw Error('設定が変わりました。再検証してください');$('preview-info').textContent=`全${result.count}件を検証済み（先頭100件まで表示）`+(result.duplicates.length?'。注意：同じファイルの取り込み履歴があります。新しい棚卸として作成されます。':'');for(const item of result.items){const tr=document.createElement('tr');for(const field of ['code','name','baseline']){const td=document.createElement('td');td.textContent=item[field];tr.append(td);}$('preview-rows').append(tr);}previewKey=key;});
bind('create',async()=>{if(!previewKey||previewKey!==signature())throw Error('取り込み前に全件検証してください');if(!confirm('表示内容を新しい棚卸として取り込みますか？'))return;await post('create',{...importData,columns:mapping(),locations:$('locations').value.split(',').map(x=>x.trim())});invalidate();});
for(const id of ['file','encoding'])$(id).onchange=()=>{invalidate();importData=null;$('mapping').hidden=true;};
for(const key of ['code','name','baseline'])$('map-'+key).onchange=invalidate;
bind('save',async()=>{const s=current();if(!s)throw Error('棚卸を選択してください');if(!s.items.some(i=>i.code===$('code').value)){if(confirm('未登録バーコードです。数量を保留して後で照合しますか？'))await post('hold',{id:crypto.randomUUID(),device:$('device').value,operator:$('actor').value,code:$('code').value,location:$('location').value,quantity:$('quantity').value});return;}const rs=active(s,$('code').value,$('location').value);if(rs.length&&!confirm('既存記録 '+rs.map(r=>r.quantity+' / '+r.device).join(', ')+' を新しい実数で訂正しますか？'))return;await post('receive',[{id:crypto.randomUUID(),device:$('device').value,operator:$('actor').value,code:$('code').value,location:$('location').value,quantity:$('quantity').value,supersedes:rs.map(r=>r.id)}]);$('quantity').value='';$('code').value='';$('code').focus();product();});
bind('complete',()=>post('complete',{location:$('location').value}));
bind('finalize',async()=>{if(confirm('確定後はこの棚卸を変更できません。確定しますか？'))await post('finalize');});
bind('export',async()=>{const s=await post('export');const url=URL.createObjectURL(new Blob(['\ufeff',s.csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='確認用_'+s.id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('session').onchange=render;$('location').onchange=product;$('code').oninput=product;refresh().catch(e=>message(e.message)).finally(controls);

bind('resolve',async()=>{const s=current(),held=s?.held?.find(x=>x.id===$('held').value);if(!held)throw Error('保留を選択してください');const code=$('code').value;const rs=active(s,code,held.location);if(rs.length)throw Error('この商品の区画には既に記録があります。履歴確認後に保留を除外し、通常の訂正を行ってください');const reason=prompt('照合した根拠を入力してください');if(reason)await post('resolve',{id:held.id,reason,record:{id:crypto.randomUUID(),code,location:held.location,quantity:held.quantity,device:held.device,operator:$('actor').value,supersedes:[]}});});
bind('dismiss',async()=>{if(!$('held').value)throw Error('保留を選択してください');const reason=prompt('保留を除外する理由を入力してください');if(reason)await post('dismiss',{id:$('held').value,reason});});

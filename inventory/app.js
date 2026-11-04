const $=id=>document.getElementById(id);let sessions=[],token='',busy=false;let importData=null,previewKey=null;
let ownsWorkspace=false;
const current=()=>sessions.find(s=>s.id===$('session').value);
function message(s){$('message').textContent=s;}
async function refresh(selected){const data=await requestJSON('/api');sessions=data.sessions;token=data.token;const old=selected||$('session').value;$('session').replaceChildren(...sessions.map(s=>new Option(s.id.slice(0,8)+' / '+s.state,s.id)));if(sessions.some(s=>s.id===old))$('session').value=old;render();}
function active(s,code,loc){const rs=s.records.filter(r=>r.code===code&&r.location===loc);const removed=new Set(rs.flatMap(r=>r.supersedes));return rs.filter(r=>!removed.has(r.id));}
function product(){const s=current(),item=s?.items.find(i=>i.code===$('code').value);$('product').textContent=item?item.name+' / 現在の記録: '+active(s,item.code,$('location').value).map(r=>r.quantity+' ('+r.device+')').join(', '):'商品番号を読み取るか入力してください';}
function rowStatus(s,code){const counts=s.locations.map(loc=>active(s,code,loc).length);return counts.some(n=>n>1)?'競合':counts.some(n=>n===0)?'未棚卸':'入力済み';}
function render(){const s=current();if(s?.import_artifact&&$('output-columns').dataset.session!==s.id){restoreOutput(s.import_artifact.profile);$('output-columns').dataset.session=s.id;}$('held').replaceChildren(...(s?.held||[]).filter(x=>x.status==='open').map(x=>new Option(x.code+' / '+x.quantity+' / '+x.location,x.id)));const loc=$('location').value;$('location').replaceChildren(...(s?.locations||[]).map(x=>new Option(x,x)));if(s?.locations.includes(loc))$('location').value=loc;$('rows').replaceChildren();const query=$('search').value.trim().toLowerCase(),filter=$('filter').value;const rows=(s?.summary||[]).filter(r=>(r.code+' '+r.name).toLowerCase().includes(query)).filter(r=>filter==='all'||(filter==='missing'&&s.locations.some(loc=>active(s,r.code,loc).length===0))||(filter==='conflict'&&s.locations.some(loc=>active(s,r.code,loc).length>1))||(filter==='difference'&&r.difference!==null&&Number(r.difference)!==0)||(filter==='held'&&(s.held||[]).some(h=>h.status==='open'&&h.code===r.code)));$('result-count').textContent=`${rows.length} / ${s?.items.length||0}件`;for(const r of rows){const tr=document.createElement('tr');for(const k of ['code','name','baseline','count','difference']){const td=document.createElement('td');td.textContent=r[k]??rowStatus(s,r.code);tr.append(td);}$('rows').append(tr);}$('state').textContent=s?`試作・連携未確認 / 状態: ${s.state} / 完了区画: ${s.completed.join(', ')||'なし'}`:'棚卸を作成してください';$('audit').textContent=s?JSON.stringify({audit:s.audit,records:s.records,capacity:s.capacity,export_manifest:s.export_manifest,export_hash:s.export_hash,import_artifact:s.import_artifact?{...s.import_artifact,data:undefined}:undefined,result_version:s.result_version,finalized_by:s.finalized_by,finalized_at:s.finalized_at,held:s.held,previous_results:s.previous_results},null,2):'';product();}
const pendingKey='inventory.pending.v1';
function pending(){const raw=localStorage.getItem(pendingKey);return raw?JSON.parse(raw):null;}
async function requestJSON(url,options={}){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
  try{const response=await fetch(url,{...options,signal:controller.signal});const result=await response.json();if(!response.ok){const error=Error(result.error||'操作に失敗しました');error.status=response.status;throw error;}return result;}
  finally{clearTimeout(timer);}
}
async function sendPending(){
  if(!ownsWorkspace)throw Error('別のタブで操作中です');
  const body=pending();if(!body)throw Error('再送する操作はありません');
  try{
    const result=await requestJSON('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify(body)});
    await refresh(result.id);localStorage.removeItem(pendingKey);if(['receive','hold','resolve_conflict'].includes(body.action)){const record=body.action==='receive'?body.payload[0]:body.action==='resolve_conflict'?body.payload.record:body.payload;localStorage.removeItem(draftKey(body.id,record.location));}
    if(['receive','hold','resolve_conflict'].includes(body.action)){$('quantity').value='';$('code').value='';product();}
    if(body.action==='create')invalidate();
    return current();
  }catch(error){
    if(error.status===400){localStorage.removeItem(pendingKey);throw error;}
    throw Error('結果を確認できません。入力・送信内容を保持しました。「同じ操作を再送」を押してください。 '+error.message);
  }
}
async function post(action,payload=null){
  if(!ownsWorkspace)throw Error('別のタブで操作中です');
  if(pending())throw Error('未確認の操作があります。先に同じ操作を再送してください');
  const s=current();const body={action,request_id:crypto.randomUUID(),actor:$('actor').value,...(action==='create'?payload:{id:s?.id,revision:s?.revision,payload})};
  localStorage.setItem(pendingKey,JSON.stringify(body));return sendPending();
}
function controls(){$('tab-status').textContent=ownsWorkspace?'このタブで操作できます':'ほかのタブを閉じると、このタブで操作できます';const waiting=!!pending();document.querySelectorAll('button').forEach(b=>b.disabled=!ownsWorkspace||busy||(waiting&&!['retry','reload'].includes(b.id)));$('create').disabled=!ownsWorkspace||busy||waiting||!previewKey;document.querySelectorAll('input,select').forEach(e=>e.disabled=!ownsWorkspace||busy||waiting);$('pending-status').textContent=waiting?'未確認の送信があります。内容はこのブラウザーに保存されています。新規操作の前に再送してください。':'';}
function bind(id,fn){$(id).onclick=async()=>{if(busy||!ownsWorkspace)return;busy=true;controls();message('');try{await fn();message('操作が完了しました');}catch(e){message(e.message);}finally{busy=false;controls();if(id==='save'&&!pending())($('code').value?$('quantity'):$('code')).focus();}};}
bind('retry',async()=>{await refresh();await sendPending();});
bind('reload',()=>refresh());
bind('reopen',async()=>{const reason=prompt('訂正理由を入力してください（出力前のみ）');if(reason)await post('reopen',{reason});});
function invalidate(){previewKey=null;$('create').disabled=true;$('preview-info').textContent='';$('preview-rows').replaceChildren();}
function mapping(){return {code:$('map-code').value,name:$('map-name').value,baseline:$('map-baseline').value};}
function signature(){return JSON.stringify({data:importData,columns:mapping(),locations:$('locations').value,reserve:$('reserve').value});}
async function importRequest(action,data){return requestJSON('/api',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify({action,...data})});}
bind('inspect',async()=>{invalidate();importData=null;$('mapping').hidden=true;const f=$('file').files[0];if(!f)throw Error('CSVを選択してください');if(f.size>1000000)throw Error('試作では1MB以内です');const encoding=$('encoding').value;let binary='';for(const byte of new Uint8Array(await f.arrayBuffer()))binary+=String.fromCharCode(byte);const data={csv:btoa(binary),encoding,source_name:f.name};const result=await importRequest('inspect',data);if(f!==$('file').files[0]||encoding!==$('encoding').value)throw Error('設定が変わりました。列を再読み込みしてください');importData=data;for(const [key,defaultName] of Object.entries({code:'商品番号',name:'名称',baseline:'数量'})){const select=$('map-'+key);select.replaceChildren(new Option('選択してください',''),...result.headers.map(h=>new Option(h,h)));if(result.headers.includes(defaultName))select.value=defaultName;}const profile=JSON.parse(localStorage.getItem('inventory.csv-profile.v1')||'null');if(profile&&profile.encoding===encoding&&Object.values(profile.columns).every(c=>result.headers.includes(c))){for(const key of ['code','name','baseline'])$('map-'+key).value=profile.columns[key];}$('mapping').hidden=false;});
bind('preview',async()=>{invalidate();if(!importData)throw Error('列を読み込んでください');const key=signature();const result=await importRequest('preview',{...importData,columns:mapping(),locations:$('locations').value.split(',').map(x=>x.trim()),correction_reserve:$('reserve').value===''?null:Number($('reserve').value)});if(key!==signature())throw Error('設定が変わりました。再検証してください');$('preview-info').textContent=`全${result.count}件を検証済み（先頭100件まで表示） / 初回${result.capacity?.initial}＋訂正予約${result.capacity?.reserve}件 / 上限${result.capacity?.limit}件`+(result.duplicates.length?'。注意：同じファイルの取り込み履歴があります。新しい棚卸として作成されます。':'');for(const item of result.items){const tr=document.createElement('tr');for(const field of ['code','name','baseline']){const td=document.createElement('td');td.textContent=item[field];tr.append(td);}$('preview-rows').append(tr);}previewKey=key;});
bind('create',async()=>{if(!previewKey||previewKey!==signature())throw Error('取り込み前に全件検証してください');if(!confirm('表示内容を新しい棚卸として取り込みますか？'))return;await post('create',{...importData,columns:mapping(),locations:$('locations').value.split(',').map(x=>x.trim()),correction_reserve:$('reserve').value===''?null:Number($('reserve').value)});invalidate();});
for(const id of ['file','encoding'])$(id).onchange=()=>{invalidate();importData=null;$('mapping').hidden=true;};
for(const key of ['code','name','baseline'])$('map-'+key).onchange=invalidate;
bind('save',async()=>{const s=current();if(!s)throw Error('棚卸を選択してください');if(!s.items.some(i=>i.code===$('code').value)){if(confirm('未登録バーコードです。数量を保留して後で照合しますか？'))await post('hold',{id:crypto.randomUUID(),device:$('device').value,operator:$('actor').value,code:$('code').value,location:$('location').value,quantity:$('quantity').value});return;}const rs=active(s,$('code').value,$('location').value);if(rs.length&&!confirm('既存記録 '+rs.map(r=>r.quantity+' / '+r.device).join(', ')+' を新しい実数で訂正しますか？'))return;const record={id:crypto.randomUUID(),device:$('device').value,operator:$('actor').value,code:$('code').value,location:$('location').value,quantity:$('quantity').value,supersedes:rs.map(r=>r.id)};if(rs.length>1){const reason=prompt('競合候補を確認した根拠・再計数の理由を入力してください');if(!reason?.trim())return;await post('resolve_conflict',{reason,record});}else await post('receive',[record]);$('quantity').value='';$('code').value='';$('code').focus();product();});
bind('complete',()=>post('complete',{location:$('location').value}));
bind('finalize',async()=>{if(confirm('全区画の計数と差異・保留・競合を確認しましたか？確定後の訂正はCSV出力前に限ります。'))await post('finalize');});
bind('export',async()=>{const s=await post('export');const url=URL.createObjectURL(new Blob(['\ufeff',s.csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='確認用_'+s.id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
const draftKey=(sid,loc)=>'inventory.draft.v1.'+sid+'.'+loc;
function saveDraft(){if(!ownsWorkspace||busy||pending())return;try{const s=current();if(s)localStorage.setItem(draftKey(s.id,$('location').value),JSON.stringify({code:$('code').value,quantity:$('quantity').value}));localStorage.setItem('inventory.preferences.v1',JSON.stringify({session:$('session').value,location:$('location').value,actor:$('actor').value,device:$('device').value,locations:$('locations').value}));$('draft-status').textContent='入力をこのPCのブラウザーに保存しました';}catch(e){message('下書きを保存できません: '+e.message);}}
function restoreDraft(){if(!ownsWorkspace)return;try{const s=current(),raw=s?localStorage.getItem(draftKey(s.id,$('location').value)):null;const draft=raw?JSON.parse(raw):{};$('code').value=draft.code||'';$('quantity').value=draft.quantity||'';$('draft-status').textContent=raw?'保存した下書きを復元しました':'';product();}catch(e){message('下書きを復元できません: '+e.message);}}
$('session').onchange=()=>{render();restoreDraft();saveDraft();};$('location').onchange=()=>{restoreDraft();saveDraft();};
for(const id of ['code','quantity','actor','device','locations'])$(id).oninput=()=>{product();saveDraft();};
$('search').oninput=render;$('filter').onchange=render;
bind('save-profile',async()=>{if(!previewKey)throw Error('全件検証後に保存してください');localStorage.setItem('inventory.csv-profile.v1',JSON.stringify({encoding:importData.encoding,columns:mapping()}));});
bind('discard-draft',async()=>{if(confirm('この区画の入力途中の下書きを削除しますか？')){const s=current();if(s)localStorage.removeItem(draftKey(s.id,$('location').value));$('code').value='';$('quantity').value='';$('draft-status').textContent='';product();}});
async function start(){
 await refresh();controls();
 if(!globalThis.navigator?.locks){message('このブラウザーは複数タブ制御に未対応です。最新のChromeまたはEdgeを使用してください');return;}
 navigator.locks.request('inventory-workspace-v1',async()=>{
  ownsWorkspace=true;
  try{await refresh();const prefs=JSON.parse(localStorage.getItem('inventory.preferences.v1')||'{}');for(const id of ['actor','device','locations'])if(typeof prefs[id]==='string')$(id).value=prefs[id];if(sessions.some(s=>s.id===prefs.session))$('session').value=prefs.session;render();if(current()?.locations.includes(prefs.location))$('location').value=prefs.location;restoreDraft();controls();}catch(e){message(e.message);controls();}
  await new Promise(()=>{});
 });
}
start().catch(e=>message(e.message));

bind('resolve',async()=>{const s=current(),held=s?.held?.find(x=>x.id===$('held').value);if(!held)throw Error('保留を選択してください');const code=$('code').value;const rs=active(s,code,held.location);if(rs.length)throw Error('この商品の区画には既に記録があります。履歴確認後に保留を除外し、通常の訂正を行ってください');const reason=prompt('照合した根拠を入力してください');if(reason)await post('resolve',{id:held.id,reason,record:{id:crypto.randomUUID(),code,location:held.location,quantity:held.quantity,device:held.device,operator:$('actor').value,supersedes:[]}});});
bind('dismiss',async()=>{if(!$('held').value)throw Error('保留を選択してください');const reason=prompt('保留を除外する理由を入力してください');if(reason)await post('dismiss',{id:$('held').value,reason});});

$('reserve').oninput=invalidate;const locationDraftHandler=$('locations').oninput;$('locations').oninput=()=>{locationDraftHandler();invalidate();};

$('code').addEventListener('keydown',event=>{if(event.key!=='Enter')return;event.preventDefault();if(!ownsWorkspace||busy||pending())return;const item=current()?.items.find(i=>i.code===$('code').value);product();if(item){$('quantity').focus();$('quantity').select();}else message('未登録の商品番号です。数量を入力して保留してください');});
$('quantity').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();if(ownsWorkspace&&!busy&&!pending())$('save').click();}});
function addOutputColumn(name='',source='constant'){
 const row=document.createElement('div');row.className='output-column';
 const label=document.createElement('label');label.textContent='列名';const input=document.createElement('input');input.value=name;label.append(input);
 const select=document.createElement('select');for(const [value,title]of [['code','商品番号'],['quantity','数量'],['name','名称'],['constant','固定値']])select.append(new Option(title,value));select.value=source;
 const constant=document.createElement('input');constant.placeholder='固定値の場合の値';const remove=document.createElement('button');remove.textContent='この列を削除';remove.onclick=()=>{if(ownsWorkspace&&!busy&&!pending())row.remove();};row.append(label,select,constant,remove);$('output-columns').append(row);
}
function outputProfile(){return{specification:$('output-spec').value,encoding:$('output-encoding').value,header:$('output-header').value==='yes',quantity_mode:$('output-mode').value,columns:Array.from($('output-columns').children).map(row=>{const [label,select,constant]=row.children;return select.value==='constant'?{name:label.querySelector('input').value,constant:constant.value}:{name:label.querySelector('input').value,source:select.value};})};}
bind('add-output-column',()=>addOutputColumn());
bind('export-import',async()=>{if(!confirm('列順・文字コード・数量の意味を確認しましたか？まず検証先で確認してください。'))return;const s=await post('export_import',outputProfile()),artifact=s.import_artifact;const bytes=Uint8Array.from(atob(artifact.data),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='棚卸取込_'+s.id+'_v'+artifact.result_version+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
function restoreOutput(profile){$('output-spec').value=profile.specification;$('output-encoding').value=profile.encoding;$('output-header').value=profile.header?'yes':'no';$('output-mode').value=profile.quantity_mode;$('output-columns').replaceChildren();for(const col of profile.columns){addOutputColumn(col.name,col.source||'constant');if('constant'in col)$('output-columns').lastChild.children[2].value=col.constant;}}
addOutputColumn('商品番号','code');addOutputColumn('数量','quantity');
bind('output-from-source',()=>{const s=current();if(!s)throw Error('棚卸を選択してください');const columns=s.columns||{code:'商品番号',name:'名称',baseline:'数量'};restoreOutput({specification:'利用者回答: 商品コード・商品名・棚卸実数、ヘッダーあり。元CSV列名/文字コードを仮用。検証先で確認が必要',encoding:s.encoding,header:true,quantity_mode:'absolute',columns:[{name:columns.code,source:'code'},{name:columns.name,source:'name'},{name:columns.baseline,source:'quantity'}]});});

const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const {mkdtempSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const path=require('node:path');
const assert=require('node:assert/strict');

(async()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'stocktake-browser-'));
 const server=spawn(process.env.PYTHON||'python',['-m','inventory.server','--port','0','--db',path.join(dir,'test.db')]);
 let browser;
 try{
  const url=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('server startup timeout')),15000);server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127.0.0.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});server.on('exit',code=>{clearTimeout(timer);reject(Error('server exited '+code));});});
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  const context=await browser.newContext({viewport:{width:1280,height:1000},acceptDownloads:true});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
  const idle=()=>page.waitForFunction(()=>document.querySelector('#tab-status').textContent.includes('このタブ')&&!document.querySelector('#save').disabled);
  await page.goto(url);await idle();
  await page.locator('#actor').fill('現場担当A');
  const csv={name:'custom.csv',mimeType:'text/csv',buffer:Buffer.from('資材番号,資材名,在庫数\n000001,架空の発送箱,10\n000002,架空のラベル,20\n000003,架空の緩衝材,0\n')};await page.locator('#file').setInputFiles(csv);await page.locator('#inspect').click();await idle();
  await page.locator('#map-code').selectOption('資材番号');await page.locator('#map-name').selectOption('資材名');await page.locator('#map-baseline').selectOption('在庫数');
  await page.locator('#preview').click();await page.waitForFunction(()=>!document.querySelector('#create').disabled);
  await page.locator('#save-profile').click();await idle();
  assert.ok(await page.evaluate(()=>localStorage.getItem('inventory.csv-profile.v1')));
  await page.locator('#create').click();await idle();assert.equal(await page.locator('#rows tr').count(),3);
  await page.locator('#code').fill('000001');await page.locator('#quantity').fill('8');
  await page.reload();await idle();assert.equal(await page.locator('#quantity').inputValue(),'8');assert.equal(await page.locator('#actor').inputValue(),'現場担当A');
  await page.locator('#file').setInputFiles(csv);await page.locator('#inspect').click();await idle();assert.equal(await page.locator('#map-code').inputValue(),'資材番号');
  const other=await context.newPage();await other.goto(url);await other.waitForFunction(()=>document.querySelector('#tab-status').textContent.includes('ほかのタブ'));
  assert.ok(await other.locator('#save').isDisabled());assert.ok(await other.locator('#quantity').isDisabled());
  await other.close();
  await page.locator('#save').click();await idle();assert.equal(await page.locator('#quantity').inputValue(),'');
  for(const [code,qty] of [['000002','20'],['000003','0']]){await page.locator('#code').fill(code);await page.locator('#quantity').fill(qty);await page.locator('#save').click();await idle();}
  await page.locator('#filter').selectOption('difference');assert.equal(await page.locator('#rows tr').count(),1);
  await page.locator('#filter').selectOption('missing');assert.equal(await page.locator('#rows tr').count(),0);
  await page.locator('#filter').selectOption('all');await page.locator('#search').fill('ラベル');assert.equal(await page.locator('#rows tr').count(),1);await page.locator('#search').fill('');
  await page.locator('#complete').click();await idle();await page.locator('#finalize').click();await idle();
  const downloaded=page.waitForEvent('download');await page.locator('#export').click();const download=await downloaded;assert.ok(download.suggestedFilename().startsWith('確認用_'));await idle();
  await page.screenshot({path:path.join(dir,'screen.png'),fullPage:true});
  // A waiting tab acquires the workspace after the owning document closes.
  const next=await context.newPage();await next.goto(url);await next.waitForFunction(()=>document.querySelector('#save').disabled);
  await page.close();await next.waitForFunction(()=>document.querySelector('#tab-status').textContent.includes('このタブ')&&!document.querySelector('#save').disabled);
  assert.deepEqual(errors,[]);
  console.log('PASS: import, profile, draft reload, tab lock/handoff, count, filters, finalize, download; no page errors');
 }finally{if(browser)await browser.close();server.kill();await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));rmSync(dir,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});

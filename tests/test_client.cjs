const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function context(){
 const elements=new Map(),storage=new Map(),calls=[];
 const elem=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,replaceChildren(){},append(){},addEventListener(){}});return elements.get(id);};
 const session={id:'s',revision:0,locations:['A'],completed:[],records:[],items:[],summary:[],state:'counting',audit:[]};let fail=true;
 const ctx={document:{getElementById:elem,querySelectorAll:()=>[],createElement:()=>({append(){}})},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},crypto:{randomUUID:()=> 'stable-id'},AbortController,setTimeout,clearTimeout,Option:function(){},confirm:()=>true,prompt:()=>'',console,
 fetch:async(url,options)=>{if(options?.method==='POST'){calls.push(JSON.parse(options.body));if(fail)throw Error('lost response');return{ok:true,json:async()=>({id:'s'})};}return{ok:true,json:async()=>({sessions:[session],token:'new-token'})};}};
 ctx.navigator={locks:{request:(_name,fn)=>fn()}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('inventory/app.js','utf8'),ctx);
 return{ctx,calls,storage,elem,recover:()=>{fail=false;}};
}
test('lost response retains exact request across retry',async()=>{
 const c=context();await vm.runInContext('refresh()',c.ctx);c.elem('session').value='s';c.elem('actor').value='test';
 await assert.rejects(vm.runInContext("post('finalize')",c.ctx));assert.equal(c.storage.size,1);
 c.recover();await vm.runInContext('sendPending()',c.ctx);assert.deepEqual(c.calls[0],c.calls[1]);assert.equal(c.storage.size,0);
});
test('local storage failure prevents send',async()=>{
 const c=context();await vm.runInContext('refresh()',c.ctx);c.ctx.localStorage.setItem=()=>{throw Error('quota')};
 await assert.rejects(vm.runInContext("post('finalize')",c.ctx));assert.equal(c.calls.length,0);
});

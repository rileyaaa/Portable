const fs=require('fs');
const path=require('path');
const vm=require('vm');
const root=path.resolve(__dirname, '..');
process.chdir(root);
const textFiles=['index.html','README.md','app/app.js','app/converter.js','app/style.css','test/smoke.js'];
const q3='?'.repeat(3), oldKey='token_'+'hint';
const badPatterns=[
  {name:'mojibake_question_triplet', re:new RegExp('\\'+q3.split('').join('\\'))},
  {name:'unicode_replacement_char', re:/\uFFFD/},
  {name:'debug_statement', re:new RegExp('\\b'+'debug'+'ger'+'\\b')},
  {name:'task_marker', re:new RegExp('\\b(?:TO'+'DO|FIX'+'ME)\\b','i')},
  {name:'runtime_network_call', re:/\bfetch\s*\(/},
  {name:'local_store_usage', re:/\blocalStorage\s*\./},
  {name:'session_store_usage', re:/\bsessionStorage\s*\./},
  {name:'indexed_db_usage', re:/\bindexedDB\s*\./},
  {name:'service_worker_register', re:/serviceWorker\s*\.\s*register/},
  {name:'cache_api_usage', re:/\bcaches\s*\./},
];
let ok=true;
for (const f of textFiles) {
  const s=fs.readFileSync(f,'utf8');
  for (const p of badPatterns) {
    if (p.re.test(s)) { console.error(`[BAD_SOURCE] ${f}: ${p.name}`); ok=false; }
  }
}
if (fs.readFileSync('app/converter.js','utf8').includes(oldKey)) { console.error('[BAD_SOURCE] converter contains old hint field literal'); ok=false; }
const html=fs.readFileSync('index.html','utf8');
for (const m of html.matchAll(/<(?:script|link)[^>]+(?:src|href)="([^"]+)"/g)) {
  const ref=m[1].replace(/^\.\//,'');
  if(!fs.existsSync(ref)) { console.error(`[MISSING_ASSET] ${ref}`); ok=false; }
}
for (const id of ['fileInput','chooseFileBtn','convertBtn','downloadZipBtn','jwtToggle','rulesToggle','vaultToggle','completeToggle','preview']) {
  if(!html.includes(`id="${id}"`)) { console.error(`[MISSING_ID] ${id}`); ok=false; }
}
const ctx={window:{}, console:{log(){},error(){},warn(){}}, atob:s=>Buffer.from(s,'base64').toString('binary'), btoa:s=>Buffer.from(s,'binary').toString('base64'), crypto:{}}; ctx.window=ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync('app/converter.js','utf8'), ctx);
const cases=[...fs.readdirSync('.').filter(f=>f.endsWith('.json')), 'test/multi-array-sample.json'];
const ell=String.fromCharCode(0x2026), rep=String.fromCharCode(0xfffd);
for (const f of cases) {
  const c=ctx.AccountConverter.canonicalize(fs.readFileSync(f,'utf8'));
  const outs=ctx.AccountConverter.convertAll(c);
  const ids=new Set(outs.map(o=>o.id));
  for (const id of ['sub2api','env','proxy-json','litellm','one-api','curl','http','report','cherry-studio','chatbox','lobechat']) if(!ids.has(id)){ console.error(`[MISSING_OUTPUT] ${f}: ${id}`); ok=false; }
  for (const o of outs) {
    for (const [name, needle] of [[q3,q3], ['replacement',rep], ['ellipsis',ell], [oldKey,oldKey]]) {
      if(o.content.includes(needle)) { console.error(`[BAD_OUTPUT] ${f}/${o.id}: ${name}`); ok=false; }
    }
  }
  const report=JSON.parse(outs.find(o=>o.id==='report').content);
  if(report.accounts.length!==c.accounts.length){ console.error(`[BAD_REPORT_COUNT] ${f}`); ok=false; }
  const sub=JSON.parse(outs.find(o=>o.id==='sub2api').content);
  for (const a of sub.accounts) {
    if(a.extra && !a.extra.token_fingerprint) { console.error(`[MISSING_FINGERPRINT] ${f}/${a.name}`); ok=false; }
    if(a.extra && oldKey in a.extra) { console.error(`[OLD_HINT_FIELD] ${f}/${a.name}`); ok=false; }
  }
}
// Use the real page handlers with inert DOM objects. Only synthetic accounts
// are supplied, and no DOM event, browser, network or clipboard is executed.
const assert=require('node:assert/strict');
function converterPageFixture(crypto={}){
  const elements=new Map();
  const element=selector=>{
    if(!elements.has(selector)) elements.set(selector, {
      value:'', checked:false, innerHTML:'', textContent:'',
      classList:{add(){},remove(){},toggle(){}}, events:Object.create(null),
      addEventListener(name,handler){this.events[name]=handler;},
      querySelectorAll(){return [];}, click(){},
    });
    return elements.get(selector);
  };
  const page={document:{querySelector:element,querySelectorAll(){return [];}},
    console:{log(){},error(){},warn(){}}, setTimeout(){}, TextEncoder, TextDecoder,
    atob:s=>Buffer.from(s,'base64').toString('binary'),
    btoa:s=>Buffer.from(s,'binary').toString('base64'), crypto};
  page.window=page; vm.createContext(page);
  vm.runInContext(fs.readFileSync('app/converter.js','utf8'),page);
  vm.runInContext(fs.readFileSync('app/app.js','utf8'),page);
  return {page,element};
}
const uiChecks=[
  ['imported account type is text, not HTML',()=>{
    const {element}=converterPageFixture();
    const marker='<img src="data:,synthetic" onerror="window.__synthetic_type_marker=1">';
    element('#inputText').value=JSON.stringify({accounts:[{
      name:'synthetic',type:marker,credentials:{api_key:'synthetic-not-a-key'},
    }]});
    element('#convertBtn').onclick();
    const html=element('#detected').innerHTML;
    assert.ok(html.includes('synthetic'));
    assert.ok(html.includes('&lt;img'));
    assert.ok(!html.includes(marker));
    assert.equal(JSON.parse(element('#inputText').value).accounts[0].type,marker);
  }],
  ['ordinary and mixed account types still render',()=>{
    const {element}=converterPageFixture();
    element('#inputText').value=JSON.stringify({accounts:[
      {name:'api',type:'api_key',credentials:{api_key:'synthetic-not-a-key'}},
      {name:'oauth',type:'oauth',credentials:{access_token:'synthetic-not-a-token'}},
    ]});
    element('#convertBtn').onclick();
    assert.ok(element('#detected').innerHTML.includes('api_key/oauth'));
    assert.ok(element('#cards').innerHTML.includes('data-i="0"'));
  }],
  ['ZIP declares UTF-8 for local and central names',()=>{
    const {page}=converterPageFixture();
    const names=['plain/account.json','\u4fbf\u643a/\u8d26\u53f7.json','emoji-\ud83d\udce6.json'];
    page.syntheticFiles=Object.fromEntries(names.map(name=>[name,'synthetic-'+name]));
    const bytes=Buffer.from(vm.runInContext('makeZip(syntheticFiles)',page));
    const end=bytes.length-22;
    assert.equal(bytes.readUInt32LE(end),0x06054b50);
    assert.equal(bytes.readUInt16LE(end+10),names.length);
    let cursor=bytes.readUInt32LE(end+16);
    for(const name of names){
      assert.equal(bytes.readUInt32LE(cursor),0x02014b50);
      assert.equal(bytes.readUInt16LE(cursor+8)&0x800,0x800);
      const nameLength=bytes.readUInt16LE(cursor+28);
      assert.equal(bytes.subarray(cursor+46,cursor+46+nameLength).toString('utf8'),name);
      const local=bytes.readUInt32LE(cursor+42);
      assert.equal(bytes.readUInt32LE(local),0x04034b50);
      assert.equal(bytes.readUInt16LE(local+6)&0x800,0x800);
      assert.equal(bytes.readUInt16LE(local+26),nameLength);
      assert.equal(bytes.subarray(local+30,local+30+nameLength).toString('utf8'),name);
      const dataStart=local+30+nameLength+bytes.readUInt16LE(local+28);
      const dataSize=bytes.readUInt32LE(local+22);
      assert.equal(bytes.subarray(dataStart,dataStart+dataSize).toString('utf8'),'synthetic-'+name);
      assert.equal(bytes.readUInt32LE(local+14),bytes.readUInt32LE(cursor+16));
      cursor+=46+nameLength+bytes.readUInt16LE(cursor+30)+bytes.readUInt16LE(cursor+32);
    }
    assert.equal(cursor,end);
  }],
  ['empty ZIP remains a valid empty archive',()=>{
    const {page}=converterPageFixture();
    const bytes=Buffer.from(vm.runInContext('makeZip({})',page));
    assert.equal(bytes.length,22);
    assert.equal(bytes.readUInt32LE(0),0x06054b50);
    assert.equal(bytes.readUInt16LE(10),0);
  }],
];
for(const [name,check] of uiChecks){
  try{check(); console.log('PASS converter UI/ZIP: '+name);}
  catch(error){ok=false; console.error('[CONVERTER_UI_ZIP] '+name+': '+error.message);}
}

// Exercise asynchronous vault handlers with real Web Crypto and synthetic data.
// Capture downloads in memory; no credentials, file dialogs or browser state.
const webcrypto=require('node:crypto').webcrypto;
function vaultFixture(crypto=webcrypto){
  const fixture=converterPageFixture(crypto);
  fixture.downloads=[];
  fixture.page.syntheticDownloads=fixture.downloads;
  vm.runInContext('downloadText=(filename,content,type)=>syntheticDownloads.push({filename,content,type})',fixture.page);
  fixture.element('#vaultPass').value='synthetic-test-password';
  return fixture;
}
function loadSyntheticAccount(fixture, name='synthetic-account'){
  fixture.element('#inputText').value=JSON.stringify({name,api_key:'synthetic-not-a-key'});
  fixture.element('#convertBtn').onclick();
  return vm.runInContext('JSON.stringify(state.canon)',fixture.page);
}
async function decryptSyntheticVault(vault,password='synthetic-test-password'){
  assert.equal(vault.format,'ai-account-converter-vault');
  assert.equal(vault.version,1);
  assert.equal(vault.kdf,'PBKDF2-SHA256-150000');
  assert.equal(vault.cipher,'AES-GCM');
  const salt=Buffer.from(vault.salt,'base64'),iv=Buffer.from(vault.iv,'base64');
  assert.equal(salt.length,16); assert.equal(iv.length,12);
  const base=await webcrypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
  const key=await webcrypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:150000,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['decrypt']);
  const plain=await webcrypto.subtle.decrypt({name:'AES-GCM',iv},key,Buffer.from(vault.data,'base64'));
  return JSON.parse(new TextDecoder().decode(plain));
}
async function checkExportSnapshot(change){
  let release,started;
  const ready=new Promise(resolve=>started=resolve), gate=new Promise(resolve=>release=resolve);
  const fixture=vaultFixture({
    getRandomValues:webcrypto.getRandomValues.bind(webcrypto),
    subtle:{
      importKey:webcrypto.subtle.importKey.bind(webcrypto.subtle),
      encrypt:webcrypto.subtle.encrypt.bind(webcrypto.subtle),
      deriveKey:async(...args)=>{started();await gate;return webcrypto.subtle.deriveKey(...args);},
    },
  });
  const expected=loadSyntheticAccount(fixture,'original-synthetic');
  const exporting=fixture.element('#exportVaultBtn').onclick();
  await ready;
  try{change(fixture);}finally{release();}
  await exporting;
  assert.equal(fixture.downloads.length,1,'Exactly one export is required');
  const restored=await decryptSyntheticVault(JSON.parse(fixture.downloads[0].content));
  assert.equal(JSON.stringify(restored.canon),expected,'Export must use the account snapshot selected at click time');
  return fixture;
}
const reviewChecks=[
  ['wrapper arrays ignore non-array metadata',()=>{
    const {page}=converterPageFixture();
    const account={name:'synthetic-wrapper',api_key:'synthetic-not-a-key'};
    for(const input of [
      {data:{count:1},items:[account]},
      {data:'metadata',tokens:[account]},
      {items:'metadata',tokens:[account]},
      {data:42,items:false,tokens:[account]},
    ]){
      const result=page.AccountConverter.canonicalize(JSON.stringify(input));
      assert.equal(result.accounts.length,1);
      assert.equal(result.accounts[0].name,account.name);
    }
  }],
  ['wrapper precedence and ordinary arrays are unchanged',()=>{
    const {page}=converterPageFixture();
    const first={name:'first',api_key:'synthetic-first'},second={name:'second',api_key:'synthetic-second'};
    for(const key of ['data','items','tokens']){
      assert.equal(page.AccountConverter.canonicalize(JSON.stringify({[key]:[first]})).accounts[0].name,'first');
    }
    assert.equal(page.AccountConverter.canonicalize(JSON.stringify({data:[first],items:[second],tokens:[second]})).accounts[0].name,'first');
    assert.throws(()=>page.AccountConverter.canonicalize(JSON.stringify({data:[],items:[second]})));
  }],
  ['vault byte encoding matches independent Base64 at chunk boundaries',()=>{
    const {page}=converterPageFixture();
    for(const size of [0,1,2,3,16383,16384,16385,32769,1048576]){
      const data=Uint8Array.from({length:size},(_,i)=>(i*37+19)&255);
      page.syntheticBytes=data;
      assert.equal(vm.runInContext('bytesToBase64(syntheticBytes)',page),Buffer.from(data).toString('base64'));
    }
  }],
  ['large vault export round-trips actual encrypted account data',async()=>{
    const fixture=vaultFixture();
    fixture.element('#inputText').value=JSON.stringify(Array.from({length:24},(_,i)=>({
      name:'synthetic-'+i,access_token:'synthetic-'+('a'.repeat(4096)),refresh_token:'synthetic-refresh-'+i,
    })));
    fixture.element('#convertBtn').onclick();
    const expected=vm.runInContext('JSON.stringify(state.canon)',fixture.page);
    assert.ok(Buffer.byteLength(expected)>300000);
    await fixture.element('#exportVaultBtn').onclick();
    assert.equal(fixture.downloads.length,1,'Large vault must not fail from argument-stack overflow');
    const restored=await decryptSyntheticVault(JSON.parse(fixture.downloads[0].content));
    assert.equal(JSON.stringify(restored.canon),expected);
  }],
  ['clear during key derivation cannot replace export with an empty vault',async()=>{
    const fixture=await checkExportSnapshot(f=>f.element('#clearBtn').onclick());
    assert.equal(vm.runInContext('state.canon',fixture.page),null);
  }],
  ['another conversion during key derivation cannot change the selected export',async()=>{
    const fixture=await checkExportSnapshot(f=>loadSyntheticAccount(f,'new-synthetic'));
    assert.equal(vm.runInContext('state.canon.accounts[0].name',fixture.page),'new-synthetic');
  }],
  ['vault format, import compatibility and wrong-password rejection remain intact',async()=>{
    const fixture=vaultFixture();
    const expected=loadSyntheticAccount(fixture,'\u5408\u6210-\ud83d\udd10');
    await fixture.element('#exportVaultBtn').onclick();
    assert.equal(fixture.downloads.length,1);
    const vault=JSON.parse(fixture.downloads[0].content);
    assert.equal(JSON.stringify((await decryptSyntheticVault(vault)).canon),expected);
    await assert.rejects(decryptSyntheticVault(vault,'wrong-synthetic-password'));
    let loaded;
    fixture.page.FileReader=class{
      readAsText(file){this.result=file.syntheticText;loaded=this.onload();}
    };
    fixture.element('#clearBtn').onclick();
    fixture.element('#vaultFileInput').onchange({target:{files:[{syntheticText:JSON.stringify(vault)}]}});
    await loaded;
    assert.equal(vm.runInContext('JSON.stringify(state.canon)',fixture.page),expected);
  }],
  ['failed vault import preserves the current account, output and input',async()=>{
    const fixture=vaultFixture();
    loadSyntheticAccount(fixture,'keep-existing-synthetic');
    const before=vm.runInContext('JSON.stringify(state)',fixture.page);
    const inputBefore=fixture.element('#inputText').value;
    const valid=JSON.parse(vm.runInContext('JSON.stringify(state.canon)',fixture.page));
    const variants=[null,{...valid,hints:null},{...valid,accounts:[null]},
      {...valid,accounts:[{...valid.accounts[0],plan:{toString:1}}]}];
    for(const canon of variants){
      const salt=webcrypto.getRandomValues(new Uint8Array(16)),iv=webcrypto.getRandomValues(new Uint8Array(12));
      const base=await webcrypto.subtle.importKey('raw',new TextEncoder().encode('synthetic-test-password'),'PBKDF2',false,['deriveKey']);
      const key=await webcrypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:150000,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['encrypt']);
      const encrypted=await webcrypto.subtle.encrypt({name:'AES-GCM',iv},key,new TextEncoder().encode(JSON.stringify({version:1,canon})));
      const vault={format:'ai-account-converter-vault',version:1,kdf:'PBKDF2-SHA256-150000',cipher:'AES-GCM',
        salt:Buffer.from(salt).toString('base64'),iv:Buffer.from(iv).toString('base64'),data:Buffer.from(encrypted).toString('base64')};
      let loaded;
      fixture.page.FileReader=class{readAsText(file){this.result=file.syntheticText;loaded=this.onload();}};
      fixture.element('#vaultFileInput').onchange({target:{files:[{syntheticText:JSON.stringify(vault)}]}});
      await loaded;
      assert.equal(vm.runInContext('JSON.stringify(state)',fixture.page),before,'Rejected vault must preserve existing state');
      assert.equal(fixture.element('#inputText').value,inputBefore,'Rejected vault must preserve existing input');
    }
  }],
  ['missing account or password cannot start a vault download',async()=>{
    const fixture=vaultFixture({getRandomValues(){throw new Error('Unexpected crypto execution');}});
    await fixture.element('#exportVaultBtn').onclick();
    assert.equal(fixture.downloads.length,0);
    loadSyntheticAccount(fixture);
    fixture.element('#vaultPass').value='';
    await fixture.element('#exportVaultBtn').onclick();
    assert.equal(fixture.downloads.length,0);
  }],
];

// Reproduce interleaved imports without timers: pause real key derivation at a
// controlled boundary, then exercise the user's actual clear/convert handlers.
function startSyntheticImport(fixture, vault){
  let loaded;
  fixture.page.FileReader=class{
    readAsText(file){this.result=file.syntheticText;loaded=this.onload();}
  };
  fixture.element('#vaultFileInput').onchange({target:{files:[{syntheticText:vault}]}});
  return loaded;
}
async function syntheticVault(name){
  const fixture=vaultFixture();
  loadSyntheticAccount(fixture,name);
  await fixture.element('#exportVaultBtn').onclick();
  assert.equal(fixture.downloads.length,1);
  return fixture.downloads[0].content;
}
function pausedImportFixture(){
  let release,started,first=true;
  const ready=new Promise(resolve=>started=resolve),gate=new Promise(resolve=>release=resolve);
  const fixture=vaultFixture({
    getRandomValues:webcrypto.getRandomValues.bind(webcrypto),
    subtle:{
      importKey:webcrypto.subtle.importKey.bind(webcrypto.subtle),
      decrypt:webcrypto.subtle.decrypt.bind(webcrypto.subtle),
      deriveKey:async(...args)=>{
        if(first){first=false;started();await gate;}
        return webcrypto.subtle.deriveKey(...args);
      },
    },
  });
  return {fixture,ready,release:()=>release()};
}
async function checkCancelledImport(change){
  const vault=await syntheticVault('pending-import');
  const {fixture,ready,release}=pausedImportFixture();
  loadSyntheticAccount(fixture,'current-account');
  const pending=startSyntheticImport(fixture,vault);
  await ready;
  change(fixture);
  const expected=vm.runInContext('JSON.stringify(state)',fixture.page);
  const expectedInput=fixture.element('#inputText').value;
  release();await pending;
  assert.ok(vm.runInContext('JSON.stringify(state)',fixture.page)===expected,
    'An older import must not overwrite a newer user decision');
  assert.equal(fixture.element('#inputText').value,expectedInput);
}
reviewChecks.push(
  ['clear cancels an in-flight decrypted vault import',async()=>{
    await checkCancelledImport(f=>f.element('#clearBtn').onclick());
  }],
  ['conversion or typed input cancels an older vault import',async()=>{
    await checkCancelledImport(f=>loadSyntheticAccount(f,'new-conversion'));
    await checkCancelledImport(f=>{
      f.element('#inputText').value='new unsaved synthetic input';
      f.element('#inputText').events.input?.();
    });
  }],
  ['newest selected vault wins even when the older crypto finishes later',async()=>{
    const oldVault=await syntheticVault('older-selection'),newVault=await syntheticVault('newer-selection');
    const {fixture,ready,release}=pausedImportFixture();
    loadSyntheticAccount(fixture,'current-account');
    const oldPending=startSyntheticImport(fixture,oldVault);
    await ready;
    await startSyntheticImport(fixture,newVault);
    assert.equal(vm.runInContext('state.canon.accounts[0].name',fixture.page),'newer-selection');
    release();await oldPending;
    assert.equal(vm.runInContext('state.canon.accounts[0].name',fixture.page),'newer-selection');
  }],
  ['out-of-order ordinary FileReader completion preserves the latest selection',()=>{
    const fixture=vaultFixture(),readers=[];
    fixture.page.FileReader=class{
      readAsText(file){this.result=file.syntheticText;readers.push(this);}
    };
    for(const name of ['older-file','newer-file']){
      fixture.element('#fileInput').onchange({target:{files:[{name,
        syntheticText:JSON.stringify({name,api_key:'synthetic-not-a-key'})}]}});
    }
    readers[1].onload();readers[0].onload();
    assert.equal(vm.runInContext('state.canon.accounts[0].name',fixture.page),'newer-file');
  }],
  ['clear cancels an ordinary pending file read and its stale error',()=>{
    const fixture=vaultFixture();let reader;
    fixture.page.FileReader=class{
      readAsText(file){this.result=file.syntheticText;reader=this;}
    };
    loadSyntheticAccount(fixture,'current-account');
    fixture.element('#fileInput').onchange({target:{files:[{name:'old-file',
      syntheticText:JSON.stringify({name:'old-file',api_key:'synthetic-not-a-key'})}]}});
    fixture.element('#clearBtn').onclick();
    const toast=fixture.element('#toast').textContent;
    reader.onload();reader.onerror();
    assert.equal(vm.runInContext('state.canon',fixture.page),null);
    assert.equal(fixture.element('#inputText').value,'');
    assert.equal(fixture.element('#toast').textContent,toast);
  }],
);

(async()=>{
  for(const [name,check] of reviewChecks){
    try{await check();console.log('PASS converter review: '+name);}
    catch(error){ok=false;console.error('[CONVERTER_REVIEW] '+name+': '+error.message);}
  }
  if(!ok){process.exitCode=1;return;}
  console.log('static audit passed');
})().catch(error=>{console.error('[CONVERTER_REVIEW] '+error.name);process.exitCode=1;});

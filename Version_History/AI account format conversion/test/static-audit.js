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
function converterPageFixture(){
  const elements=new Map();
  const element=selector=>{
    if(!elements.has(selector)) elements.set(selector, {
      value:'', checked:false, innerHTML:'', textContent:'',
      classList:{add(){},remove(){},toggle(){}}, addEventListener(){},
      querySelectorAll(){return [];}, click(){},
    });
    return elements.get(selector);
  };
  const page={document:{querySelector:element,querySelectorAll(){return [];}},
    console:{log(){},error(){},warn(){}}, setTimeout(){}, TextEncoder, TextDecoder,
    atob:s=>Buffer.from(s,'base64').toString('binary'),
    btoa:s=>Buffer.from(s,'binary').toString('base64'), crypto:{}};
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

if(!ok) process.exit(1);
console.log('static audit passed');

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
if(!ok) process.exit(1);
console.log('static audit passed');

const fs=require('fs'), vm=require('vm'), path=require('path');
process.chdir(path.resolve(__dirname, '..'));
const ctx={window:{}, console, atob:s=>Buffer.from(s,'base64').toString('binary'), btoa:s=>Buffer.from(s,'binary').toString('base64'), crypto:{}}; ctx.window=ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync('app/converter.js','utf8'), ctx);
let ok=true;
const files=[...fs.readdirSync('.').filter(f=>f.endsWith('.json')), 'test/multi-array-sample.json'];
const ell=String.fromCharCode(0x2026), rep=String.fromCharCode(0xfffd);
for (const f of files) {
  const raw=fs.readFileSync(f,'utf8');
  const c=ctx.AccountConverter.canonicalize(raw);
  const outs=ctx.AccountConverter.convertAll(c);
  const ids=outs.map(o=>o.id);
  const required=['sub2api','env','proxy-json','litellm','one-api','curl','http','report','cherry-studio','chatbox','lobechat'];
  if(c.accounts.some(a=>a.type==='oauth')) required.push('codex-auth','oauth');
  if(c.accounts.length>1) required.push('batch-files-pack');
  if(c.accounts.filter(a=>a.type==='oauth').length>1) required.push('codex-auth-list');
  const miss=required.filter(x=>!ids.includes(x));
  const report=JSON.parse(outs.find(o=>o.id==='report').content);
  const badOut=outs.filter(o=>o.content.includes('?'.repeat(3))||o.content.includes(rep)||o.content.includes('token_'+'hint')||o.content.includes(ell)).map(o=>o.id);
  const sub=JSON.parse(outs.find(o=>o.id==='sub2api').content);
  const hasFingerprint=sub.accounts.every(a=>!a.extra || !('token_'+'hint' in a.extra));
  console.log(`${f}: ${c.source}, sources=${c.sources.join('+')}, accounts=${c.accounts.length}, outputs=${outs.length}, report=${report.accounts.length}, missing=${miss.join('|')||'-'}, bad=${badOut.join('|')||'-'}`);
  if(miss.length || report.accounts.length!==c.accounts.length || badOut.length || !hasFingerprint) ok=false;
  if(f.includes('multi-array') && c.accounts.length < 4) { console.error('multi-array account count too low'); ok=false; }
}
const mapped=ctx.AccountConverter.ruleMapObject({token:'abc', mail:'a@b.c'}, {token:'access_token', mail:'email'});
if(mapped.access_token!=='abc'||mapped.email!=='a@b.c'){ console.error('ruleMapObject failed'); ok=false; }
if(!ok) process.exit(1);


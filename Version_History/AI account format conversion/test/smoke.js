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
// Synthetic input/rule tests; no account service, browser or network access.
const assert=require('node:assert/strict');
const C=ctx.AccountConverter;
const plain=value=>JSON.parse(JSON.stringify(value));
const api=(name='fixture')=>({name,api_key:'synthetic-only-'+name});
const inputCases=[
  ['items array is selected after data metadata',()=>{
    const c=C.canonicalize(JSON.stringify({data:{count:1},items:[api()]}));
    assert.equal(c.accounts.length,1);assert.equal(c.accounts[0].api_key,'synthetic-only-fixture');
  }],
  ['tokens array is selected after items metadata',()=>{
    const c=C.canonicalize(JSON.stringify({items:'metadata',tokens:[api()]}));
    assert.equal(c.accounts.length,1);
  }],
  ['tokens array is selected after two metadata fields',()=>{
    const c=C.canonicalize(JSON.stringify({data:'metadata',items:{count:1},tokens:[api()]}));
    assert.equal(c.accounts.length,1);
  }],
  ['all ordinary wrappers remain supported',()=>{
    for(const key of ['data','items','tokens']){
      const c=C.canonicalize(JSON.stringify({[key]:[api()]}));
      assert.equal(c.source,'wrapped_array');assert.equal(c.accounts.length,1);
      assert.ok(C.convertAll(c).some(o=>o.id==='sub2api'));
    }
  }],
  ['nested wrappers select their actual arrays',()=>{
    const c=C.canonicalize(JSON.stringify({data:[{data:{count:1},items:[api('nested')]}]}));
    assert.equal(c.accounts[0].name,'nested');assert.equal(c.accounts.length,1);
  }],
  ['multiple array wrapper precedence is unchanged',()=>{
    const c=C.canonicalize(JSON.stringify({data:[api('first')],items:[api('second')],tokens:[api('third')]}));
    assert.equal(c.accounts.length,1);assert.equal(c.accounts[0].name,'first');
  }],
  ['empty rules preserve prototype-named JSON fields',()=>{
    const data=JSON.parse('{"constructor":"ctor","toString":"text","__proto__":{"note":"keep"},"hasOwnProperty":"own"}');
    assert.deepEqual(plain(C.ruleMapObject(data,{})),data);
  }],
  ['mapping to __proto__ creates ordinary own data',()=>{
    const data={metadata:{api_key:'synthetic-only'}};
    const out=C.ruleMapObject(data,{metadata:'__proto__'});
    assert.equal(Object.hasOwn(out,'__proto__'),true);
    assert.equal(out.api_key,undefined);
    assert.deepEqual(plain(out),JSON.parse('{"__proto__":{"api_key":"synthetic-only"}}'));
    assert.equal(Object.getOwnPropertyDescriptor(out,'__proto__').enumerable,true);
  }],
  ['own prototype-named rules remain valid',()=>{
    const rules=JSON.parse('{"constructor":"name","__proto__":"extra"}');
    const data=JSON.parse('{"constructor":"fixture","__proto__":{"note":"keep"}}');
    assert.deepEqual(plain(C.ruleMapObject(data,rules)),{name:'fixture',extra:{note:'keep'}});
  }],
  ['mapping recurses through arrays without mutating input',()=>{
    const data=JSON.parse('[{"token":"synthetic-only","extra":{"toString":"keep","__proto__":{"note":"keep"}}},null,7]');
    const before=JSON.stringify(data);
    const out=plain(C.ruleMapObject(data,{token:'api_key'}));
    assert.equal(JSON.stringify(data),before);
    assert.equal(out[0].api_key,'synthetic-only');assert.deepEqual(out[0].extra,data[0].extra);
    assert.equal(out[1],null);assert.equal(out[2],7);
  }],
  ['inherited rules are not treated as mapping entries',()=>{
    const rules=Object.create({token:'api_key'});
    assert.deepEqual(plain(C.ruleMapObject({token:'synthetic-only'},rules)),{token:'synthetic-only'});
  }],
  ['normal mapping and empty target fallback remain unchanged',()=>{
    const out=C.ruleMapObject({token:'synthetic-only',mail:'test@example.invalid',keep:'value'},{token:'api_key',mail:'email',keep:''});
    assert.deepEqual(plain(out),{api_key:'synthetic-only',email:'test@example.invalid',keep:'value'});
    assert.equal(C.canonicalize(JSON.stringify(out)).accounts.length,1);
  }],
];
let inputPassed=0;
for(const [name,check] of inputCases){
  try{check();inputPassed++;console.log('PASS converter input/rules: '+name);}
  catch(error){ok=false;console.error('FAIL converter input/rules: '+name+' ('+error.name+')');}
}
console.log('CONVERTER_INPUT_RULE_CASES='+inputPassed+'/'+inputCases.length);

if(!ok) process.exit(1);


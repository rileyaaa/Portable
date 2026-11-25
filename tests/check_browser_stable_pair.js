'use strict';
// CI only. Compare real filtered MCP schemas and migrate an owned synthetic profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {EventEmitter} = require('node:events');
const bridge = require('../tool/automation/browser-bridge');
const [oldDeps, newDeps, oldExe, newExe, work] = process.argv.slice(2);
assert.equal(process.platform, 'win32');
assert.equal(process.argv.length, 7);
const root = path.resolve(__dirname, '..');
for (const dir of [oldDeps, newDeps, work]) bridge.checkedPath(root, dir, {directory:true});
for (const exe of [oldExe,newExe]) bridge.checkedPath(root,exe);

class MemoryTransport {
  constructor() { this.events = new EventEmitter(); }
  async start() {}
  async close() { this.onclose?.(); }
  async send(message) { this.events.emit('message',message); }
  request(message) {
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.events.off('message',handler);reject(Error('MCP schema timeout'));},10000);
      const handler=r=>{if(r.id===message.id){clearTimeout(timer);this.events.off('message',handler);resolve(r);}};
      this.events.on('message',handler);
      this.onmessage(message);
    });
  }
}
async function schema(deps, exe) {
  const {tools:{createConnection}}=require(path.join(deps,'playwright-core/lib/coreBundle'));
  const server=await createConnection({
    browser:{browserName:'chromium',isolated:false,userDataDir:path.join(work,'schema-profile'),
      launchOptions:{executablePath:exe,headless:true,chromiumSandbox:true},
      contextOptions:{acceptDownloads:false,serviceWorkers:'block'}},
    capabilities:[],webmcp:false,allowUnrestrictedFileAccess:false,
    outputDir:work,outputMaxSize:50*1024*1024,saveSession:false,codegen:'none',
  },()=>{throw Error('listing must not launch browser');});
  const inner=new MemoryTransport();
  const policy=new bridge.PolicyTransport(inner,work);
  try {
    await server.connect(policy);
    const init=await inner.request({jsonrpc:'2.0',id:1,method:'initialize',
      params:{protocolVersion:'2025-06-18',capabilities:{roots:{listChanged:true}},clientInfo:{name:'portable-compatibility',version:'1'}}});
    assert.ok(init.result,JSON.stringify(init));
    inner.onmessage({jsonrpc:'2.0',method:'notifications/initialized'});
    const response=await inner.request({jsonrpc:'2.0',id:2,method:'tools/list'});
    assert.ok(response.result,JSON.stringify(response));
    return Object.fromEntries(response.result.tools.map(t=>[t.name,t.inputSchema]));
  } finally { await server.close(); }
}
function compatible(oldValue,newValue,label) {
  assert.ok(newValue, 'removed schema: '+label);
  if (oldValue.type) assert.deepEqual(newValue.type,oldValue.type,label+' type');
  if (oldValue.enum) for (const v of oldValue.enum)
    assert.ok(newValue.enum?.includes(v),label+' removed enum '+v);
  if (oldValue.const!==undefined) assert.equal(newValue.const,oldValue.const,label+' const');
  const oldRequired=new Set(oldValue.required||[]);
  for (const p of newValue.required||[]) assert.ok(oldRequired.has(p),label+' added required '+p);
  for (const [p,v] of Object.entries(oldValue.properties||{}))
    compatible(v,newValue.properties?.[p],label+'.'+p);
  // Only filename is a reviewed new path argument, already normalized and
  // checked by the existing policy. Other optional additions need review.
  for (const p of Object.keys(newValue.properties||{}))
    if (!Object.hasOwn(oldValue.properties||{},p))
      assert.equal(p,'filename',label+' added optional argument '+p);
  if (oldValue.items) compatible(oldValue.items,newValue.items,label+'[]');
  // Do not silently discard or reinterpret compound schemas.
  const strip=v=>Array.isArray(v)?v.map(strip):v&&typeof v==='object'?
    Object.fromEntries(Object.entries(v).filter(([k])=>!['description','title','$schema'].includes(k)).map(([k,x])=>[k,strip(x)])):v;
  for(const k of ['oneOf','anyOf','allOf','not','pattern','minimum','maximum','minLength','maxLength','additionalProperties'])
    if(oldValue[k]!==undefined||newValue[k]!==undefined)
      assert.deepEqual(strip(newValue[k]),strip(oldValue[k]),label+' '+k);
}
async function main() {
  process.chdir(work);
  const old=await schema(oldDeps,oldExe),candidate=await schema(newDeps,newExe);
  console.log('MCP_OLD_TOOLS='+JSON.stringify(Object.keys(old).sort()));
  console.log('MCP_NEW_TOOLS='+JSON.stringify(Object.keys(candidate).sort()));
  assert.deepEqual(Object.keys(candidate).sort(),Object.keys(old).sort(),'filtered MCP tool set changed');
  for(const [name,s] of Object.entries(old)) {
    try { compatible(s,candidate[name],name); }
    catch(e) { console.log('MCP_SCHEMA_DIFF='+JSON.stringify({name,old:s,new:candidate[name]}));throw e; }
  }
  assert.ok(old.browser_navigate&&old.browser_click&&old.browser_snapshot&&old.browser_evaluate&&old.browser_close);
  console.log('MCP_REAL_FILTERED_SCHEMA_COMPATIBILITY=PASS');
  const server=http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html'});res.end('<title>Portable migration</title><button id="button" onclick="document.body.dataset.clicked=\'yes\'">Click</button>');});
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  try {
    const url='http://127.0.0.1:'+server.address().port;
    const profile=path.join(work,'profile'), downloads=path.join(work,'downloads'), cache=path.join(work,'cache'), crashes=path.join(work,'crashes');
    for(const p of [profile,downloads,cache,crashes])fs.mkdirSync(p,{recursive:true});
    for(const [deps,exe,version,old] of [[oldDeps,oldExe,'155.0.8059.12',true],[newDeps,newExe,'158.0.8127.88',false]]) {
      const {chromium}=require(path.join(deps,'playwright'));
      const context=await chromium.launchPersistentContext(profile,{
        executablePath:exe,headless:true,chromiumSandbox:true,downloadsPath:downloads,
        acceptDownloads:false,serviceWorkers:'block',
        args:['--no-proxy-server','--disk-cache-dir='+cache,'--crash-dumps-dir='+crashes,'--disable-breakpad'],
      });
      try {
        const page=context.pages()[0]||await context.newPage();
        await page.goto(url);
        const cdp=await context.newCDPSession(page);
        const info=await cdp.send('Browser.getVersion');
        assert.ok(info.product.endsWith('/'+version),JSON.stringify(info));
        await cdp.detach();
        if(old) {
          await page.evaluate(()=>{document.cookie='portable_migration=retained; max-age=3600; path=/';localStorage.setItem('portable','retained');});
        } else {
          assert.ok((await page.evaluate(()=>document.cookie)).includes('portable_migration=retained'));
          assert.equal(await page.evaluate(()=>localStorage.getItem('portable')),'retained');
        }
        await page.locator('#button').click();
        assert.equal(await page.evaluate(()=>document.body.dataset.clicked),'yes');
        await page.screenshot({path:path.join(work,old?'old.png':'stable.png')});
      } finally { await context.close(); }
    }
    console.log('REAL_CHROMIUM_OLD_TO_STABLE_PROFILE_COOKIE_STORAGE_CDP=PASS');
  } finally {await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{process.stderr.write(String(e.stack||e)+'\n');process.exitCode=1;});

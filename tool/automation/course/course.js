'use strict';
// Course owner is independent of the stdio client. No TCP server, CDP port,
// browser-state export, page navigation or arbitrary code endpoint.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const {checkedPath, checkTree, browserProxy} = require('../browser-bridge');
const ROOT = path.resolve(__dirname, '../../..');
const MAX_FRAME = 1024 * 1024;
const random = n => crypto.randomBytes(n).toString('hex');
class CourseError extends Error {}
const fail = message => { throw new CourseError(message); };
const assert = (condition, message) => { if (!condition) fail(message); };
const normalized = s => String(s).normalize('NFC').replace(/\s+/gu, ' ').trim();
const hash = s => crypto.createHash('sha256').update(s).digest('hex');
const hmac = (key, ...parts) => crypto.createHmac('sha256', key).update(JSON.stringify(parts)).digest('hex');
const equal = (a, b) => typeof a === 'string' && /^[0-9a-f]{64}$/.test(a) &&
    typeof b === 'string' && /^[0-9a-f]{64}$/.test(b) &&
    crypto.timingSafeEqual(Buffer.from(a,'hex'),Buffer.from(b,'hex'));
const alias = s => /^[a-z0-9][a-z0-9_-]{0,47}$/.test(s) && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/.test(s);
const validSession = s => /^[0-9a-f]{32}$/.test(s);
const samePath = (a,b) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();
const python = () => checkedPath(ROOT,path.join(ROOT,'tool/python/python.exe'));
function guard(mode, target) {
    const script = checkedPath(ROOT,path.join(__dirname,'path_guard.py'));
    const r = spawnSync(python(),['-I','-B',script,mode,target],{windowsHide:true,timeout:120000,encoding:'utf8'});
    assert(r.status === 0 && !r.error,'Course path verification refused.');
}
function stateFor(state,task,account) {
    assert(alias(task) && alias(account),'Invalid account aliases.');
    const expected = path.join(ROOT,'work','course-'+task,account);
    assert(samePath(state,expected),'Unexpected account directory.');
    return checkedPath(path.join(ROOT,'work'),expected,{directory:true});
}
function checkRuntime(state) {
    const runtime = checkedPath(state,'runtime',{directory:true});
    for (const key of ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR',
        'XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC']) {
        assert(process.env[key] && samePath(process.env[key],runtime),'Use the isolated course wrapper.');
    }
    guard('directory',runtime);
}
function scopeFor(origin,pagePath) {
    const u = new URL(origin);
    assert(['http:','https:'].includes(u.protocol) && !u.username && !u.password &&
        u.origin === origin && !u.search && !u.hash,'Use a canonical HTTP(S) origin.');
    assert(typeof pagePath === 'string' && pagePath.startsWith('/') &&
        !pagePath.startsWith('//') && !/[?#\\\x00-\x20]/.test(pagePath),'Use an exact canonical path without query.');
    const p = new URL(pagePath,u);
    assert(p.origin === u.origin && p.pathname === pagePath,'Unexpected normalized path.');
    return {origin:u.origin,pagePath};
}
function matching(url,scope) {
    try {
        const u = new URL(url);
        return u.origin === scope.origin && u.pathname === scope.pagePath && !u.username && !u.password;
    } catch { return false; }
}
function choiceFingerprint(stem,type,choices) {
    return hash(JSON.stringify([normalized(stem),type,choices.map(normalized)]));
}
function selector(s) {
    assert(typeof s === 'string' && s.length > 0 && s.length <= 500 && !/[\x00-\x1f]|>>/.test(s) &&
        !/^(body|html|\*)$/i.test(s.trim()),'Use a bounded CSS selector for the authorized content.');
    return 'css='+s;
}
const str = {type:'string',minLength:1,maxLength:500};
const boolean = {type:'boolean'};
const questionProps = {questionSelector:str,stemSelector:str};
const spec = (description,properties={},required=[]) => ({description,inputSchema:{type:'object',properties,required,additionalProperties:false}});
const tools = {
    course_status:spec('Status of this exact authorized owner; no credentials or signed URL.'),
    course_bind:spec('Bind the single matching manually opened tab after explicit confirmation.',{confirmed:boolean},['confirmed']),
    course_unbind:spec('Forget the bound tab after explicit user authorization; no navigation.',{confirmed:boolean},['confirmed']),
    course_read:spec('Read visible text in one scoped content element.',{selector:str,maxChars:{type:'integer',minimum:1,maximum:12000}},['selector']),
    course_scroll:spec('Scroll the authorized tab or a specific visible content container; no navigation.',{pixels:{type:'integer',minimum:-1200,maximum:1200},selector:str},['pixels']),
    course_questions:spec('Read current rendered native radio/checkbox questions and fingerprints.',questionProps,Object.keys(questionProps)),
    course_select:spec('Select one verified question only when owner and current request are authorized; re-read selections.',
        {...questionProps,fingerprint:{type:'string',pattern:'^[0-9a-f]{64}$'},choices:{type:'array',minItems:1,maxItems:40,items:{type:'string',minLength:1,maxLength:2000}},confirmed:boolean},
        [...Object.keys(questionProps),'fingerprint','choices','confirmed']),
    course_progress:spec('Read exact displayed total, selected count, pending status and site timer separately.',
        {...questionProps,totalSelector:str,timerSelector:str,pendingSelector:str,pendingText:str,expectedTotal:{type:'integer',minimum:1,maximum:300}},
        [...Object.keys(questionProps),'totalSelector','timerSelector','pendingSelector','pendingText','expectedTotal']),
    course_ocr_check:spec('Preflight local Windows OCR languages.',{language:{type:'string',pattern:'^[A-Za-z0-9-]{2,35}$'}},['language']),
    course_ocr:spec('Read one visible course image/canvas with local Windows OCR; no raw image retained.',
        {selector:str,pageSelector:str,language:{type:'string',pattern:'^[A-Za-z0-9-]{2,35}$'}},['selector','pageSelector','language']),
    course_save_notes:spec('Save reviewed course Markdown under this account notes only; no raw dumps or overwrite.',
        {slug:{type:'string',pattern:'^[a-z0-9][a-z0-9_-]{0,47}$'},markdown:{type:'string',minLength:1,maxLength:65536},excludedText:{type:'array',minItems:0,maxItems:40,items:{type:'string',minLength:1,maxLength:500}},confirmed:boolean},
        ['slug','markdown','excludedText','confirmed']),
    course_close:spec('Close only this owner when the user explicitly asks.',{confirmed:boolean},['confirmed']),
};
function schemaCheck(s,v) {
    if(s.type==='string') assert(typeof v==='string' && v.length >= (s.minLength||0) && v.length <= (s.maxLength||10000) &&
        (!s.pattern||new RegExp(s.pattern).test(v)),'Invalid string argument.');
    else if(s.type==='integer') assert(Number.isSafeInteger(v) && v>=s.minimum && v<=s.maximum,'Invalid integer argument.');
    else if(s.type==='boolean') assert(typeof v==='boolean','Invalid confirmation.');
    else if(s.type==='array') {
        assert(Array.isArray(v)&&v.length>=s.minItems&&v.length<=s.maxItems,'Invalid choices.');
        for(const item of v) schemaCheck(s.items,item);
    }
}
function validateCall(name,args) {
    assert(Object.hasOwn(tools,name) && args && typeof args==='object' && !Array.isArray(args),'Unsupported course operation.');
    const {properties,required} = tools[name].inputSchema;
    assert(required.every(k=>Object.hasOwn(args,k)) && Object.keys(args).every(k=>Object.hasOwn(properties,k)),'Unexpected course arguments.');
    for(const [k,v] of Object.entries(args)) schemaCheck(properties[k],v);
    if(Object.hasOwn(properties,'confirmed')) assert(args.confirmed===true,'Explicit confirmation required.');
}
function line(socket) {
    return new Promise((resolve,reject)=>{
        let text='';
        const cleanup=()=>{
            socket.off('data',data);socket.off('error',error);socket.off('end',end);socket.off('close',end);socket.off('timeout',timeout);
        };
        const error=()=>{cleanup();reject(new Error('Course IPC unavailable.'));};
        const end=error,timeout=error;
        const data=chunk=>{
            text+=chunk;
            if(Buffer.byteLength(text,'utf8')>MAX_FRAME){error();socket.destroy();return;}
            const at=text.indexOf('\n');
            if(at!==-1){
                cleanup();
                try{assert(at===text.length-1,'Unexpected IPC frames.');resolve(JSON.parse(text.slice(0,at)));}
                catch{reject(new Error('Invalid course IPC frame.'));}
            }
        };
        socket.on('data',data);socket.once('error',error);socket.once('end',end);socket.once('close',end);socket.once('timeout',timeout);
        socket.resume();
    });
}
function send(socket,obj) {
    const text=JSON.stringify(obj)+'\n';
    assert(Buffer.byteLength(text,'utf8')<=MAX_FRAME,'Course IPC result exceeds limit.');
    return new Promise((resolve,reject)=>socket.write(text,e=>e?reject(new Error('Course IPC write failed.')):resolve()));
}
const pipeName=session=>'\\\\.\\pipe\\PortableCourse-'+session;
function descriptor(state,session){return path.join(state,'runtime','connection-'+session+'.json');}
function loadDescriptor(state,task,account,session) {
    assert(validSession(session),'Invalid course session.');
    const file=descriptor(state,session);
    guard('file',file);
    assert(fs.statSync(file).size<=1024,'Invalid connection file.');
    const value=JSON.parse(fs.readFileSync(file,'utf8'));
    assert(value.session===session && value.task===task && value.account===account &&
        /^[0-9a-f]{64}$/.test(value.key),'Connection file does not match this account.');
    return value;
}
async function rpc(auth,name,args) {
    validateCall(name,args);
    const socket=net.createConnection(pipeName(auth.session));
    socket.setEncoding('utf8');socket.setTimeout(115000);
    socket.on('error',()=>{});
    try {
        const hello=await line(socket);
        assert(/^[0-9a-f]{32}$/.test(hello.nonce) &&
            equal(hello.proof,hmac(auth.key,'owner',auth.session,hello.nonce)),'Owner identity could not be verified.');
        const body=JSON.stringify({name,args});
        const nonce=random(16);
        const pending=line(socket);
        await send(socket,{nonce,body,proof:hmac(auth.key,'request',auth.session,hello.nonce,nonce,body)});
        const response=await pending;
        assert(typeof response.body==='string' && equal(response.proof,hmac(auth.key,'response',auth.session,hello.nonce,nonce,response.body)),
            'Owner response identity could not be verified.');
        const value=JSON.parse(response.body);
        if(!value.ok) fail(value.error||'Course operation refused.');
        return value.value;
    } finally {socket.destroy();}
}
async function oneVisible(page,css) {
    const loc=page.locator(selector(css));
    assert(await loc.count()===1 && await loc.isVisible(),'Expected exactly one visible authorized content element.');
    return loc;
}
// One fixed DOM snapshot per read. CSS is interpreted only as a selector;
// no caller-supplied JavaScript or hidden input values are evaluated.
async function questions(page,args) {
    selector(args.questionSelector); selector(args.stemSelector);
    const raw=await page.evaluate(({questionSelector,stemSelector})=>{
        const groups=[...document.querySelectorAll(questionSelector)];
        if(groups.length>300)throw new Error('too many groups');
        const visible=e=>!!e.getClientRects().length && !['hidden','collapse'].includes(getComputedStyle(e).visibility);
        return groups.map((group,index)=>{
            if(!visible(group))return null;
            const stems=[...group.querySelectorAll(stemSelector)].filter(visible);
            const controls=[...group.querySelectorAll('input[type=radio],input[type=checkbox]')];
            if(stems.length!==1||controls.some(input=>groups.some(g=>g!==group&&g.contains(input))))
                throw new Error('ambiguous group');
            return {index,stem:stems[0].innerText,options:controls.map(input=>({
                type:input.type,label:input.labels?.length===1&&visible(input.labels[0])?input.labels[0].innerText:null,
                selected:input.checked
            }))};
        }).filter(Boolean);
    },{questionSelector:args.questionSelector,stemSelector:args.stemSelector});
    const list=[];
    for(const item of raw){
        const stem=normalized(item.stem);
        assert(stem.length>0&&stem.length<=8000&&item.options.length>=2&&item.options.length<=40,'Incomplete or unsupported question.');
        const type=item.options[0].type,choices=[],selected=[];
        for(const opt of item.options){
            assert(['radio','checkbox'].includes(type)&&opt.type===type&&typeof opt.label==='string','Unsupported or ambiguous native option.');
            const label=normalized(opt.label);
            assert(label.length>0&&label.length<=2000&&!choices.includes(label),'Ambiguous or missing option label.');
            choices.push(label);if(opt.selected)selected.push(label);
        }
        assert(type!=='radio'||selected.length<=1,'Invalid single-choice state.');
        const fingerprint=choiceFingerprint(stem,type,choices);
        assert(!list.some(q=>q.fingerprint===fingerprint),'Duplicate question fingerprint; cannot select safely.');
        list.push({stem,type,choices,selected,fingerprint,controls:page.locator(selector(args.questionSelector)).nth(item.index).locator('input[type=radio],input[type=checkbox]')});
    }
    return list;
}
const serialQuestion=({controls,...q})=>q;
const selectedKey=q=>JSON.stringify([...q.selected].sort());
async function selectQuestion(page,args,ensurePage) {
    const before=await questions(page,args);
    let target=before.find(q=>q.fingerprint===args.fingerprint);
    assert(target,'Question fingerprint not present on this account.');
    const wanted=args.choices.map(normalized);
    assert(new Set(wanted).size===wanted.length && wanted.every(s=>target.choices.includes(s)) &&
        (target.type!=='radio'||wanted.length===1),'Choices do not match the actual current question.');
    for(const option of target.choices){
        if(target.type==='radio'&&!wanted.includes(option))continue;
        await ensurePage();
        const current=(await questions(page,args)).find(q=>q.fingerprint===args.fingerprint);
        assert(current,'Question changed before selection; stop and re-read.');
        const checked=current.selected.includes(option);
        const desired=wanted.includes(option);
        if(checked!==desired){
            const input=current.controls.nth(current.choices.indexOf(option));
            const handle=await input.elementHandle({timeout:5000});
            assert(handle,'Native option no longer exists.');
            try{
                // Bind to the actual DOM node. A locator re-resolved after a
                // page rerender must never silently click a different question.
                const proof=await handle.evaluate((e,{questionSelector,stemSelector})=>{
                    const g=e.closest(questionSelector);
                    if(!g||!e.isConnected||e.labels?.length!==1)return null;
                    const stems=[...g.querySelectorAll(stemSelector)];
                    const controls=[...g.querySelectorAll('input[type=radio],input[type=checkbox]')];
                    if(stems.length!==1||controls.some(x=>x.type!==e.type||x.labels?.length!==1))return null;
                    return {stem:stems[0].innerText,type:e.type,choices:controls.map(x=>x.labels[0].innerText),option:e.labels[0].innerText};
                },{questionSelector:args.questionSelector,stemSelector:args.stemSelector});
                assert(proof&&choiceFingerprint(proof.stem,proof.type,proof.choices)===args.fingerprint&&normalized(proof.option)===option,
                    'Question or option changed before selection; stop.');
                assert(await handle.isVisible()&&await handle.isEnabled(),'Native option is not normally operable.');
                await ensurePage();
                if(desired)await handle.check({timeout:5000});else await handle.uncheck({timeout:5000});
                await ensurePage();
            }finally{await handle.dispose();}
        }
    }
    const after=await questions(page,args);
    target=after.find(q=>q.fingerprint===args.fingerprint);
    assert(target && selectedKey(target)===JSON.stringify([...wanted].sort()),'Selection could not be verified; do not retry blindly.');
    for(const q of before.filter(q=>q.fingerprint!==args.fingerprint)){
        const now=after.find(x=>x.fingerprint===q.fingerprint);
        assert(now&&selectedKey(now)===selectedKey(q),'Another rendered question changed; stop and review.');
    }
    return serialQuestion(target);
}
function ocr(state,language,image) {
    const script=checkedPath(ROOT,path.join(__dirname,'ocr.ps1'));
    guard('file',script);
    const ps=path.join(process.env.SystemRoot,'System32/WindowsPowerShell/v1.0/powershell.exe');
    assert(fs.existsSync(ps),'Built-in Windows PowerShell missing.');
    const argv=['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',script,'-State',state,'-Language',language];
    if(image)argv.push('-Image',image);else argv.push('-Check');
    const r=spawnSync(ps,argv,{windowsHide:true,cwd:state,timeout:90000,encoding:'utf8',maxBuffer:MAX_FRAME});
    assert(r.status===0&&!r.error,'Local Windows OCR failed; check OS API and language support.');
    try{return JSON.parse(r.stdout.replace(/^\uFEFF/,''));}catch{fail('Unexpected local OCR output.');}
}
function operations(context,state,scope,allowSelection,auth) {
    let bound=null, urlHash=null, bindingId=null, invalid=false, navigationListener=null;
    const isBound=()=>Boolean(bound&&!bound.isClosed()&&!invalid&&matching(bound.url(),scope)&&hash(bound.url())===urlHash);
    function unbind(){if(bound&&navigationListener)bound.off('framenavigated',navigationListener);bound=null;urlHash=null;bindingId=null;invalid=false;navigationListener=null;}
    function ensurePage(){
        assert(isBound(),
            'Bound page changed or closed; explicit new page authorization required.');
        return bound;
    }
    return async(name,args)=>{
        validateCall(name,args);
        if(name==='course_status')return {task:auth.task,account:auth.account,session:auth.session,scope,allowSelection,
            bound:isBound(),bindingId:isBound()?bindingId:null,blank:context.pages().length>0&&context.pages().every(p=>p.url()==='about:blank')};
        if(name==='course_close')return {closing:true,session:auth.session};
        if(name==='course_unbind'){unbind();return {bound:false};}
        if(name==='course_bind'){
            assert(!bound,'Already bound; explicitly unbind before a new page authorization.');
            const pages=context.pages().filter(p=>matching(p.url(),scope)&&!p.isClosed());
            assert(pages.length===1,'Expected one manually opened authorized tab.');
            assert(await pages[0].locator('input[type=password]:visible').count()===0,'Login or credential page is not an authorized course tab.');
            bound=pages[0];urlHash=hash(bound.url());bindingId=random(16);invalid=false;
            navigationListener=frame=>{if(frame===bound?.mainFrame())invalid=true;};
            bound.on('framenavigated',navigationListener);ensurePage();return {bound:true,scope,bindingId};
        }
        if(name==='course_save_notes'){
            ensurePage();
            assert(alias(args.slug)&&/^#\s/m.test(args.markdown),'Use a reviewed Markdown course note.');
            assert(!/https?:\/\/[^\s<>()]+[?#][^\s<>()]*|(?:authorization|set-cookie|cookie)\s*:/i.test(args.markdown),
                'Remove signed URLs and credential material before saving.');
            const compact=s=>normalized(s).toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
            const body=compact(args.markdown);
            for(const item of args.excludedText){const marker=compact(item);assert(marker.length>=3&&!body.includes(marker),'Reviewed note still contains an excluded personal/watermark marker.');}
            const target=path.join(state,'notes','course-'+args.slug+'.md');
            guard('directory',path.dirname(target));guard('missing',target);
            const fd=fs.openSync(target,'wx');
            try{fs.writeFileSync(fd,args.markdown,'utf8');}finally{fs.closeSync(fd);}
            guard('file',target);
            return {saved:'notes/course-'+args.slug+'.md'};
        }
        if(name==='course_ocr_check')return ocr(state,args.language);
        const page=ensurePage();
        if(name==='course_read'){
            const loc=await oneVisible(page,args.selector);
            const text=await loc.innerText({timeout:5000});
            ensurePage();
            const limit=args.maxChars||12000;
            return {text:text.slice(0,limit),truncated:text.length>limit};
        }
        if(name==='course_scroll'){
            if(args.selector){
                const loc=await oneVisible(page,args.selector);
                await loc.evaluate((e,p)=>e.scrollBy(0,p),args.pixels);
            }else await page.evaluate(p=>window.scrollBy(0,p),args.pixels);
            ensurePage();return {scrolled:true,pixels:args.pixels};
        }
        if(name==='course_questions'){
            const list=await questions(page,args);ensurePage();
            return {renderedCount:list.length,questions:list.map(serialQuestion)};
        }
        if(name==='course_progress'){
            const total=normalized(await (await oneVisible(page,args.totalSelector)).innerText());
            assert(/^\d{1,3}$/.test(total)&&Number(total)===args.expectedTotal,'Displayed total differs from expected total.');
            const list=await questions(page,args);
            const count=list.filter(q=>q.selected.length>0).length;
            const pending=normalized(await (await oneVisible(page,args.pendingSelector)).innerText())===normalized(args.pendingText);
            const siteTimer=normalized(await (await oneVisible(page,args.timerSelector)).innerText()).slice(0,100);
            assert(list.length<=args.expectedTotal,'Rendered questions exceed displayed total.');
            ensurePage();
            const complete=list.length===args.expectedTotal&&count===args.expectedTotal&&pending;
            return {rendered:list.length,answered:count,total:args.expectedTotal,pending,
                status:'\u5df2\u7b54 '+count+'/'+args.expectedTotal+(complete?'\uff0c\u5f85\u4ea4\u5377':''),siteTimer};
        }
        if(name==='course_select'){
            assert(allowSelection,'This owner was authorized for reading only.');
            const q=await selectQuestion(page,args,ensurePage);ensurePage();return q;
        }
        if(name==='course_ocr'){
            const preflight=ocr(state,args.language);
            if(!preflight.supported)return preflight;
            const loc=await oneVisible(page,args.selector);
            const pageLabel=normalized(await (await oneVisible(page,args.pageSelector)).innerText());
            assert(pageLabel.length>0&&pageLabel.length<=200,'Page provenance is missing or ambiguous.');
            assert(await loc.evaluate(e=>['IMG','CANVAS'].includes(e.tagName)),'Only a single course image/canvas is permitted.');
            const temp=path.join(state,'tmp','ocr-'+random(16)+'.png');
            guard('directory',path.dirname(temp));guard('missing',temp);
            let created=false;
            try{
                const png=await loc.screenshot({type:'png',scale:'css',timeout:10000});
                ensurePage();assert(png.length<=20*1024*1024,'OCR image exceeds temporary size limit.');
                guard('missing',temp);
                const fd=fs.openSync(temp,'wx');created=true;
                try{fs.writeFileSync(fd,png);}finally{fs.closeSync(fd);}
                guard('file',temp);
                const result=ocr(state,args.language,temp);
                ensurePage();return {...result,source:{pageLabel,imageSelector:args.selector,bindingId}};
            }finally{if(created){guard('file',temp);fs.unlinkSync(temp);}}
        }
        fail('Unsupported course operation.');
    };
}
async function owner(state,task,account,exe,origin,pagePath,mode,landing='blank') {
    const scope=scopeFor(origin,pagePath);
    assert(['read','select'].includes(mode)&&['blank','open-non-timed'].includes(landing),'Invalid owner mode.');
    const directories={};
    for(const name of ['profile','cache','crashes','downloads','runtime','tmp','notes']){
        directories[name]=checkedPath(state,name,{directory:true});
        guard('tree',directories[name]);
    }
    checkTree(ROOT,path.dirname(exe));
    checkTree(ROOT,path.join(__dirname,'../playwright/node_modules'));
    const proxy=browserProxy(process.env);
    const {chromium}=require('../playwright/node_modules/playwright');
    const context=await chromium.launchPersistentContext(directories.profile,{
        executablePath:exe,headless:false,chromiumSandbox:true,acceptDownloads:false,serviceWorkers:'block',
        downloadsPath:directories.downloads,...(proxy?{proxy}:{}),
        args:[...(proxy?[]:['--no-proxy-server']),'--disk-cache-dir='+directories.cache,
            '--crash-dumps-dir='+directories.crashes,'--disable-breakpad','--disable-gpu-shader-disk-cache'],
    });
    const auth={task,account,session:random(16),key:random(32)};
    const file=descriptor(state,auth.session);
    const run=operations(context,state,scope,mode==='select',auth);
    let busy=false,closing=false,created=false,closedResolve;
    const closed=new Promise(resolve=>closedResolve=resolve);
    const sockets=new Set();
    const server=net.createServer(socket=>{
        sockets.add(socket);socket.setEncoding('utf8');socket.setTimeout(115000);
        socket.on('error',()=>{});socket.once('close',()=>sockets.delete(socket));
        void (async()=>{
            const nonce=random(16);
            try{
                const request=line(socket);
                await send(socket,{nonce,proof:hmac(auth.key,'owner',auth.session,nonce)});
                const r=await request;
                assert(/^[0-9a-f]{32}$/.test(r.nonce)&&typeof r.body==='string'&&
                    equal(r.proof,hmac(auth.key,'request',auth.session,nonce,r.nonce,r.body)),'Unauthorized course client.');
                const call=JSON.parse(r.body);
                let value;
                if(busy||closing)value={ok:false,error:'Owner busy or closing; no operation performed.'};
                else {
                    busy=true;
                    try{value={ok:true,value:await run(call.name,call.args)};}
                    catch(e){
                        // Do not expose Playwright errors that may contain signed URLs,
                        // raw page data, browser details or credentials.
                        value={ok:false,error:e instanceof CourseError?e.message:'Course operation failed; inspect current authorized page manually.'};
                    }finally{busy=false;}
                }
                let body=JSON.stringify(value);
                if(Buffer.byteLength(body,'utf8')>MAX_FRAME/2)body=JSON.stringify({ok:false,error:'Result too large; narrow the selected content.'});
                await send(socket,{body,proof:hmac(auth.key,'response',auth.session,nonce,r.nonce,body)});
                if(value.ok&&call.name==='course_close')await stop();
            }catch{}finally{socket.destroy();}
        })();
    });
    async function stop(){
        if(closing)return;
        closing=true;
        try{
            await context.close();
            for(const s of sockets)s.destroy();
            if(server.listening)await new Promise(resolve=>server.close(resolve));
            if(created){guard('file',file);fs.unlinkSync(file);}
        }catch(e){
            process.exitCode=1;
            for(const s of sockets)s.destroy();
            if(server.listening)server.close();
            process.stderr.write('Course owner close/cleanup incomplete; inspect this account only.\n');
        }finally{closedResolve();}
    }
    const onClose=()=>void stop().catch(()=>{process.exitCode=1;closedResolve();});
    context.once('close',onClose);process.once('SIGINT',onClose);process.once('SIGTERM',onClose);
    try{
        // Optional explicit opening of a known non-timed landing page only;
        // the ordinary owner opens blank for the user's manual navigation.
        if(landing==='open-non-timed'){
            const page=context.pages()[0]||await context.newPage();
            await page.goto(scope.origin+scope.pagePath,{waitUntil:'domcontentloaded',timeout:30000});
        }
        await new Promise((resolve,reject)=>{server.once('error',reject);server.listen({path:pipeName(auth.session),readableAll:false,writableAll:false},resolve);});
        guard('missing',file);
        const fd=fs.openSync(file,'wx');created=true;
        try{fs.writeFileSync(fd,JSON.stringify(auth),'utf8');}finally{fs.closeSync(fd);}
        guard('file',file);
        console.log('COURSE_SESSION_READY='+auth.session);
        await closed;
    }catch(e){await stop();throw e;}
}
async function client(state,task,account,session) {
    const auth=loadDescriptor(state,task,account,session);
    // Prove possession of the live owner before exposing any tools.
    await rpc(auth,'course_status',{});
    const {StdioServerTransport}=require('../playwright/node_modules/playwright-core/lib/utilsBundle');
    const transport=new StdioServerTransport();
    let initialized=false;
    transport.onmessage=message=>void (async()=>{
        const id=message?.id;
        try{
            assert(message?.jsonrpc==='2.0','Invalid MCP message.');
            if(message.method==='notifications/initialized'&&id===undefined)return;
            if(message.method==='notifications/cancelled'&&id===undefined)return;
            assert(typeof id==='string'||Number.isSafeInteger(id),'Invalid MCP request ID.');
            let result;
            if(message.method==='initialize'){
                assert(!initialized,'Already initialized.');
                const requested=message.params?.protocolVersion;
                const supported=['2024-11-05','2025-03-26','2025-06-18','2025-11-25'];
                result={protocolVersion:supported.includes(requested)?requested:'2025-06-18',
                    capabilities:{tools:{}},serverInfo:{name:'portable-course-assistant',version:'1.0.0'}};
                initialized=true;
            }else{
                assert(initialized,'MCP initialization required.');
                if(message.method==='ping')result={};
                else if(message.method==='tools/list')result={tools:Object.entries(tools).map(([name,s])=>({name,...s}))};
                else if(message.method==='tools/call'){
                    try{
                        const v=await rpc(auth,message.params?.name,message.params?.arguments||{});
                        result={content:[{type:'text',text:JSON.stringify(v)}]};
                    }catch(e){result={isError:true,content:[{type:'text',text:e.message||'Course call refused.'}]};}
                }else fail('Unsupported course MCP method.');
            }
            await transport.send({jsonrpc:'2.0',id,result});
        }catch(e){if(id!==undefined)await transport.send({jsonrpc:'2.0',id,error:{code:-32602,message:'Course MCP request refused.'}});}
    })().catch(()=>{process.exitCode=1;});
    await transport.start();
    // No owner shutdown on EOF, cancellation, transport failure, or response end.
}
async function main() {
    assert(process.platform==='win32'&&process.arch==='x64','Windows x64 required.');
    assert(samePath(process.execPath,path.join(ROOT,'tool/node/node.exe')),'Use packaged Node.');
    const [action,rawState,task,account,exe,...args]=process.argv.slice(2);
    const state=stateFor(rawState,task,account);
    checkRuntime(state);
    const versions=JSON.parse(fs.readFileSync(checkedPath(ROOT,path.join(__dirname,'../versions.json')),'utf8'));
    const expected=checkedPath(ROOT,path.join(__dirname,'..',versions.browser.executable));
    assert(samePath(exe,expected),'Only the pinned package Chromium is allowed.');
    if(action==='owner'&&args.length===4)await owner(state,task,account,expected,...args);
    else if(action==='client'&&args.length===1)await client(state,task,account,args[0]);
    else fail('Explicit owner/client selection required.');
}
module.exports={scopeFor,matching,choiceFingerprint,validateCall,operations,owner,rpc,loadDescriptor,client,tools};
if(require.main===module)main().catch(()=>{process.stderr.write('Course assistant refused or failed; inspect authorization, paths, owner state and Windows support.\n');process.exitCode=1;});

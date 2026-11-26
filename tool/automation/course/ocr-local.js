'use strict';
// No discovery, network or environment-configurable executable/model.
// The checked-in distribution lock is disabled until separate review.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const ROOT=path.resolve(__dirname,'../../..');
const MAX=512*1024;
const MODEL={size:2469156,sha256:'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730'};
const TSV={size:22,sha256:'59d079bb75d8b3d7c839a3564580cb559e362c93a9d70f234e421c0c3e767e04'};
const HEADER='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext';
const KNOWN_STDERR=[
    'Error in pixReadMemTiff: function not present',
    'Error in pixReadMem: tiff: no pix returned',
    'Error in pixaGenerateFontFromString: pix not made',
    'Error in bmfCreate: font pixa not made'
];
function requireThat(ok,code){if(!ok)throw new Error(code);}
function same(a,b){return path.resolve(a).toLowerCase()===path.resolve(b).toLowerCase();}
function jsonResult(r,code){
    requireThat(!r.error&&r.status===0,code);
    try{return JSON.parse(r.stdout.replace(/^\uFEFF/,''));}
    catch{throw new Error(code);}
}
function validState(state,guard){
    const rel=path.relative(path.join(ROOT,'work'),state).split(path.sep);
    requireThat(rel.length===2&&/^course-[a-z0-9][a-z0-9_-]{0,47}$/.test(rel[0])&&
        /^[a-z0-9][a-z0-9_-]{0,47}$/.test(rel[1]),'OCR_PATH');
    guard('directory',state);guard('directory',path.join(state,'tmp'));
    guard('directory',path.join(state,'runtime'));
}
function pngInfo(state,image,guard,python){
    validState(state,guard);
    requireThat(same(path.dirname(image),path.join(state,'tmp'))&&/^ocr-[0-9a-f]{32}\.png$/.test(path.basename(image)),'OCR_PATH');
    guard('file',image);
    const script=path.join(__dirname,'png_guard.py');guard('file',script);
    const p=spawnSync(python(),['-I','-B',script,state,image],{cwd:state,windowsHide:true,timeout:20000,encoding:'utf8',maxBuffer:4096});
    if(p.error||p.status!==0){
        const code=(p.stderr||'').trim();
        throw new Error(/^PNG_(?:LIMIT|FORMAT|CORRUPT|PATH|PATH_OR_DECODER)$/.test(code)?code:'PNG_VALIDATION_FAILED');
    }
    const info=jsonResult(p,'PNG_VALIDATION_FAILED');
    requireThat(Number.isInteger(info.width)&&Number.isInteger(info.height)&&info.width>0&&info.height>0&&
        Math.max(info.width,info.height)<=4096&&info.width*info.height<=16*1024*1024,'PNG_VALIDATION_FAILED');
    return info;
}
function fileIdentity(file,expected,guard){
    requireThat(expected&&Number.isSafeInteger(expected.size)&&expected.size>0&&expected.size<=32*1024*1024&&
        /^[0-9a-f]{64}$/.test(expected.sha256),'OCR_PAYLOAD_LOCK');
    guard('file',file);
    requireThat(fs.statSync(file).size===expected.size,'OCR_PAYLOAD_INTEGRITY');
    requireThat(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')===expected.sha256,'OCR_PAYLOAD_INTEGRITY');
}
function verifyPayload(root,lock,guard){
    requireThat(lock&&lock.format===1&&lock.engine==='tesseract-5.5.4'&&lock.modelLanguage==='chi_sim','OCR_PAYLOAD_LOCK');
    const base=path.join(root,'tool','automation','course','ocr-native');
    const bin=path.join(base,'bin'),data=path.join(base,'tessdata');
    for(const d of [base,bin,data,path.join(data,'configs')])guard('directory',d);
    // A second executable, adjacent DLL or extra language/config is forbidden.
    const names=(d,want)=>requireThat(JSON.stringify(fs.readdirSync(d).sort())===JSON.stringify(want.slice().sort()),'OCR_PAYLOAD_INVENTORY');
    names(base,['bin','tessdata']);names(bin,['tesseract.exe']);
    names(data,['chi_sim.traineddata','configs']);names(path.join(data,'configs'),['tsv']);
    const exe=path.join(bin,'tesseract.exe');
    fileIdentity(exe,lock.exe,guard);
    fileIdentity(path.join(data,'chi_sim.traineddata'),MODEL,guard);
    fileIdentity(path.join(data,'configs','tsv'),TSV,guard);
    return {exe,bin,data};
}
function distributionPayload(guard){
    const f=path.join(__dirname,'ocr-native-lock.json');guard('file',f);
    requireThat(fs.statSync(f).size<=4096,'OCR_PAYLOAD_LOCK');
    const lock=JSON.parse(fs.readFileSync(f,'utf8'));
    requireThat(lock.format===1&&lock.engine==='tesseract-5.5.4'&&lock.modelLanguage==='chi_sim','OCR_PAYLOAD_LOCK');
    if(lock.distributionQualified===false){
        requireThat(lock.exe===null&&!fs.existsSync(path.join(__dirname,'ocr-native')),'OCR_UNQUALIFIED_PAYLOAD');
        return null;
    }
    requireThat(lock.distributionQualified===true&&typeof lock.evidence==='string'&&lock.evidence.length>0,'OCR_PAYLOAD_LOCK');
    return verifyPayload(ROOT,lock,guard);
}
function parseTsv(raw,info){
    requireThat(typeof raw==='string'&&Buffer.byteLength(raw,'utf8')<=MAX&&!raw.includes('\uFFFD'),'OCR_OUTPUT_INVALID');
    const rows=raw.replace(/\r\n/g,'\n').split('\n');
    if(rows[rows.length-1]==='')rows.pop();
    requireThat(rows.shift()===HEADER&&rows.length<=16000,'OCR_OUTPUT_INVALID');
    const groups=new Map();let words=0,chars=0;
    for(const row of rows){
        const f=row.split('\t');
        requireThat(f.length===12&&f.slice(0,10).every(s=>/^\d{1,9}$/.test(s))&&/^-?\d+(?:\.\d+)?$/.test(f[10]),'OCR_OUTPUT_INVALID');
        const [level,page,block,par,line,word,x,y,width,height]=f.slice(0,10).map(Number);
        requireThat(level>=1&&level<=5&&page===1,'OCR_OUTPUT_INVALID');
        if(level!==5)continue;
        const text=f[11].trim();
        if(!text)continue;
        requireThat(block>0&&par>0&&line>0&&word>0&&width>0&&height>0&&
            x+width<=info.width&&y+height<=info.height&&Number(f[10])>=0&&Number(f[10])<=100&&
            !/[\x00-\x1f\x7f]/.test(text),'OCR_OUTPUT_INVALID');
        words++;chars+=text.length;
        requireThat(words<=4096&&chars<=65536,'OCR_OUTPUT_LIMIT');
        const k=[block,par,line].join(':');
        if(!groups.has(k))groups.set(k,[]);
        groups.get(k).push({text,x,y,width,height});
    }
    const lines=[...groups.values()].map(words=>({text:words.map(w=>w.text).join(' '),words}));
    return {text:lines.length?lines.map(l=>l.text).join('\n'):null,lines,status:lines.length?'ok':'empty'};
}
function nativeResult(r,info){
    requireThat(!r.error&&r.status===0,'OCR_NATIVE_FAILED');
    const stderr=(r.stderr||'').replace(/\r\n/g,'\n').trim();
    // Accept only the exact upstream diagnostic sequence already observed for
    // this PNG-only build. Do not treat arbitrary stderr as a success or echo it.
    requireThat(!stderr||stderr===KNOWN_STDERR.join('\n'),'OCR_NATIVE_DIAGNOSTIC');
    const parsed=parseTsv(r.stdout,info);
    return {...parsed,diagnostics:stderr?['TIFF_FONT_UNAVAILABLE']:[]};
}
function runNative(state,image,info,payload,guard){
    validState(state,guard);guard('file',image);
    requireThat(same(path.dirname(image),path.join(state,'tmp'))&&/^ocr-[0-9a-f]{32}\.png$/.test(path.basename(image)),'OCR_PATH');
    const cwd=path.dirname(image),data=path.relative(cwd,payload.data);
    // All relative components are fixed ASCII; avoid passing a Chinese parent
    // path through Tesseract's narrow argv conversion.
    requireThat(/^[A-Za-z0-9_.\\/-]+$/.test(data)&&same(path.resolve(cwd,data),payload.data),'OCR_PAYLOAD_PATH');
    const env={};
    for(const k of ['SystemRoot','WINDIR','SystemDrive','ComSpec','OS','PROCESSOR_ARCHITECTURE'])if(process.env[k])env[k]=process.env[k];
    requireThat(process.env.SystemRoot,'OCR_OS');
    for(const k of ['HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC',
        'XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_STATE_HOME'])env[k]=path.join(state,'runtime');
    env.PATH=payload.bin+';'+path.join(process.env.SystemRoot,'System32');
    env.TESSDATA_PREFIX=data;
    const r=spawnSync(payload.exe,[path.basename(image),'stdout','--tessdata-dir',data,'-l','chi_sim','--psm','6','tsv'],
        {cwd,env,windowsHide:true,timeout:90000,encoding:'utf8',maxBuffer:MAX});
    return nativeResult(r,info);
}
function selectEngine(windows,language,payload){
    if(windows.supported)return 'windows';
    if(language.toLowerCase()==='zh-hans-cn'&&payload)return 'native';
    return 'unavailable';
}
function windowsResult(result){
    requireThat(result&&Array.isArray(result.lines)&&typeof result.supported==='boolean','OCR_WINDOWS_OUTPUT');
    requireThat(result.supported,'OCR_WINDOWS_ENGINE_CHANGED');
    if(typeof result.text==='string'&&result.text.trim()&&result.lines.length&&result.lines.some(l=>Array.isArray(l.words)&&l.words.some(w=>typeof w.text==='string'&&w.text.trim()))){
        return {...result,status:'ok',engine:'windows',windowsSupported:true,diagnostics:[]};
    }
    requireThat(!result.text||!result.text.trim(),'OCR_WINDOWS_OUTPUT');
    return {...result,text:null,lines:[],status:'empty',engine:'windows',windowsSupported:true,diagnostics:[]};
}
function createOcr(guard,python,windows,resolvePayload=()=>distributionPayload(guard)){
    // The injectable resolver is used only by developer tests. The MCP entry
    // supplies no resolver, user path, environment override or raw CLI option.
    return (state,language,image)=>{
        validState(state,guard);
        const info=image?pngInfo(state,image,guard,python):null;
        const os=windows(state,language);
        requireThat(os&&typeof os.supported==='boolean'&&Array.isArray(os.available),'OCR_WINDOWS_OUTPUT');
        let payload=null;
        if(!os.supported&&language.toLowerCase()==='zh-hans-cn')payload=resolvePayload();
        const engine=selectEngine(os,language,payload);
        const status={...os,windowsSupported:os.supported,engine:engine==='unavailable'?null:engine,
            supported:engine!=='unavailable',actualLanguage:engine==='native'?'chi_sim':os.actualLanguage,
            fallbackStatus:engine==='native'?'ready':engine==='windows'?'not_needed':'unavailable'};
        if(!image||engine==='unavailable')return {...status,status:engine==='unavailable'?'unavailable':'ready',text:null,lines:[]};
        if(engine==='windows')return {...status,...windowsResult(windows(state,language,image))};
        return {...status,...runNative(state,image,info,payload,guard)};
    };
}
module.exports={createOcr,verifyPayload,parseTsv,nativeResult,selectEngine,windowsResult,KNOWN_STDERR,pngInfo,runNative,distributionPayload};

'use strict';
// Developer-only Windows harness. No CLI option is exposed to the product MCP.
// This file is copied only into private scratch after verified ZIP readback.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const ROOT=path.resolve(process.argv[2]);
const state=path.join(ROOT,'work','course-ocrfixture','a');
const c=require(path.join(ROOT,'tool/automation/course/course.js'));
const o=require(path.join(ROOT,'tool/automation/course/ocr-local.js'));
assert.equal(process.platform,'win32');
assert.equal(path.resolve(process.execPath).toLowerCase(),path.join(ROOT,'tool/node/node.exe').toLowerCase());
const report=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const lock={format:1,engine:'tesseract-5.5.4',modelLanguage:'chi_sim',exe:report.runtime_pe};
const files=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
const output=[];
function row(item,status,detail){output.push({item,status,detail});console.log(JSON.stringify(output[output.length-1]));}
const resolve=()=>o.verifyPayload(ROOT,lock,c.guard);
const service=o.createOcr(c.guard,c.python,c.windowsOcr,resolve);
const language='zh-Hans-CN';
const check=c.windowsOcr(state,language);
row('actual Windows OCR language preflight',check.supported?'BLOCKED_LANGUAGE_PRESENT':'PASS_ACTUAL',{windowsSupported:check.supported,zhHansSupported:check.zhHansSupported,available:check.available});
// Check invalid PNG before engine selection even if language is installed.
for(const [k,code] of [['badcrc','PNG_CORRUPT'],['truncated','PNG_CORRUPT'],['nonpng','PNG_FORMAT'],['oversized','PNG_LIMIT'],['bytes','PNG_LIMIT']]){
    assert.throws(()=>service(state,language,files[k]),e=>e.message===code);
    row('product rejects '+k,'PASS_ACTUAL',code);
}
assert.throws(()=>service(state,language,files.outside),/OCR_PATH/);
row('product rejects outside account tmp','PASS_ACTUAL','no path fallback');
if(check.supported){
    const preferred=service(state,language);
    assert.equal(preferred.engine,'windows');
    row('Windows OCR preferred','PASS_ACTUAL','actual OS engine selected; missing-language native path not exercised');
}else{
    const result=service(state,language,files.normal);
    assert.equal(result.engine,'native');
    assert.equal(result.windowsSupported,false);
    assert.equal(result.actualLanguage,'chi_sim');
    assert.equal(result.status,'ok');
    const words=result.lines.flatMap(l=>l.words);
    const cells=[
        ['\u4e2d\u6587\u8bfe\u4ef6',80,50,650,150],['\u6570\u91cf',80,200,550,300],['\u91d1\u989d',650,200,1100,300],
        ['1208',80,340,550,440],['0.05',650,340,1100,440],['70301',80,480,550,580],['9007',650,480,1100,580],
        ['\u6c34\u5370',80,690,550,810],['\u7f16\u53f7314159',650,690,1150,810]
    ];
    const matched=cells.map(([expected,x,y,x2,y2])=>{
        const found=words.filter(w=>w.x>=x-20&&w.x+w.width<=x2&&w.y>=y-20&&w.y+w.height<=y2).sort((a,b)=>a.x-b.x);
        assert.equal(found.map(w=>w.text).join('').replace(/\s/gu,''),expected);
        return {expected,boxes:found.map(({x,y,width,height})=>({x,y,width,height}))};
    });
    row('actual product Chinese/numeric PNG on moved Windows path','PASS_ACTUAL',{cells:matched.length,engine:result.engine,diagnostics:result.diagnostics,boxes:matched.map(m=>m.boxes)});
    const blank=service(state,language,files.blank);
    assert.equal(blank.status,'empty');assert.equal(blank.text,null);assert.deepEqual(blank.lines,[]);
    row('actual native blank PNG','PASS_ACTUAL',{status:blank.status,diagnostics:blank.diagnostics});
    // Integrity faults use the exact same verifier, no arbitrary executable.
    const payload=resolve();
    for(const f of [payload.exe,path.join(payload.data,'chi_sim.traineddata'),path.join(payload.data,'configs','tsv')]){
        const original=fs.readFileSync(f),altered=Buffer.from(original);altered[0]^=1;
        try{fs.writeFileSync(f,altered);assert.throws(()=>service(state,language),/OCR_PAYLOAD_INTEGRITY/);}
        finally{fs.writeFileSync(f,original);}
    }
    resolve();row('actual exe, model and TSV byte-change refusal','PASS_ACTUAL','three same-size alterations rejected and restored');
    const dll=path.join(payload.bin,'extra.dll');
    try{fs.writeFileSync(dll,'synthetic');assert.throws(()=>service(state,language),/OCR_PAYLOAD_INVENTORY/);}
    finally{fs.unlinkSync(dll);}
    row('extra adjacent DLL refused','PASS_ACTUAL','no host fallback');
}
// Actual default distribution lock is closed: do not claim this test fixture
// is a distributable or installed OCR payload. Remove private bytes first.
fs.rmSync(path.join(ROOT,'tool/automation/course/ocr-native'),{recursive:true});
const shipped=c.ocr(state,language);
assert.equal(shipped.supported,check.supported);
assert.equal(shipped.engine,check.supported?'windows':null);
row('default product closed distribution lock','PASS_ACTUAL',{supported:shipped.supported,engine:shipped.engine});
for(const f of Object.values(files))if(f!==files.outside)fs.unlinkSync(f);
assert.deepEqual(fs.readdirSync(path.join(state,'tmp')),[]);
row('owned synthetic temporary files removed','PASS_ACTUAL','no OCR stdout/stderr or images persisted');
fs.writeFileSync(process.argv[5],JSON.stringify({completed:true,missingLanguage:!check.supported,rows:output}));

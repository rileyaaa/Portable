'use strict';
const assert=require('node:assert/strict');
const m=require('../tool/automation/course/ocr-local');
const header='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n';
const line='5\t1\t1\t1\t1\t1\t2\t4\t5\t6\t95.0\t\u6570\u91cf\n';
const page='1\t1\t0\t0\t0\t0\t0\t0\t20\t20\t-1\t\n';
const dims={width:20,height:20};
let cases=0;
function test(name,f){f();cases++;console.log('PASS_UNIT '+name);}
test('windows preferred',()=>assert.equal(m.selectEngine({supported:true},'zh-Hans-CN',{}),'windows'));
test('missing Chinese uses only explicit verified payload',()=>{
    assert.equal(m.selectEngine({supported:false},'zh-Hans-CN',{}),'native');
    assert.equal(m.selectEngine({supported:false},'zh-Hans-CN',null),'unavailable');
    assert.equal(m.selectEngine({supported:false},'en-US',{}),'unavailable');
});
test('TSV word geometry and Chinese',()=>assert.deepEqual(m.parseTsv(header+page+line,dims),
    {text:'\u6570\u91cf',lines:[{text:'\u6570\u91cf',words:[{text:'\u6570\u91cf',x:2,y:4,width:5,height:6}]}],status:'ok'}));
test('empty valid TSV distinct from malformed no-output',()=>{
    assert.deepEqual(m.parseTsv(header+page,dims),{text:null,lines:[],status:'empty'});
    assert.throws(()=>m.parseTsv('',dims),/OCR_OUTPUT_INVALID/);
});
test('invalid geometry, page, encoding, confidence and columns refused',()=>{
    for(const x of [line.replace('\t2\t4\t5\t6','\t19\t4\t5\t6'),line.replace('5\t1\t','5\t2\t'),line.replace('\t95.0\t','\t101\t'),line.replace('\u6570\u91cf','\uFFFD'),line.trimEnd()+'\textra\n'])
        assert.throws(()=>m.parseTsv(header+x,dims),/OCR_OUTPUT_INVALID/);
});
test('bounded stdout',()=>assert.throws(()=>m.parseTsv(header+'x'.repeat(512*1024),dims),/OCR_OUTPUT_INVALID/));
test('known stderr plus valid successful TSV',()=>{
    const r=m.nativeResult({status:0,stdout:header+line,stderr:m.KNOWN_STDERR.join('\r\n')+'\r\n'},dims);
    assert.equal(r.status,'ok');assert.deepEqual(r.diagnostics,['TIFF_FONT_UNAVAILABLE']);
});
test('unknown stderr or failed exit never leaks raw input',()=>{
    const secret='SYNTHETIC_PRIVATE_MARKER';
    for(const r of [{status:0,stdout:header+line,stderr:secret},{status:1,stdout:header+line,stderr:secret},
        {error:new Error(secret),status:null,stdout:'',stderr:secret}]){
        assert.throws(()=>m.nativeResult(r,dims),e=>/^OCR_NATIVE_(?:FAILED|DIAGNOSTIC)$/.test(e.message)&&!e.message.includes(secret));
    }
    assert.throws(()=>m.nativeResult({status:0,stdout:'',stderr:m.KNOWN_STDERR.join('\n')},dims),/OCR_OUTPUT_INVALID/);
});
test('Windows empty distinct from engine loss or inconsistent OCR',()=>{
    assert.equal(m.windowsResult({supported:true,text:'',lines:[]}).status,'empty');
    assert.throws(()=>m.windowsResult({supported:false,lines:[],text:null}),/OCR_WINDOWS_ENGINE_CHANGED/);
    assert.throws(()=>m.windowsResult({supported:true,text:'not empty',lines:[]}),/OCR_WINDOWS_OUTPUT/);
});
console.log('COURSE_OCR_UNIT='+cases);

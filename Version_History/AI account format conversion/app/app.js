const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
const input=$('#inputText'), fileInput=$('#fileInput'), chooseFileBtn=$('#chooseFileBtn'), drop=$('#dropZone'), detected=$('#detected'), hints=$('#hints'), cards=$('#cards'), preview=$('#preview code'), select=$('#formatSelect'), redact=$('#redactToggle'), toast=$('#toast');
const toggles={jwt:$('#jwtToggle'), rules:$('#rulesToggle'), vault:$('#vaultToggle'), complete:$('#completeToggle')};
let state={canon:null, outputs:[], active:0};
// Async imports may finish after the user clears, edits or selects another file.
let inputRevision=0;
function showToast(msg){toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2200)}
function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function downloadText(filename, content, type='text/plain;charset=utf-8'){const blob=new Blob([content],{type}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click(); URL.revokeObjectURL(a.href)}
function setPreview(){const out=state.outputs[state.active]; if(!out){preview.textContent='';return} preview.textContent=redact.checked?AccountConverter.redactText(out.content):out.content; select.value=out.id; $$('.card').forEach((c,i)=>c.classList.toggle('active',i===state.active));}
function inputForConvert(){
  const raw=input.value;
  if(!toggles.rules.checked) return raw;
  const txt=$('#rulesText').value.trim(); if(!txt) return raw;
  try{ const rules=JSON.parse(txt); const data=JSON.parse(raw); return JSON.stringify(AccountConverter.ruleMapObject(data,rules)); }
  catch(e){ showToast('规则 JSON 或输入 JSON 无法解析，已按原文转换'); return raw; }
}
function render(){
  const c=state.canon; if(!c){detected.className='detected empty'; detected.textContent='等待输入'; hints.innerHTML=''; cards.innerHTML=''; select.innerHTML=''; preview.textContent=''; $('#insightsPanel').classList.add('hidden'); return;}
  detected.className='detected'; const accs=c.accounts;
  detected.innerHTML=`<div><span class="pill ok">来源：${escapeHtml(c.source)}</span><span class="pill">账号数：${accs.length}</span><span class="pill">类型：${escapeHtml([...new Set(accs.map(a=>a.type))].join('/'))}</span></div>` + accs.map((a,i)=>`<div class="pill">#${i+1} ${escapeHtml(a.name||'account')} · ${escapeHtml(a.email||a.user_id||a.account_id||'unknown')} · ${escapeHtml(a.plan||a.platform||'')}</div>`).join('');
  hints.innerHTML=[...c.hints.map(x=>`<div class="good">${escapeHtml(x)}</div>`),...c.warnings.map(x=>`<div class="warn">${escapeHtml(x)}</div>`)].join('');
  cards.innerHTML=state.outputs.map((o,i)=>`<div class="card ${i===state.active?'active':''}" data-i="${i}"><b>${escapeHtml(o.title)}</b><small>${escapeHtml(o.desc)}</small></div>`).join('');
  cards.querySelectorAll('.card').forEach(card=>card.onclick=()=>{state.active=Number(card.dataset.i);setPreview()});
  select.innerHTML=state.outputs.map(o=>`<option value="${o.id}">${escapeHtml(o.title)}</option>`).join('');
  renderInsights(); setPreview();
}
function scoreClass(score){return score>=80?'good':score>=50?'warn':'bad'}
function renderInsights(){
  const c=state.canon; if(!c) return; $('#insightsPanel').classList.remove('hidden');
  const rep=AccountConverter.report(c);
  $('#reportBox').innerHTML=rep.accounts.map(a=>`<div class="acct-report"><b>#${a.index} ${escapeHtml(a.name)}</b><span class="score ${scoreClass(a.score.score)}">${escapeHtml(a.score.level)} · ${a.score.score}</span><p>${escapeHtml(a.score.reason)}</p><small>${escapeHtml(a.type)} · ${escapeHtml(a.email||a.user_id||a.account_id||'unknown')}<br>exp: ${escapeHtml(a.expires||'-')}<br>refresh: ${a.has_refresh_token?'有':'无'} · api_key: ${a.has_api_key?'有':'无'}</small></div>`).join('') + (rep.duplicates.length?rep.duplicates.map(d=>`<div class="dup-card"><b>重复疑似</b><p>${escapeHtml(d.key)} =&gt; #${d.indexes.join(', #')}</p></div>`).join(''):'<div class="dup-card"><b>重复检测</b><p>未发现 email/user/account/token fingerprint 重复。</p></div>');
  renderJwt(); renderComplete();
}
function renderJwt(){
  const box=$('#jwtBox'); box.classList.toggle('hidden',!toggles.jwt.checked); if(!toggles.jwt.checked||!state.canon) return;
  box.innerHTML=state.canon.accounts.map((a,i)=>{const toks=[['access_token',a.access_token],['id_token',a.id_token]].filter(([,v])=>v); if(!toks.length) return `<div class="jwt-item"><b>#${i+1} ${escapeHtml(a.name)}</b><pre>无 JWT token</pre></div>`; return toks.map(([k,v])=>{const d=AccountConverter.decodeJwt(v); return `<div class="jwt-item"><b>#${i+1} ${escapeHtml(a.name)} · ${k}</b><pre>${escapeHtml(JSON.stringify(d?d.payload:{error:'不是可解析 JWT'},null,2))}</pre></div>`}).join('');}).join('');
}
function renderComplete(){
  const box=$('#completeBox'); box.classList.toggle('hidden',!toggles.complete.checked); if(!toggles.complete.checked||!state.canon) return;
  box.innerHTML=`<table class="complete-table"><thead><tr><th>#</th><th>name</th><th>email</th><th>account_id</th><th>user_id</th><th>base_url</th><th>plan</th></tr></thead><tbody>${state.canon.accounts.map((a,i)=>`<tr data-i="${i}"><td>${i+1}</td>${['name','email','account_id','user_id','base_url','plan'].map(k=>`<td><input data-k="${k}" value="${escapeHtml(a[k]||'')}"></td>`).join('')}</tr>`).join('')}</tbody></table><div class="mini-actions"><button id="applyCompleteBtn" class="primary small">应用补全并重新生成</button></div>`;
  $('#applyCompleteBtn').onclick=()=>{inputRevision++;box.querySelectorAll('tr[data-i]').forEach(tr=>{const i=Number(tr.dataset.i); tr.querySelectorAll('input').forEach(inp=>state.canon.accounts[i][inp.dataset.k]=inp.value.trim());}); state.outputs=AccountConverter.convertAll(state.canon); render(); showToast('字段补全已应用');};
}
function convert(){inputRevision++;try{state.canon=AccountConverter.canonicalize(inputForConvert());state.outputs=AccountConverter.convertAll(state.canon);state.active=0;render();showToast('转换完成')}catch(e){state={canon:null,outputs:[],active:0};render();hints.innerHTML=`<div class="warn">${escapeHtml(e.message)}</div>`}}
function readFile(f){if(!f) return; const revision=++inputRevision; const reader=new FileReader(); reader.onload=()=>{if(revision!==inputRevision)return;input.value=String(reader.result||''); convert(); showToast(`已读取：${f.name}`)}; reader.onerror=()=>{if(revision===inputRevision)showToast(`读取失败：${f.name}`);}; reader.readAsText(f,'utf-8');}
chooseFileBtn.onclick=()=>{fileInput.value=''; fileInput.click();}; fileInput.onchange=e=>readFile(e.target.files&&e.target.files[0]);
['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('drag')})); ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('drag')})); drop.addEventListener('drop',e=>{const f=e.dataTransfer.files[0]; if(f) readFile(f)});
$('#convertBtn').onclick=convert; $('#clearBtn').onclick=()=>{inputRevision++;input.value='';state={canon:null,outputs:[],active:0};render()}; redact.onchange=setPreview; select.onchange=()=>{const i=state.outputs.findIndex(o=>o.id===select.value); if(i>=0){state.active=i;setPreview()}};
$('#copyBtn').onclick=async()=>{const out=state.outputs[state.active]; if(!out)return; await navigator.clipboard.writeText(out.content); showToast('已复制未脱敏内容')};
$('#downloadBtn').onclick=()=>{const out=state.outputs[state.active]; if(!out)return; downloadText(out.filename,out.content)};
input.addEventListener('input',()=>{inputRevision++;});
input.addEventListener('paste',()=>setTimeout(()=>{if(input.value.trim()) convert()},50));
Object.values(toggles).forEach(t=>t.onchange=()=>{ $('#rulesBox').classList.toggle('hidden',!toggles.rules.checked); $('#vaultBox').classList.toggle('hidden',!toggles.vault.checked); if(state.canon) renderInsights(); });

// ZIP: no compression, pure JS, no cache/temp.
const crcTable=(()=>{let c,t=[]; for(let n=0;n<256;n++){c=n; for(let k=0;k<8;k++) c=(c&1)?(0xedb88320^(c>>>1)):(c>>>1); t[n]=c>>>0;} return t;})();
function crc32(buf){let c=0xffffffff; for(const b of buf)c=crcTable[(c^b)&255]^(c>>>8); return (c^0xffffffff)>>>0}
function u16(n){return [n&255,(n>>>8)&255]} function u32(n){return [n&255,(n>>>8)&255,(n>>>16)&255,(n>>>24)&255]}
function makeZip(files){const enc=new TextEncoder(); let chunks=[], central=[], offset=0; for(const [name,content] of Object.entries(files)){const nameB=enc.encode(name), data=enc.encode(content), crc=crc32(data); const local=new Uint8Array([...u32(0x04034b50),...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(0),...u32(crc),...u32(data.length),...u32(data.length),...u16(nameB.length),...u16(0),...nameB,...data]); chunks.push(local); const cent=new Uint8Array([...u32(0x02014b50),...u16(20),...u16(20),...u16(0x800),...u16(0),...u16(0),...u16(0),...u32(crc),...u32(data.length),...u32(data.length),...u16(nameB.length),...u16(0),...u16(0),...u16(0),...u16(0),...u32(0),...u32(offset),...nameB]); central.push(cent); offset+=local.length;} const centralSize=central.reduce((a,b)=>a+b.length,0), total=offset+centralSize+22; const out=new Uint8Array(total); let p=0; [...chunks,...central].forEach(ch=>{out.set(ch,p);p+=ch.length}); out.set(new Uint8Array([...u32(0x06054b50),...u16(0),...u16(0),...u16(central.length),...u16(central.length),...u32(centralSize),...u32(offset),...u16(0)]),p); return out;}
$('#downloadZipBtn').onclick=()=>{if(!state.canon){showToast('请先转换');return} const files={}; state.outputs.forEach(o=>files[`outputs/${o.filename}`]=o.content); const pack=state.outputs.find(o=>o.id==='batch-files-pack'); if(pack){try{Object.assign(files,JSON.parse(pack.content).files||{})}catch{}} const zip=makeZip(files); const blob=new Blob([zip],{type:'application/zip'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='ai-account-converter-export.zip'; a.click(); URL.revokeObjectURL(a.href);};

// Optional encrypted vault: file export/import only, no local storage.
// Convert large ciphertext without exceeding the engine's function-argument limit.
function bytesToBase64(bytes){
  const chunks=[];
  for(let offset=0;offset<bytes.length;offset+=0x4000){
    chunks.push(String.fromCharCode(...bytes.subarray(offset,offset+0x4000)));
  }
  return btoa(chunks.join(''));
}
// Validate imported canonical data before replacing an existing conversion.
function checkedVaultCanon(obj){
  const canon=obj && obj.canon;
  if(!canon || typeof canon.source!=='string' || !Array.isArray(canon.accounts) ||
      !canon.accounts.length || !canon.accounts.every(a=>a && typeof a==='object' && !Array.isArray(a)) ||
      !['sources','hints','warnings'].every(k=>Array.isArray(canon[k]) && canon[k].every(v=>typeof v==='string'))){
    throw new Error('Invalid vault account data');
  }
  // JSON can contain an own non-callable toString property. Check every field
  // coerced by the UI now, so a rendering error cannot replace prior state.
  for(const account of canon.accounts){
    for(const name of ['name','type','email','user_id','account_id','plan','platform','expires','base_url']){
      String(account[name] ?? '');
    }
  }
  return canon;
}
async function keyFromPass(pass,salt){const enc=new TextEncoder(); const base=await crypto.subtle.importKey('raw',enc.encode(pass),'PBKDF2',false,['deriveKey']); return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:150000,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);}
$('#exportVaultBtn').onclick=async()=>{try{if(!state.canon) throw new Error('请先转换'); const pass=$('#vaultPass').value; if(!pass) throw new Error('请输入密码'); const salt=crypto.getRandomValues(new Uint8Array(16)), iv=crypto.getRandomValues(new Uint8Array(12)); const plain=new TextEncoder().encode(JSON.stringify({version:1,created_at:new Date().toISOString(),canon:state.canon})); const key=await keyFromPass(pass,salt); const ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},key,plain)); const vault={format:'ai-account-converter-vault',version:1,kdf:'PBKDF2-SHA256-150000',cipher:'AES-GCM',salt:btoa(String.fromCharCode(...salt)),iv:btoa(String.fromCharCode(...iv)),data:bytesToBase64(ct)}; downloadText('ai-account-vault.json',JSON.stringify(vault,null,2),'application/json');}catch(e){showToast(e.message)}};
$('#importVaultBtn').onclick=()=>{$('#vaultFileInput').value=''; $('#vaultFileInput').click();};
$('#vaultFileInput').onchange=e=>{const f=e.target.files&&e.target.files[0]; if(!f)return; const revision=++inputRevision; const r=new FileReader(); r.onload=async()=>{if(revision!==inputRevision)return;try{const pass=$('#vaultPass').value; if(!pass) throw new Error('请输入密码'); const v=JSON.parse(String(r.result)); const bin=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0)); const key=await keyFromPass(pass,bin(v.salt)); const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:bin(v.iv)},key,bin(v.data)); const obj=JSON.parse(new TextDecoder().decode(plain)); if(revision!==inputRevision)return; const canon=checkedVaultCanon(obj); const outputs=AccountConverter.convertAll(canon); const restoredInput=JSON.stringify(canon.accounts,null,2); state={canon,outputs,active:0}; input.value=restoredInput; render(); showToast('vault 已解密导入');}catch(err){if(revision===inputRevision)showToast('vault 解密失败：'+err.message)}}; r.readAsText(f,'utf-8');};

$('#offlineCheckBtn').onclick=()=>{const checks=[['网络 fetch',typeof window.fetch==='function'?'浏览器存在，但本工具代码未调用':'不可用'],['localStorage','未使用'],['sessionStorage','未使用'],['IndexedDB','未使用'],['Service Worker','未注册'],['Cache API','未使用']]; $('#insightsPanel').classList.remove('hidden'); $('#reportBox').innerHTML=checks.map(c=>`<div class="offline-card"><b>${c[0]}</b><p>${c[1]}</p></div>`).join(''); $('#jwtBox').classList.add('hidden'); $('#completeBox').classList.add('hidden'); showToast('离线自检完成：工具代码无联网/存储调用');};
render();

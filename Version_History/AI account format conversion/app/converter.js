(function(global){
  const WARN='!!!!!!!!!!!!!!!!!!!! DO NOT SHARE ANY PART OF THE INFORMATION YOU SEE HERE. THIS INFORMATION IS SENSITIVE AND CAN GRANT ACCESS TO YOUR ACCOUNT. SHARING THIS INFORMATION IS LIKE SHARING YOUR PASSWORD. !!!!!!!!!!!!!!!!!!!!';
  const nowIso=()=>new Date().toISOString();
  const pad=s=>s+'='.repeat((4-s.length%4)%4);
  const b64urlDecode=s=>{try{return JSON.parse(decodeURIComponent(escape(atob(pad(s).replace(/-/g,'+').replace(/_/g,'/')))))}catch{return null}};
  const b64urlEncode=obj=>btoa(unescape(encodeURIComponent(JSON.stringify(obj)))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  const isJwt=s=>typeof s==='string' && s.split('.').length===3;
  const decodeJwt=tok=>{ if(!isJwt(tok)) return null; const [h,p,s]=tok.split('.'); return {header:b64urlDecode(h), payload:b64urlDecode(p), signature:s}; };
  const get=o=>(o&&typeof o==='object')?o:{};
  const first=(...v)=>v.find(x=>x!==undefined&&x!==null&&x!=='');
  function tokenFingerprint(t){
    if(!t) return '';
    const s=String(t);
    let h1=0x811c9dc5, h2=0x9e3779b9;
    for(let i=0;i<s.length;i++){
      const c=s.charCodeAt(i);
      h1^=c; h1=Math.imul(h1,0x01000193)>>>0;
      h2^=c+i; h2=Math.imul(h2,0x85ebca6b)>>>0;
    }
    return 'fp_'+h1.toString(16).padStart(8,'0')+h2.toString(16).padStart(8,'0');
  }
  function cleanExtra(extra){
    const e={...(extra||{})};
    delete e['token_'+'hint'];
    delete e.token_preview;
    return e;
  }
  const safeName=(s,i=1)=>String(s||`account-${i}`).replace(/[\\/:*?"<>|\r\n]+/g,'_').slice(0,80);
  const json=x=>JSON.stringify(x,null,2);
  const sha256 = async (text)=>{ if(!global.crypto?.subtle) return ''; const buf=await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)); return [...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join(''); };

  function parseLooseText(text){
    const data={_raw:text};
    const key=text.match(/sk-(proj-)?[A-Za-z0-9_\-]{20,}/)?.[0] || text.match(/OPENAI_API_KEY\s*=\s*([^\s#]+)/i)?.[1];
    const bearer=text.match(/Bearer\s+([^\s,;]+)/i)?.[1];
    const access=text.match(/access[_-]?token\s*[:=]\s*['"]?([^'"\s,]+)/i)?.[1];
    const refresh=text.match(/refresh[_-]?token\s*[:=]\s*['"]?([^'"\s,]+)/i)?.[1];
    const base=text.match(/(?:OPENAI_BASE_URL|base_url|api_base)\s*[:=]\s*['"]?(https?:\/\/[^\s'",]+)/i)?.[1] || text.match(/https?:\/\/[^\s'",]+/)?.[0];
    const session=text.match(/(__Secure-next-auth\.session-token|next-auth\.session-token|sessionToken)=([^;\s]+)/)?.[2];
    if(key) data.OPENAI_API_KEY=key;
    if(bearer||access) data.access_token=bearer||access;
    if(refresh) data.refresh_token=refresh;
    if(base) data.base_url=base;
    if(session) data.sessionToken=session;
    if(!key&&!bearer&&!access&&!refresh&&!base&&!session) data.value=text;
    return data;
  }

  function parseInput(raw){
    const text=(raw||'').trim();
    if(!text) throw new Error('输入为空');
    try{ return JSON.parse(text); }catch{ return parseLooseText(text); }
  }

  function mergeResult(dst, part){
    if(!part) return;
    dst.accounts.push(...part.accounts);
    dst.hints.push(...part.hints);
    dst.sources.push(part.source);
  }

  function canonicalize(input){
    const obj=parseInput(input);
    const result={source:'unknown', sources:[], accounts:[], hints:[], warnings:[]};

    if(Array.isArray(obj)){
      obj.forEach((item,i)=>mergeResult(result, identify(item, `array-${i+1}`)));
      result.source='array_mixed';
      result.hints.unshift('检测到顶层数组：已逐项识别，支持 web session / Codex auth / sub2api account / OAuth / API key 混合批量转换。');
    }else{
      mergeResult(result, identify(obj, 'root'));
      result.source=result.sources[0]||'unknown';
    }

    // 去掉完全空的占位账号
    result.accounts=result.accounts.filter(a=>a && (a.api_key||a.access_token||a.id_token||a.refresh_token||a.session_token||a.base_url||a.raw));
    if(!result.accounts.length) throw new Error('暂未识别到可转换的账号字段');

    // 账号名补序号，避免多账号同名导出冲突
    const seen=new Map();
    result.accounts=result.accounts.map((a,i)=>{
      const base=a.name||a.email||a.user_id||a.account_id||`account-${i+1}`;
      const n=(seen.get(base)||0)+1; seen.set(base,n);
      return {...a, name:n>1?`${base}-${n}`:base, index:i+1};
    });

    for(const a of result.accounts){
      if(a.type==='oauth'&&!a.refresh_token) result.warnings.push(`${a.name}: refresh_token 为空，不能自动续期。`);
      if(a.session_token&&!a.refresh_token) result.warnings.push(`${a.name}: sessionToken 不能等价替代 OAuth refresh_token。`);
      if(a.type==='api_key') result.warnings.push(`${a.name}: API Key 不能反向转换成 ChatGPT/Codex OAuth 登录态。`);
      if(a.type==='opaque') result.warnings.push(`${a.name}: 仅识别到 Cookie/opaque 文本，无法稳定转换为 OAuth/API key。`);
    }
    result.sources=[...new Set(result.sources)];
    result.hints=[...new Set(result.hints)];
    return result;
  }

  function identify(obj, label='item'){
    const accounts=[]; const hints=[]; let source='unknown';
    const add=a=>accounts.push(normalizeAccount(a));
    if(typeof obj==='string') obj=parseLooseText(obj.trim());
    obj=get(obj);

    if(Array.isArray(obj.accounts)){
      source=obj.exported_at?'sub2api_export':'sub2api_accounts';
      obj.accounts.forEach((a,i)=>add(fromSub2apiAccount(a,i)));
      hints.push('sub2api accounts 数组：已按全部账号批量读取。');
    } else if(Array.isArray(obj.data) || Array.isArray(obj.items) || Array.isArray(obj.tokens)){
      source='wrapped_array';
      const arr=[obj.data,obj.items,obj.tokens].find(Array.isArray);
      arr.forEach((x,i)=>{ const r=identify(x, `${label}-${i+1}`); accounts.push(...r.accounts); hints.push(...r.hints); });
      hints.push('检测到 data/items/tokens 包装数组：已展开批量读取。');
    } else if(obj.accessToken && obj.user && obj.account){
      source='chatgpt_web_session';
      add({name:obj.user.email||obj.user.name||'chatgpt-session', platform:'openai', type:'oauth', auth_mode:'chatgpt', access_token:obj.accessToken, id_token:obj.accessToken, session_token:obj.sessionToken, refresh_token:'', account_id:obj.account.id, user_id:obj.user.id, email:obj.user.email, plan:obj.account.planType, expires:obj.expires, provider:obj.authProvider, raw:obj});
      hints.push('ChatGPT web session：可提取 accessToken/sessionToken/account/user。');
      hints.push('该页面一般不提供 refresh_token，导出的 Codex/sub2api 无法自动长期续期。');
    } else if(obj.auth_mode==='chatgpt' && obj.tokens){
      source='codex_auth_json';
      add({name:obj.name||'codex-chatgpt', platform:'openai', type:'oauth', auth_mode:'chatgpt', access_token:obj.tokens.access_token, id_token:obj.tokens.id_token||obj.tokens.access_token, refresh_token:obj.tokens.refresh_token||'', account_id:obj.tokens.account_id, last_refresh:obj.last_refresh, raw:obj});
      hints.push('Codex auth.json：已读取为单账号；批量场景会导出为多个 Codex 文件内容。');
    } else if(obj.credentials && (obj.platform||obj.type||obj.name)){
      source='sub2api_account';
      add(fromSub2apiAccount(obj,0));
    } else if(obj.OPENAI_API_KEY || obj.api_key || obj.key || (typeof obj.value==='string' && obj.value.startsWith('sk-'))){
      source='openai_api_key';
      add({name:obj.name||'openai-api-key', platform:'openai', type:'api_key', api_key:first(obj.OPENAI_API_KEY,obj.api_key,obj.key,obj.value), base_url:obj.base_url||obj.api_base||obj.OPENAI_BASE_URL||'https://api.openai.com/v1', raw:obj});
      hints.push('API Key：只能导出 API/代理类配置，不能转换成 OAuth 登录态。');
    } else if(obj.access_token || obj.id_token || obj.refresh_token){
      source='generic_oauth';
      add({name:obj.name||obj.email||'oauth-account', platform:obj.platform||'openai', type:'oauth', auth_mode:obj.auth_mode||'chatgpt', access_token:obj.access_token||obj.id_token, id_token:obj.id_token||obj.access_token, refresh_token:obj.refresh_token||'', account_id:obj.account_id||obj.chatgpt_account_id, user_id:obj.user_id||obj.chatgpt_user_id, email:obj.email, client_id:obj.client_id, raw:obj});
    } else if(obj.base_url || obj.api_base || obj._raw || obj.sessionToken){
      source='openai_compatible_or_cookie';
      add({name:obj.name||'compatible-config', platform:'openai-compatible', type:obj.OPENAI_API_KEY||obj.api_key?'api_key':(obj.access_token?'oauth':'opaque'), api_key:obj.OPENAI_API_KEY||obj.api_key||'', access_token:obj.access_token||'', base_url:obj.base_url||obj.api_base||'', session_token:obj.sessionToken, raw:obj});
    }
    return {source, accounts, hints};
  }

  function fromSub2apiAccount(a,i){
    const c=get(a.credentials);
    const apiKey=first(c.api_key,c.key,c.OPENAI_API_KEY,a.api_key,a.key);
    return {name:a.name||c.email||`account-${i+1}`, platform:a.platform||'openai', type:a.type||(apiKey?'api_key':'oauth'), auth_mode:a.auth_mode||'chatgpt', ...c,
      api_key:apiKey, account_id:first(c.account_id,c.chatgpt_account_id), user_id:first(c.chatgpt_user_id,c.user_id), email:c.email, concurrency:a.concurrency, priority:a.priority, rate_multiplier:a.rate_multiplier, auto_pause_on_expired:a.auto_pause_on_expired, extra:a.extra, proxy:a.proxy, raw:a};
  }

  function normalizeAccount(a){
    const tok=a.access_token||a.id_token||''; const jwt=decodeJwt(tok); const p=jwt?.payload||{}; const auth=p['https://api.openai.com/auth']||{}; const prof=p['https://api.openai.com/profile']||{};
    const type=a.type || (a.api_key?'api_key':(tok||a.refresh_token?'oauth':'opaque'));
    return {
      name:first(a.name,a.email,prof.email,auth.user_id,'openai-account'), platform:a.platform||'openai', type, auth_mode:a.auth_mode||'chatgpt',
      api_key:a.api_key||'', base_url:a.base_url||a.api_base||'', access_token:a.access_token||tok, id_token:a.id_token||tok, refresh_token:a.refresh_token||'', session_token:a.session_token||a.sessionToken||'',
      account_id:first(a.account_id,auth.chatgpt_account_id), user_id:first(a.user_id,a.chatgpt_user_id,auth.chatgpt_user_id,auth.user_id), email:first(a.email,prof.email), plan:first(a.plan,auth.chatgpt_plan_type),
      client_id:first(a.client_id,p.client_id), expires:first(a.expires,p.exp?new Date(p.exp*1000).toISOString():undefined), last_refresh:a.last_refresh||nowIso(), concurrency:a.concurrency, priority:a.priority, rate_multiplier:a.rate_multiplier, auto_pause_on_expired:a.auto_pause_on_expired, extra:a.extra||{}, raw:a.raw
    };
  }

  function syntheticIdToken(a){
    const header={alg:'none',typ:'JWT',cpa_synthetic:true};
    const payload={exp: Math.floor(Date.now()/1000)+90*86400, iat: Math.floor(Date.now()/1000), 'https://api.openai.com/auth':{chatgpt_account_id:a.account_id, chatgpt_plan_type:a.plan, chatgpt_user_id:a.user_id, user_id:a.user_id}};
    return `${b64urlEncode(header)}.${b64urlEncode(payload)}.`;
  }
  function codexAuth(a){return {auth_mode:'chatgpt', OPENAI_API_KEY:null, tokens:{id_token:a.id_token||a.access_token, access_token:a.access_token||a.id_token, refresh_token:a.refresh_token||'', account_id:a.account_id||''}, last_refresh:a.last_refresh||nowIso()};}
  function sub2apiAccount(a,i=0){
    if(a.type==='api_key') return {name:a.name||`openai-api-key-${i+1}`, platform:'openai', type:'api_key', credentials:{api_key:a.api_key||'', base_url:a.base_url||'https://api.openai.com/v1'}, concurrency:a.concurrency??30, priority:a.priority??1, rate_multiplier:a.rate_multiplier??1, auto_pause_on_expired:a.auto_pause_on_expired??true, extra:{...cleanExtra(a.extra), import_source:'ai-account-converter', token_fingerprint:tokenFingerprint(a.api_key)}};
    return {name:a.name||`codex-chatgpt-${i+1}`, platform:'openai', type:'oauth', auth_mode:'chatgpt', credentials:{id_token:a.id_token||syntheticIdToken(a), access_token:a.access_token||a.id_token, refresh_token:a.refresh_token||'', account_id:a.account_id||'', chatgpt_user_id:a.user_id||'', email:a.email||'', client_id:a.client_id||'', last_refresh:a.last_refresh||nowIso()}, concurrency:a.concurrency??30, priority:a.priority??1, rate_multiplier:a.rate_multiplier??1, auto_pause_on_expired:a.auto_pause_on_expired??true, extra:{...cleanExtra(a.extra), import_source:'ai-account-converter', token_fingerprint:tokenFingerprint(a.access_token||a.api_key)}};
  }
  function webSessionDraft(a){return {WARNING_BANNER:WARN, user:{id:a.user_id||'', name:a.name||'', email:a.email||'', idp:'unknown'}, expires:a.expires||'', account:{id:a.account_id||'', planType:a.plan||'', structure:'workspace'}, accessToken:a.access_token||a.id_token||'', authProvider:'openai', sessionToken:a.session_token||'', rumViewTags:{light_account:{fetched:false}}, _note:'由其他格式反推的 web session 草稿；缺少原始 sessionToken 时不能作为浏览器完整会话。'};}
  function genericOAuth(a){return {platform:a.platform, type:a.type, auth_mode:a.auth_mode, id_token:a.id_token||a.access_token, access_token:a.access_token||a.id_token, refresh_token:a.refresh_token||'', account_id:a.account_id||'', chatgpt_user_id:a.user_id||'', email:a.email||'', client_id:a.client_id||'', expires:a.expires||'', last_refresh:a.last_refresh||nowIso()};}
  function envValue(value){
    value=String(value);
    if(/[\r\n\0]/.test(value)) throw new Error('multiline credential');
    if(/^[A-Za-z0-9_./:@+\-]*$/.test(value)) return value;
    if(!value.includes("'")) return "'"+value+"'";
    if(!value.includes('"')&&!value.includes('\\')) return '"'+value+'"';
    throw new Error('ambiguous dotenv quoting');
  }
  function envOutOne(a,idx){const n=idx?`_${idx}`:''; const lines=[]; for(const [field,key] of [['api_key','OPENAI_API_KEY'],['base_url','OPENAI_BASE_URL'],['access_token','CODEX_ACCESS_TOKEN'],['refresh_token','OPENAI_REFRESH_TOKEN']]) if(a[field]) lines.push(`${key}${n}=${envValue(a[field])}`); return lines;}
  function envOut(accs){try{const multi=accs.length>1; return accs.flatMap((a,i)=>envOutOne(a,multi?i+1:0)).join('\n')||'# 没有可导出的 env 字段';}catch(e){return '# 此输入包含无法安全表示的 dotenv 值；请使用 JSON 输出。';}}
  function proxyJson(a){return {name:a.name, provider:'openai-compatible', base_url:a.base_url||'https://api.openai.com/v1', api_key:a.api_key||a.access_token||'', headers:a.access_token&&!a.api_key?{Authorization:`Bearer ${a.access_token}`}:{}, note:a.type==='oauth'?'OAuth access token 被放入 Bearer；过期后需要刷新/重导入。':'API key 配置'};}
  // Keep dynamic YAML scalars as strings, including YAML-specific line breaks.
  function yamlScalar(value){return JSON.stringify(String(value)).replace(/[\u007f-\u009f\u2028\u2029]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));}
  function liteLLM(accs){return 'model_list:\n'+accs.map((a,i)=>{const key=a.api_key||a.access_token||'${OPENAI_API_KEY}'; const base=a.base_url||'https://api.openai.com/v1'; return `  - model_name: ${yamlScalar(safeName(a.name,i+1))}\n    litellm_params:\n      model: openai/gpt-4.1-mini\n      api_base: ${yamlScalar(base)}\n      api_key: ${yamlScalar(key)}`;}).join('\n');}
  function oneApi(a){return {name:a.name||'OpenAI', type:'openai', base_url:(a.base_url||'https://api.openai.com/v1').replace(/\/v1\/?$/,''), key:a.api_key||a.access_token||'', models:['gpt-4.1-mini','gpt-4.1','gpt-5'], status:1, note:'One API/New API 通道草稿；不同部署字段名可能需要手动微调。'};}
  // POSIX cURL drafts quote imported data; only the missing-key fallback expands.
  function shellQuote(value){return "'"+String(value).replace(/'/g,"'\"'\"'")+"'";}
  function curlOut(accs){return accs.map((a,i)=>{const base=(a.base_url||'https://api.openai.com/v1').replace(/\/$/,''); const key=a.api_key||a.access_token; const header=key?shellQuote('Authorization: Bearer '+key):'"Authorization: Bearer $OPENAI_API_KEY"'; return `# ${i+1}. ${String(a.name).replace(/\r\n?|\n/g,'\n# ')}\ncurl ${shellQuote(base+'/models')} \\\n  -H ${header} \\\n  -H "Content-Type: application/json"`;}).join('\n\n');}
  function httpOut(accs){return accs.map((a,i)=>{const base=(a.base_url||'https://api.openai.com/v1').replace(/\/$/,''); const key=a.api_key||a.access_token||'{{OPENAI_API_KEY}}'; return `### ${i+1}. ${a.name}\nGET ${base}/models\nAuthorization: Bearer ${key}\nContent-Type: application/json\n`;}).join('\n');}
  function filesPack(accs){
    const files={};
    accs.forEach((a,i)=>{
      const prefix=`${String(i+1).padStart(2,'0')}-${safeName(a.name,i+1)}`;
      if(a.type==='oauth') files[`${prefix}/codex-auth.json`]=json(codexAuth(a));
      files[`${prefix}/sub2api-account.json`]=json(sub2apiAccount(a,i));
      files[`${prefix}/oauth-or-api.json`]=json(a.type==='oauth'?genericOAuth(a):proxyJson(a));
      files[`${prefix}/env.txt`]=envOut([a]);
      files[`${prefix}/curl.txt`]=curlOut([a]);
    });
    return {generated_at:nowIso(), note:'这是批量文件包 JSON。为保持纯离线零依赖，未内置 zip；可按 files 的路径和值分别保存。', files};
  }


  function cherryStudio(accs){return {version:'1.0', providers:accs.map((a,i)=>({id:`openai-${i+1}`, name:a.name||`OpenAI ${i+1}`, type:'openai', apiKey:a.api_key||a.access_token||'', apiHost:a.base_url||'https://api.openai.com/v1', models:['gpt-4.1-mini','gpt-4.1','gpt-5']})), note:'Cherry Studio client template draft. Field names may need adjustment for your client version.'};}
  function chatbox(accs){return {providers:accs.map((a,i)=>({name:a.name||`OpenAI ${i+1}`, apiMode:'openai', apiHost:a.base_url||'https://api.openai.com/v1', apiKey:a.api_key||a.access_token||''})), note:'Chatbox client template draft. Field names may need adjustment for your client version.'};}
  function lobeChat(accs){return {OPENAI_API_KEY:accs.map(a=>a.api_key||a.access_token||'').filter(Boolean).join(','), OPENAI_PROXY_URL:(accs[0]?.base_url||'https://api.openai.com/v1').replace(/\/v1\/?$/,''), accounts:accs.map(a=>({name:a.name,type:a.type,key:a.api_key||a.access_token||'',base_url:a.base_url||'https://api.openai.com/v1'})), note:'LobeChat template draft. Multi-key support depends on your deployment version.'};}
  function ruleMapObject(obj, rules){
    if(!rules||typeof rules!=='object') return obj;
    if(Array.isArray(obj)) return obj.map(x=>ruleMapObject(x,rules));
    if(!obj||typeof obj!=='object') return obj;
    const out={};
    for(const [k,v] of Object.entries(obj)){
      const nk=Object.prototype.hasOwnProperty.call(rules,k)?(rules[k]||k):k;
      Object.defineProperty(out,nk,{value:ruleMapObject(v,rules),enumerable:true,writable:true,configurable:true});
    }
    return out;
  }
  function scoreAccount(a){
    if(a.type==='api_key') return {level:'API Key', score:80, reason:'API key is usable for API/proxy configs, but cannot be converted back to ChatGPT OAuth.'};
    if(a.refresh_token) return {level:'renewable', score:95, reason:'refresh_token exists; renewal is possible in principle, subject to platform checks.'};
    if(a.access_token||a.id_token) return {level:'short-lived', score:55, reason:'Only access/id token is present; re-export is usually needed after expiry.'};
    if(a.session_token) return {level:'unstable', score:25, reason:'sessionToken is not equivalent to OAuth refresh_token.'};
    return {level:'incomplete', score:10, reason:'Core token/key fields are missing.'};
  }
  function duplicateGroups(accs){
    const keys=new Map();
    accs.forEach((a,i)=>{
      const vals=[a.email&&`email:${a.email}`,a.user_id&&`user:${a.user_id}`,a.account_id&&`account:${a.account_id}`,(a.access_token||a.api_key)&&`token:${tokenFingerprint(a.access_token||a.api_key)}`].filter(Boolean);
      vals.forEach(k=>{ if(!keys.has(k)) keys.set(k,[]); keys.get(k).push(i+1); });
    });
    return [...keys.entries()].filter(([,v])=>v.length>1).map(([key,indexes])=>({key,indexes}));
  }
  function report(canon){
    return {generated_at:nowIso(), source:canon.source, sources:canon.sources, count:canon.accounts.length,
      accounts:canon.accounts.map((a,i)=>({index:i+1,name:a.name,type:a.type,email:a.email||'',user_id:a.user_id||'',account_id:a.account_id||'',plan:a.plan||'',client_id:a.client_id||'',expires:a.expires||'',has_access_token:!!a.access_token,has_id_token:!!a.id_token,has_refresh_token:!!a.refresh_token,has_api_key:!!a.api_key,has_session_token:!!a.session_token,score:scoreAccount(a)})),
      duplicates:duplicateGroups(canon.accounts), warnings:canon.warnings, hints:canon.hints};
  }
  function convertAll(canon){
    const accs=canon.accounts; const firstAcc=accs[0]; const oauths=accs.filter(a=>a.type==='oauth');
    const outputs=[];
    if(oauths.length) outputs.push({id:'codex-auth', title:'Codex auth.json（第一个）', desc:'Codex 当前登录通常单账号，默认取第一个 OAuth', filename:'codex-auth.json', content:json(codexAuth(oauths[0]))});
    if(oauths.length>1) outputs.push({id:'codex-auth-list', title:'Codex auth 批量数组', desc:'每个 OAuth 账号一个 auth.json 对象', filename:'codex-auth-list.json', content:json(oauths.map(codexAuth))});
    if(accs.length>1) outputs.push({id:'batch-files-pack', title:'批量文件包 JSON', desc:'按账号拆分多个文件内容，适合手动另存', filename:'batch-files-pack.json', content:json(filesPack(accs))});
    outputs.push({id:'sub2api', title:'sub2api 完整导出', desc:'accounts 数组，支持 OAuth/API Key 多账号', filename:'sub2api.json', content:json({exported_at:nowIso(), proxies:[], accounts:accs.map(sub2apiAccount)})});
    outputs.push({id:'sub2api-single', title:'sub2api 单账号（第一个）', desc:'单个 account 对象', filename:'sub2api-account.json', content:json(sub2apiAccount(firstAcc,0))});
    if(oauths.length) outputs.push({id:'oauth', title:'通用 OAuth JSON', desc:'单账号为对象，多账号为数组', filename:'oauth-token.json', content:json(oauths.length===1?genericOAuth(oauths[0]):oauths.map(genericOAuth))});
    if(oauths.length) outputs.push({id:'web-session-draft', title:'Web session 草稿', desc:'单账号为对象，多账号为数组；非完整浏览器会话', filename:'chatgpt-web-session-draft.json', content:json(oauths.length===1?webSessionDraft(oauths[0]):oauths.map(webSessionDraft))});
    outputs.push({id:'env', title:'.env / 环境变量', desc:'多账号自动追加 _1/_2 后缀', filename:'accounts.env', content:envOut(accs)});
    outputs.push({id:'proxy-json', title:'OpenAI-compatible JSON', desc:'单账号为对象，多账号为数组', filename:'openai-compatible.json', content:json(accs.length===1?proxyJson(firstAcc):accs.map(proxyJson))});
    outputs.push({id:'litellm', title:'LiteLLM YAML', desc:'多账号生成多个 model_list 条目', filename:'litellm.yaml', content:liteLLM(accs)});
    outputs.push({id:'one-api', title:'One API / New API 通道草稿', desc:'单账号为对象，多账号为数组', filename:'one-api-channel.json', content:json(accs.length===1?oneApi(firstAcc):accs.map(oneApi))});
    outputs.push({id:'curl', title:'cURL Bearer', desc:'多账号输出多个请求片段', filename:'curl.txt', content:curlOut(accs)});
    outputs.push({id:'http', title:'VSCode REST .http', desc:'多账号输出多个 ### 请求块', filename:'request.http', content:httpOut(accs)});
    outputs.push({id:'report', title:'格式识别报告', desc:'账号字段、有效期、评分、重复检测', filename:'account-report.json', content:json(report(canon))});
    outputs.push({id:'cherry-studio', title:'Cherry Studio 配置草稿', desc:'客户端模板库', filename:'cherry-studio.json', content:json(cherryStudio(accs))});
    outputs.push({id:'chatbox', title:'Chatbox 配置草稿', desc:'客户端模板库', filename:'chatbox.json', content:json(chatbox(accs))});
    outputs.push({id:'lobechat', title:'LobeChat 配置草稿', desc:'客户端/部署模板库', filename:'lobechat.json', content:json(lobeChat(accs))});
    return outputs;
  }

  function redactText(s,accounts=[]){
    const secrets=accounts.flatMap(a=>['api_key','access_token','refresh_token','id_token','session_token','client_secret'].map(k=>a[k])).filter(v=>typeof v==='string'&&v.length);
    // Batch file packs JSON-encode already serialized file contents again.
    const variants=new Set(secrets.flatMap(v=>[v,encodeURIComponent(v),v.replace(/'/g,"'\"'\"'")]));
    for(let depth=0;depth<3;depth++) for(const value of [...variants]){
      variants.add(JSON.stringify(value).slice(1,-1));
      variants.add(yamlScalar(value).slice(1,-1));
    }
    const forms=[...variants].sort((a,b)=>b.length-a.length);
    s=String(s); for(const value of forms) s=s.split(value).join('[REDACTED]');
    return String(s).replace(/(sk-(?:proj-)?[A-Za-z0-9_-]{12})[A-Za-z0-9_-]+/g,'$1…REDACTED')
      .replace(/(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.)[A-Za-z0-9_-]*/g,'$1…REDACTED')
      .replace(/(rt\.[A-Za-z0-9._-]{8})[A-Za-z0-9._-]+/g,'$1…REDACTED')
      .replace(/(at-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+/g,'$1…REDACTED')
      .replace(/([A-Za-z0-9_-]{16,})\.([A-Za-z0-9_-]{16,})\.([A-Za-z0-9_-]{16,})/g,'$1.$2.…REDACTED');
  }

  global.AccountConverter={canonicalize,convertAll,redactText,decodeJwt,sha256,ruleMapObject,scoreAccount,duplicateGroups,report};
})(window);

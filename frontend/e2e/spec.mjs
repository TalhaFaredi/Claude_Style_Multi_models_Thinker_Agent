/** Exact production frontend against a deterministic HTTP/SSE fixture. No provider calls or credits.
 * Build: NEXT_PUBLIC_API_URL=http://127.0.0.1:8487 NEXT_BUILD_DIR=.next-spec-live next build --webpack
 * Run with node e2e/spec.mjs. Owns and closes its fixture and Next server.
 */
import { chromium } from 'playwright-core';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const results=[];
const defaultSettings={reader:'auto',askLimit:.5,monthBudget:5,longMemory:true,autoCompact:true,tempChat:false,chartDescriptions:true,keepPageImages:true,windowCap:32000,embeddings:true};
const simple={model:'sonnet',thinking:'medium',style:'balanced',tools:{web:true,code:false,files:true},maxTokens:1200};
const team={source:'same',model:'sonnet',agents:3,mixed:['sonnet','opus'],style:'independent',rounds:2,composer:'auto'};
const model=(id,name,tier,tools=true,vision=true,thinking=true)=>({id,name,company:id,provider:'openrouter',tier,tools,vision,thinking,costLevel:'$',callCost:.02,available:true,priceIn:1,priceOut:2,speed:'Fast'});
const models=[model('sonnet','Claude Sonnet 5.5',3),model('opus','Claude Opus 5.5',3),model('mistral','Mistral Large',2,true,false,false),model('llama','Llama 3.3',1,false,false,false)];
const context={percent:10,level:'normal',parts:[],windowTokens:32000,usableTokens:27200,usedTokens:2720};
const card={title:'Charts',pages:2,summary:'Contains ticket ZX-4928.',outline:[{title:'Facts',page:1}],tables:[],charts:[{page:2,description:'A chart.'}],weakPages:[],cost:.7};
const fp='a'.repeat(64);
let settings={...defaultSettings},failDelete=false,offline=false,failApprove=false,lastRun=null,lastApproval=null,lastPermission=null,lastTeam=null,forkCount=0;
const runs=new Map();
const send=(res,event)=>res.write(`data: ${JSON.stringify(event)}\n\n`);
const json=(res,data,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(data));};
const finish=(res,text='A checked answer.')=>{send(res,{type:'text',delta:text});send(res,{type:'cost',usd:.02,calls:2});send(res,{type:'context',...context});send(res,{type:'done',monthUsd:.02});res.end();};
const steps=(status='planned',extra={})=>[{task:'Research evidence',modeLabel:'Simple',kind:'easy',doneTest:'Includes a cited fact.',status,...extra}];
const fixture=createServer(async(req,res)=>{
  res.setHeader('access-control-allow-origin','*');res.setHeader('access-control-allow-headers','*');res.setHeader('access-control-allow-methods','GET,POST,PUT,DELETE,OPTIONS');
  if(req.method==='OPTIONS'){res.writeHead(204);res.end();return;}
  const url=new URL(req.url,'http://127.0.0.1:8487');
  let raw='';for await(const c of req)raw+=c;
  let body={};try{body=JSON.parse(raw||'{}');}catch{}
  if(url.pathname==='/api/config')return json(res,{version:'test',defaults:{simple,team,runIn:'auto',budget:.25,planModel:'sonnet'},qualityPresets:{fast:'mistral',balanced:'sonnet',best:'opus'},limits:{},providers:{openrouter:{ok:true,reason:''}},readers:Object.fromEntries(['auto','text','local','api','vision'].map(r=>[r,{available:true,reason:''}])),capabilities:{codeSandbox:true,zipPassword:true,embeddings:true,webSearch:true},settings,monthUsd:0});
  if(url.pathname==='/api/models')return json(res,models);
  if(url.pathname==='/api/usage')return json(res,{totalUsd:0,monthBudget:settings.monthBudget});
  if(url.pathname==='/api/settings'){settings={...settings,...body};return json(res,settings);}
  if(url.pathname==='/api/estimate')return json(res,{usd:body.prompt?.includes('expensive')?.8:body.mode==='thinker'?.2:.02,calls:2,kind:body.mode,breakdown:{},context});
  if(url.pathname==='/api/chats')return json(res,[]);
  if(url.pathname.endsWith('/context'))return json(res,context);
  if(url.pathname==='/api/memory')return json(res,{facts:[{id:1,text:'Ticket ZX-4928',source:'Nov 10, source chat'}],enabled:true});
  if(url.pathname==='/api/memory/1'){if(failDelete){failDelete=false;return json(res,{detail:'Delete temporarily unavailable'},503);}return json(res,{deleted:true});}
  if(url.pathname.endsWith('/fork')){forkCount++;return json(res,{chatId:'fork-chat',title:'Continued chat'});}
  if(url.pathname==='/api/chats/fork-chat')return json(res,{chat:{id:'fork-chat',title:'Continued chat',temp:false},messages:[{id:'summary',role:'sys',text:'Preserved ticket ZX-4928 in the session ledger.'}],context,files:[{fingerprint:fp,name:'charts.pdf',pages:2,ready:true,card,cost:0}],costUsd:0});
  if(url.pathname.endsWith('/files')&&req.method==='POST')return json(res,{fingerprint:fp,name:'charts.pdf',size:128,pages:2,kinds:{text:1,scan:0,chart:1,tables:0},plans:Object.fromEntries(['auto','text','local','api','vision'].map(r=>[r,{rows:[{label:'Chart page',kind:'chart',count:1,reader:r,cost:r==='text'?0:.7}],total:r==='text'?0:.7}])),readers:Object.fromEntries(['auto','text','local','api','vision'].map(r=>[r,{available:true,reason:''}])),readBefore:{}});
  if(url.pathname.endsWith('/read'))return json(res,{fingerprint:fp,reused:false,cost:body.textOnly?0:.7,card});
  if(url.pathname==='/api/runs'){
    lastRun=body;
    if(offline){req.socket.destroy();return;}
    res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-cache'});res.flushHeaders();runs.set(body.id,res);
    if(body.mode==='auto')send(res,{type:'route',kind:'simple',reason:'Auto chose Simple: a fact.'});
    send(res,{type:'status',text:'Working'});
    if(body.prompt.includes('permission')){send(res,{type:'permission',id:'permission-1',tool:'sandbox',description:'Run the displayed calculation.',arguments:{code:'print(2+2)'}});return;}
    if(body.mode==='planner'){
      const recovery=body.prompt.includes('team recovery');
      send(res,{type:'plan',phase:recovery?'Failed step: choose a recovery':'Waiting for your approval',steps:steps(recovery?'failed':'planned',recovery?{canUseTeam:true}:{}),awaitingApproval:true,estimateUsd:.02,version:'plan-v1'});return;
    }
    if(body.mode==='thinker')send(res,{type:'composer',model:'sonnet',status:'running',explanation:'Resolves disagreements with evidence.'});
    setTimeout(()=>{if(!res.destroyed){if(body.mode==='thinker')send(res,{type:'composer',model:'sonnet',status:'done',explanation:'Merged the supported conclusions.'});finish(res);}},400);return;
  }
  const control=url.pathname.match(/^\/api\/runs\/([^/]+)\/(approve|edit|permission|use-team|stop)$/);
  if(control){
    const stream=runs.get(control[1]),action=control[2];
    if(action==='approve'&&failApprove){failApprove=false;return json(res,{detail:'Approval temporarily unavailable'},503);}
    if(action==='approve')lastApproval=body;
    if(action==='permission')lastPermission=body;
    if(action==='use-team')lastTeam=body;
    json(res,{ok:true});
    if(action==='edit'){send(stream,{type:'plan',phase:'Waiting for your approval',steps:steps(),awaitingApproval:true,estimateUsd:.02,version:'plan-v2'});return;}
    if(action==='stop'){send(stream,{type:'done'});stream.end();return;}
    if(action==='permission')send(stream,{type:'permission',id:'permission-1',tool:'sandbox',description:'Decision recorded.',resolved:true});
    if(action==='approve'||action==='use-team'){send(stream,{type:'plan',phase:'Finished',steps:steps('done'),awaitingApproval:false,version:'plan-v1'});send(stream,{type:'output',file:{name:'report.pdf',pages:1,sources:1,checked:true}});}
    finish(stream);return;
  }
  return json(res,{ok:true});
});
await new Promise((resolve)=>fixture.listen(8487,'127.0.0.1',resolve));
const next=spawn(process.execPath,[path.join(root,'node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port','3138'],{cwd:root,env:{...process.env,NEXT_BUILD_DIR:'.next-spec-live'},windowsHide:true,stdio:['ignore','pipe','pipe']});
let serverLog='';next.stdout.on('data',d=>serverLog+=d);next.stderr.on('data',d=>serverLog+=d);
const browser=await chromium.launch({channel:process.env.E2E_CHANNEL??'msedge',headless:true});
const errors=[];
let page;
const check=(name,condition)=>{if(!condition)throw new Error(name);results.push({name,pass:true});console.log('PASS',name);};
const wait=async(fn)=>{for(let i=0;i<100;i++){if(await fn())return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timed out waiting for condition');};
const mode=(n)=>page.getByRole('group',{name:'Mode',exact:true}).getByRole('button',{name:n,exact:true});
const dialog=()=>page.getByRole('dialog');
const setup=()=>page.getByRole('button',{name:'Set up this mode'}).click();
const close=async()=>{await page.keyboard.press('Escape');await dialog().waitFor({state:'detached'});};
const ask=async(text)=>{await page.locator('textarea').fill(text);await page.getByRole('button',{name:'Send',exact:true}).click();};
const idle=()=>page.getByRole('button',{name:'Send',exact:true}).waitFor();
const settingsOpen=()=>page.getByRole('button',{name:'Settings, memory, data',exact:true}).click();
const fresh=async()=>{if(page)await page.context().close();settings={...defaultSettings};const c=await browser.newContext();page=await c.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:3138/app',{waitUntil:'networkidle'});await page.getByText('What should we work on?').waitFor();};
try{
  await wait(async()=>{try{return(await fetch('http://127.0.0.1:3138')).ok;}catch{return false;}});
  await fresh();check('F1 empty Send stays disabled',await page.getByRole('button',{name:'Send',exact:true}).isDisabled());
  await page.evaluate(({simple,team})=>localStorage.setItem('mma-chat-config-live',JSON.stringify({state:{mode:'thinker',simple,team:{...team,source:'mixed',mixed:['sonnet']},runIn:'auto',planModel:'sonnet',budget:1},version:1})),{simple,team});await page.reload({waitUntil:'networkidle'});await page.locator('textarea').fill('Compare models');check('F2 invalid persisted team blocks Send and explains',await page.getByRole('button',{name:'Send',exact:true}).isDisabled()&&await page.getByText('Pick at least 2 models').isVisible());
  await fresh();await mode('Thinker').click();await setup();for(let i=0;i<4;i++)await dialog().getByRole('button',{name:'More agents'}).click();check('F3 fifth agent is limit with toast',await page.getByText('At most 5 agents').isVisible()&&await page.locator('.stepper-val').first().innerText()==='5');await close();
  await mode('Simple').click();await setup();await dialog().getByRole('button',{name:'Web search',exact:true}).click();await dialog().getByRole('button',{name:'Claude Sonnet 5.5',exact:true}).click();check('F4 File reader alone disables models without tools',await dialog().getByRole('button',{name:/Llama 3\.3/}).isDisabled());await dialog().getByRole('button',{name:/Mistral Large/}).click();await dialog().getByRole('button',{name:'Done',exact:true}).click();check('F6 nonthinking model uses Off and disables High',await dialog().getByRole('group',{name:'Thinking level'}).getByRole('button',{name:'Off'}).getAttribute('aria-pressed')==='true'&&await dialog().getByRole('group',{name:'Thinking level'}).getByRole('button',{name:'High'}).isDisabled());await close();
  await page.getByRole('button',{name:'Attach a file'}).click();await dialog().locator('input[type=file]').setInputFiles({name:'charts.pdf',mimeType:'application/pdf',buffer:Buffer.from('fixture')});await dialog().getByText(/Approved maximum/).waitFor();check('F8 expensive file shows amber threshold and Text only',await dialog().getByText(/Over your.*ask-me limit/).isVisible()&&await dialog().getByRole('button',{name:'Text only (free)'}).isVisible());await dialog().getByRole('button',{name:/Read file/}).click();await page.locator('.fchip').getByText('Ready',{exact:true}).waitFor();await setup();await dialog().getByRole('button',{name:'Mistral Large',exact:true}).click();check('F5 charts disable nonvision models',await dialog().getByRole('button',{name:/Mistral Large/}).isDisabled());await dialog().getByRole('button',{name:'Done',exact:true}).click();await close();
  await fresh();await ask('An expensive question');await page.getByRole('dialog',{name:'Over your budget'}).waitFor();check('F7 no run starts before budget choice',lastRun===null);await dialog().getByRole('button',{name:/Allow up to/}).click();await idle();check('F7 allow once uses disclosed hard cap',lastRun.budgetUsd===1&&lastRun.allowOver===true);
  await ask('A normal question');await page.getByRole('button',{name:'Stop',exact:true}).waitFor();check('F9 mode locked during live answer',await mode('Planner').isDisabled());await idle();
  await mode('Planner').click();failApprove=true;await ask('Make a report');await page.getByRole('button',{name:'Approve and run'}).waitFor();check('F10 plan shows done-test and waits for approval',await page.getByText('Done when: Includes a cited fact.').isVisible()&&lastApproval===null);await page.getByRole('button',{name:'Approve and run'}).click();await page.getByText(/Approval temporarily unavailable/).first().waitFor();check('Failed approval keeps retryable Approve button',await page.getByRole('button',{name:'Approve and run'}).isEnabled());await page.getByRole('button',{name:'Approve and run'}).click();await idle();check('Approval sends exact plan version',lastApproval.planVersion==='plan-v1');
  await settingsOpen();await page.getByRole('tab',{name:'Memory',exact:true}).click();failDelete=true;await dialog().getByRole('button',{name:'Delete',exact:true}).click();check('F11 memory delete asks Keep or Delete',await dialog().getByRole('button',{name:'Keep',exact:true}).isVisible());await dialog().getByRole('button',{name:'Delete',exact:true}).click();await page.getByText('Delete temporarily unavailable').waitFor();check('Failed memory delete keeps the fact',await dialog().getByText('Ticket ZX-4928',{exact:true}).isVisible());await dialog().getByRole('button',{name:'Delete',exact:true}).click();await wait(async()=>await dialog().getByText('Ticket ZX-4928',{exact:true}).count()===0);check('Memory removed only after success',true);
  await dialog().getByRole('switch',{name:'Remember facts across chats'}).click();await page.getByRole('tab',{name:'Data and safety'}).click();await dialog().getByRole('switch',{name:/Temporary chat/}).click();await dialog().getByRole('button',{name:'Reset everything to safe defaults'}).click();await wait(()=>Promise.resolve(settings.tempChat===false&&settings.longMemory===true));check('F12 full reset clears Temporary chat',await dialog().getByRole('switch',{name:/Temporary chat/}).getAttribute('aria-checked')==='false');await page.getByRole('tab',{name:'Memory',exact:true}).click();check('F12 full reset restores long-term memory',await dialog().getByRole('switch',{name:'Remember facts across chats'}).getAttribute('aria-checked')==='true');await close();
  await mode('Thinker').click();await setup();await dialog().getByRole('button',{name:/Different models/}).click();await dialog().getByRole('button',{name:/Pick models/}).click();await dialog().getByRole('button',{name:/Llama 3\.3/}).click();await dialog().getByRole('button',{name:'Done',exact:true}).click();check('F13 mixed strengths warn and suggest similar models',await dialog().getByText(/A weak model can pull/).isVisible());await close();
  await fresh();offline=true;await ask('Keep this offline message');await page.getByText(/Connection lost\. Your message is kept as a draft/).first().waitFor();check('Offline send restores exact draft',await page.locator('textarea').inputValue()==='Keep this offline message');offline=false;await page.getByRole('button',{name:'Retry',exact:true}).click();await idle();check('Offline Retry completes without dropping original question',await page.locator('.user').count()===1);
  await ask('permission action');await page.getByRole('button',{name:'Deny',exact:true}).waitFor();await page.getByRole('button',{name:'Deny',exact:true}).click();await idle();check('Risky tool requires and transmits explicit denial',lastPermission.id==='permission-1'&&lastPermission.allow===false);
  await page.getByRole('button',{name:/Memory window/}).click();await dialog().getByRole('button',{name:/New chat with summary/}).click();await page.getByText('Preserved ticket ZX-4928 in the session ledger.').waitFor();check('Summary continuation opens actual persisted fork and cards',forkCount===1&&await page.locator('.fchip').count()===1);
  await mode('Planner').click();await ask('team recovery');await page.getByRole('button',{name:'Use the team for step 1'}).click();await idle();check('Failed Simple step can explicitly use team',lastTeam.step===0);
  check('No browser page errors',errors.length===0);
}catch(e){results.push({name:e.message,pass:false});console.error(e);if(page)await page.screenshot({path:path.join(root,'e2e/spec-failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}
finally{await browser.close();for(const res of runs.values())res.end();await new Promise(r=>fixture.close(r));next.kill();fs.writeFileSync(path.join(root,'e2e/spec-results.json'),JSON.stringify({results,errors,serverLog},null,2));console.log(`${results.filter(r=>r.pass).length}/${results.length} checks passed`);}

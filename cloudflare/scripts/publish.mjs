import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,existsSync,mkdirSync,unlinkSync} from 'node:fs';
import {createHash,randomBytes} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {createInterface} from 'node:readline/promises';
import {smartschoolCode} from '../src/embed.mjs';

const writePrivate=(path,data)=>writeFileSync(path,data,{mode:0o600});
export function deployedOrigin(output,workerName) {
  const entries=output.trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
  const last=entries.filter(x=>x.type==='deploy' && x.version_id).at(-1);
  for(const target of last?.targets || []) {
    try {const url=new URL(target);if(url.protocol==='https:' && url.hostname.startsWith(workerName+'.') && url.hostname.endsWith('.workers.dev') && !url.username && !url.password) return url.origin;}catch{}
  }
  throw new Error('Geen bevestigde workers.dev-link ontvangen. Bekijk de melding van Cloudflare; er is geen link verzonnen.');
}

export async function publish({root,run,chooseAccount,check,log=console.log}) {
  const privateDir=join(root,'private-import');mkdirSync(privateDir,{recursive:true});
  const statePath=join(privateDir,'installation.json'),configPath=join(root,'.wrangler.publish.json');
  if(!existsSync(join(privateDir,'import.sql'))) throw new Error('De kalenderimport ontbreekt. Pak het volledige ZIP-bestand uit.');
  let identity;
  try{identity=JSON.parse(await run(['whoami','--json'],{capture:true}));}catch{}
  if(!identity?.loggedIn) {
    log('Je browser opent voor aanmelden bij Cloudflare. Gebruik je gratis account.');
    await run(['login','--scopes','account:read','user:read','workers_scripts:write','d1:write'],{interactive:true});
    identity=JSON.parse(await run(['whoami','--json'],{capture:true}));
  }
  if(!identity.loggedIn || !identity.accounts?.length) throw new Error('Geen Cloudflare-account gevonden. Rond eerst de aanmelding af.');
  let state=existsSync(statePath) ? JSON.parse(readFileSync(statePath,'utf8')) : null;
  const selected=state ? identity.accounts.find(x=>x.id===state.accountId) : identity.accounts.length===1 ? identity.accounts[0] : await chooseAccount(identity.accounts);
  if(!selected) throw new Error('De eerdere installatie hoort bij een ander account. Gebruik dat account om verder te gaan.');
  if(!state) {
    const suffix=randomBytes(3).toString('hex');
    state={accountId:selected.id,workerName:'telescoop-kalender-'+suffix,databaseName:'telescoop-kalender-'+suffix,editorToken:randomBytes(32).toString('hex')};
    writePrivate(statePath,JSON.stringify(state,null,2));
  }
  if(state.databaseName!==state.workerName || !/^[a-f0-9]{64}$/.test(state.editorToken) || !/^telescoop-kalender-[a-f0-9]{6}$/.test(state.workerName)) throw new Error('Installatiebestand is ongeldig. Bewaar dit bestand en herstel het uit je kopie.');
  const config=JSON.parse(readFileSync(join(root,'wrangler.jsonc'),'utf8'));
  config.name=state.workerName;config.account_id=selected.id;
  const env={CLOUDFLARE_ACCOUNT_ID:selected.id};
  let databases=JSON.parse(await run(['d1','list','--json'],{capture:true,env}));
  let database=databases.find(x=>x.name===state.databaseName);
  if(!database) {
    if(state.databaseId) throw new Error('De eerder gebruikte database is niet gevonden. Er wordt geen lege vervanging gemaakt.');
    log('Kalenderdatabase aanmaken...');
    await run(['d1','create',state.databaseName,'--location','weur','--update-config=false'],{interactive:true,env});
    databases=JSON.parse(await run(['d1','list','--json'],{capture:true,env}));database=databases.find(x=>x.name===state.databaseName);
  }
  if(!database?.uuid || (state.databaseId && state.databaseId!==database.uuid)) throw new Error('De database kon niet eenduidig worden gekoppeld.');
  state.databaseId=database.uuid;writePrivate(statePath,JSON.stringify(state,null,2));
  config.d1_databases=[{binding:'DB',database_name:state.databaseName,database_id:state.databaseId}];
  writePrivate(configPath,JSON.stringify(config,null,2));
  const d1=['d1','execute',state.databaseName,'--remote','--config',configPath,'--yes'];
  log('Schema en aangeleverde kalender overzetten...');
  await run([...d1,'--file',join(root,'schema.sql')],{interactive:true,env});
  await run([...d1,'--file',join(privateDir,'import.sql')],{interactive:true,env});
  const secrets=join(privateDir,'deploy-secrets.json'),outputPath=join(privateDir,'deploy-result.jsonl');
  writePrivate(secrets,JSON.stringify({EDITOR_TOKEN_SHA256:createHash('sha256').update(state.editorToken).digest('hex')}));
  writePrivate(outputPath,'');
  try {
    log('Kalender publiceren... Er wordt geen betaald abonnement of domein aangeschaft.');
    await run(['deploy','--config',configPath,'--secrets-file',secrets],{interactive:true,env:{...env,WRANGLER_OUTPUT_FILE_PATH:outputPath}});
  } finally {unlinkSync(secrets);}
  const origin=deployedOrigin(readFileSync(outputPath,'utf8'),state.workerName);
  const manager=origin+'/beheer#sleutel='+state.editorToken;
  writePrivate(join(privateDir,'BEHEERLINK.txt'),'Persoonlijke beheerlink - houd deze vertrouwelijk:\n'+manager+'\n\nOpenbare kalender:\n'+origin+'/smartschool-calendar\n');
  writeFileSync(join(root,'SMARTSCHOOL-code.txt'),smartschoolCode(origin)+'\n');
  writeFileSync(join(root,'KALENDER-LINK.txt'),origin+'/smartschool-calendar\n');
  state.origin=origin;writePrivate(statePath,JSON.stringify(state,null,2));
  log('Online controle uitvoeren...');
  await check(origin,state.editorToken);
  log('KLAAR. Open private-import/BEHEERLINK.txt voor beheer en SMARTSCHOOL-code.txt voor de HTML-code.');
  return {origin};
}

async function onlineCheck(origin,token) {
  for(let attempt=0;attempt<6;attempt++) {
    try {
      const health=await fetch(origin+'/health',{signal:AbortSignal.timeout(10000)});
      if(!health.ok || !(await health.json()).ok) throw Error('Databasecontrole mislukt.');
      const response=await fetch(origin+'/smartschool-calendar',{signal:AbortSignal.timeout(10000)}),body=await response.text();
      if(!response.ok || !body.includes('Kalender wijzigen') || !body.includes('content="1800"')) throw Error('Leesweergave niet gereed.');
      const edit=await fetch(origin+'/api/manage/links',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(10000)});
      if(!edit.ok) throw Error('Beheersleutelcontrole mislukt.');
      return;
    }catch(error){if(attempt===5) throw new Error('Publicatie uitgevoerd, maar online controle nog niet geslaagd: '+error.message+' De links zijn opgeslagen. Start opnieuw om de controle te herhalen.');await new Promise(r=>setTimeout(r,1500));}
  }
}

if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
  const cli=join(root,'node_modules','wrangler','bin','wrangler.js');
  const run=(args,options={})=>new Promise((resolveRun,reject)=>{
    const child=spawn(process.execPath,[cli,...args],{cwd:root,env:{...process.env,WRANGLER_SEND_METRICS:'false',...options.env},stdio:options.capture ? ['ignore','pipe','pipe'] : 'inherit',shell:false});
    let output='',errors='';if(options.capture){child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>errors+=x);}
    child.once('error',reject);child.once('close',code=>code===0?resolveRun(output):reject(new Error('Cloudflare-opdracht mislukt ('+args.slice(0,2).join(' ')+'). '+errors.slice(-1000))));
  });
  const chooseAccount=async accounts=>{
    accounts.forEach((a,i)=>console.log(`${i+1}. ${a.name}`));const reader=createInterface({input:process.stdin,output:process.stdout});
    try{const value=await reader.question('Welk account wil je gebruiken? Geef het nummer: ');return accounts[Number(value)-1];}finally{reader.close();}
  };
  try{if(Number(process.versions.node.split('.')[0])<24) throw new Error('Installeer eerst Node.js 24 of nieuwer via https://nodejs.org/');await publish({root,run,chooseAccount,check:onlineCheck});}
  catch(error){console.error('\nNIET AFGEROND: '+error.message);process.exitCode=1;}
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,copyFileSync,readFileSync,writeFileSync,existsSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {publish,deployedOrigin} from '../scripts/publish.mjs';

test('publicatie hervat na fout zonder extra database, sleutelrotatie of gefabriceerde link',async()=>{
  const root=mkdtempSync(join(tmpdir(),'calendar-publish-'));mkdirSync(join(root,'private-import'));
  copyFileSync(new URL('../wrangler.jsonc',import.meta.url),join(root,'wrangler.jsonc'));
  writeFileSync(join(root,'private-import','import.sql'),'SELECT 1;');
  let loggedIn=false,databases=[],failDeploy=true,created=0,checked=0,deploys=0,lastConfig;
  const run=async(args,options={})=>{
    const command=args.slice(0,2).join(' ');
    if(command==='whoami --json'){if(!loggedIn)throw Error('not signed in');return JSON.stringify({loggedIn:true,accounts:[{id:'account1',name:'Test'}]});}
    if(args[0]==='login'){loggedIn=true;return '';}
    if(command==='d1 list')return JSON.stringify(databases);
    if(command==='d1 create'){created++;databases.push({name:args[2],uuid:'db1'});return '';}
    if(command==='d1 execute')return '';
    if(args[0]==='deploy'){
      deploys++;lastConfig=JSON.parse(readFileSync(args[args.indexOf('--config')+1]));
      const secrets=JSON.parse(readFileSync(args[args.indexOf('--secrets-file')+1]));
      const state=JSON.parse(readFileSync(join(root,'private-import','installation.json')));
      assert.equal(secrets.EDITOR_TOKEN_SHA256,createHash('sha256').update(state.editorToken).digest('hex'));
      assert.ok(!JSON.stringify(lastConfig).includes(state.editorToken));
      if(failDeploy)throw Error('deployment interrupted');
      writeFileSync(options.env.WRANGLER_OUTPUT_FILE_PATH,JSON.stringify({type:'deploy',version:1,version_id:'version1',targets:[`https://${lastConfig.name}.test.workers.dev`]})+'\n');return '';
    }
    throw Error('unexpected '+command);
  };
  const options={root,run,chooseAccount(){throw Error('should use only account');},async check(origin,token){checked++;assert.match(origin,/^https:\/\/telescoop-kalender-/);assert.match(token,/^[a-f0-9]{64}$/);},log(){}};
  try {
    await assert.rejects(publish(options),/deployment interrupted/);
    const first=JSON.parse(readFileSync(join(root,'private-import','installation.json')));
    assert.equal(existsSync(join(root,'private-import','deploy-secrets.json')),false);
    assert.equal(existsSync(join(root,'SMARTSCHOOL-code.txt')),false);
    failDeploy=false;const result=await publish(options);
    const second=JSON.parse(readFileSync(join(root,'private-import','installation.json')));
    assert.equal(created,1);assert.equal(deploys,2);assert.equal(checked,1);assert.equal(first.editorToken,second.editorToken);assert.equal(first.databaseId,second.databaseId);
    const code=readFileSync(join(root,'SMARTSCHOOL-code.txt'),'utf8');assert.ok(code.includes(result.origin+'/smartschool-calendar'));assert.ok(!code.includes(first.editorToken));
    assert.ok(readFileSync(join(root,'private-import','BEHEERLINK.txt'),'utf8').includes('/beheer#sleutel='+first.editorToken));
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('alleen een bevestigde publicatie op de verwachte workers.dev-host levert links op',()=>{
  const worker='telescoop-kalender-123456';
  const entry={type:'deploy',version:1,version_id:'id',targets:['https://'+worker+'.school.workers.dev']};
  assert.equal(deployedOrigin(JSON.stringify(entry),worker),'https://'+worker+'.school.workers.dev');
  for(const invalid of [{...entry,version_id:null},{...entry,targets:['https://other.school.workers.dev']},{...entry,targets:['https://'+worker+'.evil.example']},{...entry,type:'version-upload'}]) assert.throws(()=>deployedOrigin(JSON.stringify(invalid),worker));
});

import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import worker from '../src/worker.mjs';
const TOKEN='a'.repeat(64);
export function harness() {
  const sqlite=new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('../schema.sql',import.meta.url),'utf8'));
  const DB={prepare(sql){return {bind(...args){const statement=sqlite.prepare(sql);return {
    async all(){return {results:statement.all(...args)};},
    async first(){return statement.get(...args) || null;},
    async run(){const result=statement.run(...args);return {meta:{changes:Number(result.changes)}};}
  };}}}};
  const env={DB,EDITOR_TOKEN_SHA256:createHash('sha256').update(TOKEN).digest('hex')};
  async function call(path,method='GET',body,token=TOKEN){
    const headers=token ? {Authorization:`Bearer ${token}`} : {};
    if(body) headers['Content-Type']='application/json';
    return worker.fetch(new Request('https://example.workers.dev'+path,{method,headers,body:body?JSON.stringify(body):undefined}),env);
  }
  return {call,sqlite,env};
}

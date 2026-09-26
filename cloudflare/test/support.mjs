import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import worker from '../src/worker.mjs';
const TOKEN='a'.repeat(64);
export function harness() {
  const sqlite=new DatabaseSync(':memory:'),queries=[];
  sqlite.exec(readFileSync(new URL('../schema.sql',import.meta.url),'utf8'));
  const DB={prepare(sql){return {bind(...args){const statement=sqlite.prepare(sql);return {
    async all(){const results=statement.all(...args);queries.push({sql,rows:results.length});return {results};},
    async first(){const result=statement.get(...args) || null;queries.push({sql,rows:result?1:0});return result;},
    async run(){const result=statement.run(...args);queries.push({sql,rows:0});return {meta:{changes:Number(result.changes)}};}
  };}}},async batch(statements){sqlite.exec('BEGIN');try{const results=[];for(const s of statements)results.push(await s.all());sqlite.exec('COMMIT');return results;}catch(e){sqlite.exec('ROLLBACK');throw e;}}};
  const env={DB,EDITOR_TOKEN_SHA256:createHash('sha256').update(TOKEN).digest('hex')};
  async function call(path,method='GET',body,token=TOKEN,extraHeaders={}){
    const headers={...(token ? {Authorization:`Bearer ${token}`} : {}),...extraHeaders};
    if(body) headers['Content-Type']='application/json';
    return worker.fetch(new Request('https://example.workers.dev'+path,{method,headers,body:body?JSON.stringify(body):undefined}),env);
  }
  return {call,sqlite,env,queries};
}

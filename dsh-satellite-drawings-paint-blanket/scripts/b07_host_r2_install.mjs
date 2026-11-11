// Exercise the deployed private installer + real CLI, exclusively in a synthetic /data/qmh home.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..'),out=root+'/work/host-r2';
const runtime='/data/lbk/codex_web/deepseek-harness-no-history';
const {initProfile,loadProfileDirectory}=await import(pathToFileURL(runtime+'/packages/boot/app-boot/lib/index.js'));
const {inspectPrivateArchive}=await import(pathToFileURL(runtime+'/packages/custom/auth/src/server/private-plugin-policy.ts'));
const packages=JSON.parse(await fs.readFile(out+'/packages.json','utf8'));
const work=await fs.mkdtemp('/data/qmh/b07-host-r2-install-'),user='b07-installer-fixture';
const home=work+'/users/'+createHash('sha256').update(user).digest('hex')+'/home';
await fs.mkdir(home,{recursive:true,mode:0o700});
const profile=work+'/public';initProfile(profile,[]);await fs.mkdir(profile+'/node_modules');
await fs.writeFile(home+'/private-plugin-context.json',JSON.stringify({userId:user,home,harnessRoot:runtime,systemProfileDir:profile,trustedPrivatePluginDigests:packages.map(p=>p.sha256)}),{mode:0o600});
const records=[];
for(const pkg of packages){assert.throws(()=>inspectPrivateArchive(pkg.path,[]),/not operator-approved/);inspectPrivateArchive(pkg.path,[pkg.sha256]);}
async function command(args){
 const argv=['--import',runtime+'/node_modules/tsx/dist/loader.mjs',runtime+'/packages/custom/auth/src/server/private-plugin-install.mjs','--account-home',home,...args];
 const child=spawn(process.execPath,argv,{cwd:work,env:{PATH:path.dirname(process.execPath)+':'+runtime+'/node_modules/.bin:/usr/bin:/bin',XDG_CACHE_HOME:work+'/cache',XDG_DATA_HOME:work+'/data',XDG_CONFIG_HOME:work+'/config',npm_config_cache:work+'/npm-cache',COREPACK_HOME:work+'/corepack'},stdio:['ignore','pipe','pipe']});
 let output='';child.stdout.on('data',b=>{output+=b;process.stdout.write(b)});child.stderr.on('data',b=>{output+=b;process.stderr.write(b)});
 const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve)});
 records.push({args,exit_code:code});await fs.writeFile(out+'/install.json',JSON.stringify({node:process.version,scope:'synthetic account private installer, no live platform installation',work,records},null,2));
 assert.equal(code,0,output);return output;
}
await command(['list']);
for(const pkg of packages)await command(['install',pkg.path]);
const listed=JSON.parse(await command(['list']));assert.equal(Object.keys(listed.packages).length,2);
for(const pkg of packages)assert.equal(listed.packages[pkg.name].sha256,pkg.sha256);
await command(['remove',packages[1].name]);await command(['rollback']);
assert.equal(Object.keys(JSON.parse(await command(['list'])).packages).length,2);
console.log('PASS private digest admission, real Node22 DSH CLI install both bundles, list, remove, rollback');

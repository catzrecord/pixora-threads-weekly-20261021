const {test}=require('node:test'),assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const {run}=require('../lib/clock');
const due='2026-10-22T08:30:00+07:00',env={CRON_SECRET:'test-only',GITHUB_DISPATCH_TOKEN:'test-only'};
const base={env,authorization:'Bearer test-only',query:{slot:'0830'},at:new Date('2026-10-21T23:30:00Z')};
function fake({state='pending',badHash=false,runs=[],end='2027-04-20',count=546,slotDue=due,largeSchedule=false}={}){
 const posts=Array.from({length:count},(_,i)=>({id:'P'+i,due:i===0?slotDue:'other-'+i,media:[1,2,3]}));
 const raw=JSON.stringify(posts),calls=[];
 const files={'schedule.json':raw,'approval.json':JSON.stringify({account:'1fatherx',start:'2026-10-21',end,schedule_sha256:badHash?'bad':createHash('sha256').update(raw).digest('hex')}),'state.json':JSON.stringify({jobs:{P0:{state}}})};
 return {calls,fetcher:async(url,options)=>{
  const path=url.split('/pixora-threads-weekly-20261021/')[1];calls.push({path,...options});
  const name=path.startsWith('contents/')?path.slice(9).split('?')[0]:null;
  const data=largeSchedule&&name==='schedule.json'?{encoding:'none',content:'',sha:'large-schedule-blob'}:path==='git/blobs/large-schedule-blob'?{encoding:'base64',content:Buffer.from(raw).toString('base64')}:name?{content:Buffer.from(files[name]).toString('base64')}:path.includes('variables/')?{value:'true'}:path.includes('/runs?')?{workflow_runs:runs}:null;
  return {ok:true,status:options.method==='POST'?204:200,json:async()=>data};
 }};
}
test('unauthenticated requests cannot access GitHub',async()=>{const f=fake();assert.equal((await run({...base,authorization:'wrong',fetcher:f.fetcher})).status,401);assert.equal(f.calls.length,0)});
test('unsupported slots and completed campaign do not dispatch',async()=>{const f=fake();assert.equal((await run({...base,query:{slot:'0900'},fetcher:f.fetcher})).status,400);assert.equal((await run({...base,at:new Date('2027-10-21T00:00:00Z'),fetcher:f.fetcher})).body.state,'outside_approved_campaign');assert.equal(f.calls.length,0)});
test('dry run verifies approval without posting or dispatching',async()=>{const f=fake();const result=await run({...base,query:{slot:'0830',dry_run:'1'},fetcher:f.fetcher});assert.equal(result.body.state,'ready');assert.equal(result.body.due,due);assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});
test('published and ambiguous slots never dispatch',async()=>{for(const state of ['published','publishing','needs_reconciliation','missed']){const f=fake({state});assert.equal((await run({...base,fetcher:f.fetcher})).body.state,'already_recorded');assert.equal(f.calls.filter(x=>x.method==='POST').length,0)}});
test('approval hash change stops dispatch',async()=>{const f=fake({badHash:true});await assert.rejects(run({...base,fetcher:f.fetcher}),/verification failed/);assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});
test('an armed run is reused',async()=>{const f=fake({runs:[{display_title:`Threads wait-due ${due}`,status:'in_progress',html_url:'https://github.com/test'}]});assert.equal((await run({...base,fetcher:f.fetcher})).body.state,'already_armed');assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});
test('dispatch uses exact approved slot and wait mode',async()=>{const f=fake();const result=await run({...base,fetcher:f.fetcher});assert.equal(result.status,202);const requests=f.calls.filter(x=>x.method==='POST');assert.equal(requests.length,1);assert.deepEqual(JSON.parse(requests[0].body),{ref:'main',inputs:{mode:'wait-due',due}})});
test('late and overly early timers do not dispatch',async()=>{const f=fake();for(const at of [new Date('2026-10-21T21:00:00Z'),new Date('2026-10-22T02:01:00Z')]){await run({...base,at,fetcher:f.fetcher})}assert.equal(f.calls.length,0)});
test('annual approval arms the last evening on 20 October',async()=>{const target='2027-10-20T20:00:00+07:00',f=fake({end:'2027-10-20',count:1095,slotDue:target});const result=await run({...base,query:{slot:'2000'},at:new Date('2027-10-20T12:00:00Z'),fetcher:f.fetcher});assert.equal(result.body.state,'armed');assert.equal(result.body.due,target)});
test('legacy approval still stops after its approved April end',async()=>{const f=fake();const result=await run({...base,query:{slot:'2000'},at:new Date('2027-04-21T12:00:00Z'),fetcher:f.fetcher});assert.equal(result.body.state,'outside_approved_campaign');assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});
test('an annual end with only six months of rows cannot dispatch',async()=>{const f=fake({end:'2027-10-20',count:546});await assert.rejects(run({...base,fetcher:f.fetcher}),/verification failed/);assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});
test('large annual schedule loads through Git blob before verifying its hash',async()=>{const f=fake({end:'2027-10-20',count:1095,largeSchedule:true});const result=await run({...base,query:{slot:'0830',dry_run:'1'},fetcher:f.fetcher});assert.equal(result.body.state,'ready');assert.ok(f.calls.some(x=>x.path==='git/blobs/large-schedule-blob'));assert.equal(f.calls.filter(x=>x.method==='POST').length,0)});

const {createHash, timingSafeEqual}=require('node:crypto');
const REPO='catzrecord/pixora-threads-weekly-20261021';
const SLOTS={'0830':'08:30','1300':'13:00','2000':'20:00'};

function authorized(value, secret){
 if(!secret||typeof value!=='string')return false;
 const actual=Buffer.from(value),expected=Buffer.from('Bearer '+secret);
 return actual.length===expected.length&&timingSafeEqual(actual,expected);
}
function localDate(at){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Jakarta',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(at).map(p=>[p.type,p.value]));
 return `${parts.year}-${parts.month}-${parts.day}`;
}
async function run({authorization,query,env=process.env,at=new Date(),fetcher=fetch}){
 if(!authorized(authorization,env.CRON_SECRET))return {status:401,body:{state:'unauthorized'}};
 const slot=SLOTS[String(query.slot)];
 if(!slot)return {status:400,body:{state:'invalid_slot'}};
 const date=localDate(at),due=`${date}T${slot}:00+07:00`;
 if(date<'2026-10-21'||date>'2027-10-20')return {status:200,body:{state:'outside_approved_campaign'}};
 const remaining=(new Date(due)-at)/1000;
 if(remaining>10800)return {status:200,body:{state:'too_early',due}};
 if(remaining< -1800)return {status:200,body:{state:'too_late',due}};
 if(!env.GITHUB_DISPATCH_TOKEN)throw Error('Clock credential is not configured');
 async function github(path,method='GET',body){
  const response=await fetcher(`https://api.github.com/repos/${REPO}/${path}`,{method,
   headers:{Authorization:'Bearer '+env.GITHUB_DISPATCH_TOKEN,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
   ...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error(`GitHub clock request failed (${response.status})`);
  return response.status===204?null:response.json();
 }
 async function file(name){
  let d=await github(`contents/${name}?ref=main`);
  // The annual schedule is larger than the Contents API's 1 MB inline limit.
  if(d.encoding==='none'||(!d.content&&d.sha))d=await github(`git/blobs/${d.sha}`);
  if(typeof d.content!=='string'||!d.content)throw Error('Approved campaign file is unavailable');
  return Buffer.from(d.content,'base64');
 }
 const [rawSchedule,rawApproval,rawState,enabled]=await Promise.all([
  file('schedule.json'),file('approval.json'),file('state.json'),github('actions/variables/PUBLISH_ENABLED')]);
 const schedule=JSON.parse(rawSchedule),approval=JSON.parse(rawApproval),ledger=JSON.parse(rawState);
 const days={'2027-04-20':182,'2027-10-20':365}[approval.end];
 if(approval.account!=='1fatherx'||approval.start!=='2026-10-21'||!days||schedule.length!==days*3||
  createHash('sha256').update(rawSchedule).digest('hex')!==approval.schedule_sha256)throw Error('Approved campaign verification failed');
 if(date>approval.end)return {status:200,body:{state:'outside_approved_campaign'}};
 if(enabled.value!=='true')return {status:200,body:{state:'publisher_disabled',due}};
 const matching=schedule.filter(p=>p.due===due);
 if(matching.length!==1)throw Error('Approved slot is missing or duplicated');
 const post=matching[0],state=ledger.jobs[post.id]?.state;
 if(['published','publishing','needs_reconciliation','missed'].includes(state))return {status:200,body:{state:'already_recorded',post_id:post.id,due}};
 const result={due,post_id:post.id,media_items:post.media.length,mode:'wait-due',published_by_this_request:0};
 if(query.dry_run==='1')return {status:200,body:{state:'ready',...result}};
 const expectedTitle=`Threads wait-due ${due}`;
 const runs=await github('actions/workflows/publish.yml/runs?event=workflow_dispatch&per_page=30');
 const existing=runs.workflow_runs?.find(r=>r.display_title===expectedTitle&&['queued','in_progress','waiting','pending','requested'].includes(r.status));
 if(existing)return {status:200,body:{state:'already_armed',...result,run_url:existing.html_url}};
 await github('actions/workflows/publish.yml/dispatches','POST',{ref:'main',inputs:{mode:'wait-due',due}});
 return {status:202,body:{state:'armed',...result}};
}
module.exports={run,authorized,localDate};

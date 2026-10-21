const {run}=require('../lib/clock');
module.exports=async(req,res)=>{
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='GET')return res.status(405).json({state:'method_not_allowed'});
 try {const result=await run({authorization:req.headers.authorization,query:req.query});return res.status(result.status).json(result.body)}
 catch(error){console.error(JSON.stringify({state:'clock_error',message:error.message}));return res.status(503).json({state:'clock_error',message:error.message})}
};

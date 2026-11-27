// Fixture-backed failure, isolation and retry coverage. Live serving is tested separately.
const {test}=require('node:test');const assert=require('node:assert/strict');const {chromium}=require('playwright');const {expect}=require('playwright/test');
const base=process.env.PORTAL_TEST_URL||'http://localhost:3000';
const launch=process.env.PLAYWRIGHT_CHROME_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROME_EXECUTABLE}:{};
test('models: fixed lineage, lost registration retry, health failure, promotion, rollback and isolation',async()=>{
 const browser=await chromium.launch({headless:true,...launch});try{
  const p=await browser.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));let production=1,lose=true,failHealth=true,deny=false,posted=[],predictions=[],hold;
  const model=()=>({model_id:'model-1',project_id:'project-1',name:'Image classifier',latest_version:2,production_version:production});
  const job={job_id:'job-1',project_id:'project-1',status:'SUCCEEDED',spec:{model:'resnet18',dataset_id:'dataset-1',dataset_version:2}};
  const ver=n=>({model_id:'model-1',name:'Image classifier',version:n,job_id:'job-1',dataset_id:'dataset-1',dataset_version:2,mlflow_run_id:'run-1',metrics:{accuracy:.9},stage:production===n?'production':n===1?'archived':'none',artifact_uri:'s3://artifacts/model/model'});
  await p.route('**/api/v1/**',async route=>{
   const r=route.request(),u=new URL(r.url());let body;
   if(u.pathname.endsWith('/projects'))body={items:[{project_id:'project-1',name:'First'},{project_id:'project-2',name:'Second'}]};
   else if(u.pathname.endsWith('/models')&&r.method()==='GET')body={items:u.searchParams.get('project_id')==='project-1'?[model()]:[]};
   else if(u.pathname.endsWith('/jobs'))body={items:[job]};
   else if(u.pathname.endsWith('/experiments/get-by-name'))body={experiment:{experiment_id:'1'}};
   else if(u.pathname.endsWith('/runs/search'))body={runs:[{info:{run_id:'run-1',status:'FINISHED'},data:{tags:[{key:'project_id',value:'project-1'},{key:'job_id',value:'job-1'}],metrics:[]}}]};
   else if(u.pathname.endsWith('/models')&&r.method()==='POST'){
    posted.push({body:r.postDataJSON(),key:r.headers()['idempotency-key']});
    if(lose){lose=false;await new Promise(resolve=>{hold=resolve});return route.abort();}body=ver(2);
   }
   else if(u.pathname.endsWith('/versions')){if(deny)return route.fulfill({status:403,json:{error:{code:'FORBIDDEN',message:'Membership revoked'}}});body={items:[ver(1),ver(2)]};}
   else if(u.pathname.endsWith('/promote')){if(failHealth){failHealth=false;return route.fulfill({status:503,json:{error:{code:'DEPLOYMENT_FAILED',message:'Candidate health check failed',request_id:'fixture-health'}}});}production=2;body={...model(),version:production};}
   else if(u.pathname.endsWith('/rollback')){production=1;body={...model(),version:production};}
   else if(u.pathname.endsWith('/predict')){predictions.push({body:r.postDataBuffer().toString(),type:r.headers()['content-type']});body={model_id:'model-1',version:production,predictions:[{label:'cat',score:.91}]};}
   else throw Error('Unexpected gateway URL '+u.pathname);
   await route.fulfill({status:200,json:body});
  });
  await p.goto(base+'/models?project=project-1');await expect(p.getByLabel('Registered model',{exact:true})).toBeVisible();
  await p.getByLabel('Model name',{exact:true}).fill('Image classifier');await p.getByLabel('Successful training job').selectOption('job-1');await expect(p.getByLabel('Finished MLflow run')).toHaveValue('run-1');
  await p.getByRole('button',{name:'Register model version',exact:true}).click();await expect(p.getByLabel('Project',{exact:true})).toBeDisabled();assert.ok(hold);hold();await expect(p.locator('.notice.error[role=alert]')).toContainText('Cannot reach CloudTrain');
  await p.reload();await p.getByLabel('Model name',{exact:true}).fill('Image classifier');await p.getByLabel('Successful training job').selectOption('job-1');await expect(p.getByLabel('Finished MLflow run')).toHaveValue('run-1');await p.getByRole('button',{name:'Register model version',exact:true}).click();await expect(p.getByText('Registered Image classifier, version 2.',{exact:true})).toBeVisible();
  assert.equal(posted.length,2);assert.equal(posted[0].key,posted[1].key);assert.equal(posted[1].body.dataset_version,2);assert.equal(posted[1].body.job_id,'job-1');
  await p.getByRole('button',{name:'Promote version 2',exact:true}).click();await p.getByRole('button',{name:'Confirm deployment',exact:true}).click();await expect(p.locator('.notice.error[role=alert]')).toContainText('Candidate health check failed');await expect(p.getByText('Live version:',{exact:false}).first()).toContainText('Version 1');
  await p.getByRole('button',{name:'Promote version 2',exact:true}).click();await p.getByRole('button',{name:'Confirm deployment',exact:true}).click();await expect(p.getByText('Live version:',{exact:false}).first()).toContainText('Version 2');
  await p.getByRole('button',{name:'Roll back live version',exact:true}).click();await p.getByRole('button',{name:'Confirm deployment',exact:true}).click();await expect(p.getByText('Live version:',{exact:false}).first()).toContainText('Version 1');
  await p.getByLabel('Project',{exact:true}).selectOption('project-2');await expect(p.getByText('No registered models yet.',{exact:false})).toBeVisible();await expect(p.getByRole('button',{name:'Promote version 2'})).toHaveCount(0);
  deny=true;await p.getByLabel('Project',{exact:true}).selectOption('project-1');await expect(p.locator('.notice.error[role=alert]')).toContainText('Membership revoked');await expect(p.getByText('Version 2 · none',{exact:true})).toHaveCount(0);deny=false;
  await p.goto(base+'/predict?project=project-1');await p.getByLabel('Image',{exact:true}).setInputFiles({name:'cat.png',mimeType:'image/png',buffer:Buffer.from('fixture image')});await p.getByRole('button',{name:'Get prediction',exact:true}).click();await expect(p.getByTestId('prediction-result')).toContainText('cat');assert.match(predictions[0].type,/multipart\/form-data; boundary=/);assert.match(predictions[0].body,/name="model_id"\r\n\r\nmodel-1/);assert.match(predictions[0].body,/filename="cat.png"/);
  await p.getByLabel('Image',{exact:true}).setInputFiles({name:'bad.csv',mimeType:'text/csv',buffer:Buffer.from('no')});await expect(p.getByTestId('prediction-result')).toHaveCount(0);await p.getByRole('button',{name:'Get prediction',exact:true}).click();await expect(p.locator('.notice.error[role=alert]')).toContainText('PNG or JPEG');assert.equal(predictions.length,1);
  await p.getByLabel('Project',{exact:true}).selectOption('project-2');await expect(p.getByText('No live models in this project.',{exact:false})).toBeVisible();await expect(p.getByTestId('prediction-result')).toHaveCount(0);
  await p.setViewportSize({width:390,height:844});assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});

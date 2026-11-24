// Real CPU training through the gateway. Creates a small project/dataset in the local stack.
const {test}=require('node:test');const assert=require('node:assert/strict');const {readFileSync,mkdirSync}=require('node:fs');const path=require('node:path');const {randomUUID}=require('node:crypto');const {chromium}=require('playwright');const {expect}=require('playwright/test');
const baseURL=process.env.PORTAL_TEST_URL||'http://localhost:3000';
test('live CPU job: choose version, submit, history and MLflow results through the browser',async()=>{
 const env=readFileSync(path.resolve(__dirname,'../../..','.env'),'utf8');const token=process.env.DEV_AUTH_TOKEN||env.match(/^DEV_AUTH_TOKEN=(.*)$/m)?.[1]?.trim();assert.ok(token,'Local dev token required');
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROME_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROME_EXECUTABLE}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));const headers={Authorization:`Bearer ${token}`,'Idempotency-Key':randomUUID()};const url='http://localhost:5810/api/v1';
  const created=await page.request.post(url+'/projects',{headers,data:{name:'Portal jobs '+Date.now(),description:'Automated browser CPU training test'}});assert.equal(created.status(),201);const project=await created.json();
  const csv='radius,texture,perimeter,diagnosis\n1,1.1,1.2,B\n1.1,1.2,1.3,B\n0.9,1,1.1,B\n1.2,1.3,1.4,B\n8,8.1,8.2,M\n8.1,8.2,8.3,M\n7.9,8,8.1,M\n8.2,8.3,8.4,M\n';
  const upload=await page.request.post(url+'/datasets',{headers:{...headers,'Idempotency-Key':randomUUID()},multipart:{project_id:project.project_id,name:'CPU job training data',format:'csv',file:{name:'train.csv',mimeType:'text/csv',buffer:Buffer.from(csv)}}});assert.equal(upload.status(),201);const dataset=await upload.json();
  await page.goto(baseURL+'/jobs/new?project='+project.project_id);await page.getByLabel('Dataset',{exact:true}).selectOption(dataset.dataset_id);await expect(page.getByTestId('job-dataset-version')).toContainText('version 1');
  await page.getByRole('button',{name:'Submit training job'}).click();await expect(page).toHaveURL(/\/jobs\/job-\d+$/,{timeout:20000});
  await expect(page.getByTestId('live-job-status')).toHaveAttribute('data-status','SUCCEEDED',{timeout:180000});
  await expect(page.getByTestId('job-history')).toContainText('QUEUED');await expect(page.getByTestId('job-history')).toContainText('RUNNING');await expect(page.getByTestId('job-history')).toContainText('SUCCEEDED');
  await expect(page.getByRole('button',{name:'Cancel job',exact:true})).toHaveCount(0);
  await expect(page.locator('[data-testid="job-results"]')).toHaveAttribute('data-state','ready',{timeout:30000});
  await expect(page.locator('[data-testid="job-results"]')).not.toContainText('1 GPU');
  assert.deepEqual(errors,[]);mkdirSync(path.resolve(__dirname,'../../test-results'),{recursive:true});await page.screenshot({path:path.resolve(__dirname,'../../test-results/job-detail.png'),fullPage:true});console.log('Live browser job passed:',page.url());
 }finally{await browser.close();}
});

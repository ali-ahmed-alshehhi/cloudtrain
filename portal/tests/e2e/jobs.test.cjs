const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { expect } = require('playwright/test');
const baseURL = process.env.PORTAL_TEST_URL || 'http://localhost:3000';
const launch = process.env.PLAYWRIGHT_CHROME_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE } : {};
const waitReady = async page => { await expect(page.getByLabel('Project', { exact: true })).toHaveValue('project-01'); };

test('job form and detail: exact version, safe retry, live history, cancellation and project isolation', async () => {
  const browser = await chromium.launch({headless:true,...launch});
  try {
    const page = await browser.newPage(); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    let lost=true,requests=[],status='QUEUED',versionReads=[],unavailable=false, releaseSubmission;
    const at='2026-11-23T12:00:00Z';
    const job=()=>({job_id:'job-104',project_id:'project-01',status,spec:requests.at(-1)?.body||{},attempt:1,machine_type:'local-cpu',created_at:at,updated_at:at,started_at:null,finished_at:null,gpu_hours:0,estimated_cost_usd:0,history:[{status:'QUEUED',at,reason:null},...(status==='CANCELLED'?[{status,at,reason:'cancelled by user'}]:[])]});
    await page.route('**/api/v1/**', async route => {
      const req=route.request(),url=new URL(req.url()); let body;
      if(url.pathname.endsWith('/projects')) body={items:[{project_id:'project-01',name:'First'},{project_id:'project-02',name:'Second'}]};
      else if(url.pathname.endsWith('/datasets')) {const p=url.searchParams.get('project_id');body={items:[{dataset_id:p==='project-01'?'dataset-01':'dataset-02',project_id:p,name:p==='project-01'?'Versioned data':'Second data',format:'csv',latest_version:p==='project-01'?2:1}]};}
      else if(/\/datasets\/.+\/versions\/\d+$/.test(url.pathname)) {const v=Number(url.pathname.split('/').at(-1));versionReads.push(v);body={dataset_id:url.pathname.split("/")[4],version:v,size_bytes:22,checksum_sha256:String(v).repeat(64),created_at:at};}
      else if(url.pathname.endsWith('/jobs') && req.method()==='POST') {
        requests.push({body:req.postDataJSON(),key:req.headers()['idempotency-key']});
        if(lost){lost=false;await new Promise(resolve=>{releaseSubmission=resolve;});await route.abort();return;}body=job();
      }
      else if(url.pathname.endsWith('/cancel')){status='CANCELLED';body=job();}
      else if(url.pathname.endsWith('/jobs/events'))body={items:[]};
      else if(url.pathname.endsWith('/jobs/job-104')) {if(unavailable)return route.fulfill({status:403,json:{error:{code:'FORBIDDEN',message:'Not a project member'}}});body=job();}
      else if(url.pathname.endsWith('/jobs'))body={items:requests.length?[job()]:[]};
      else if(url.pathname.includes('/experiments/'))return route.fulfill({status:404,json:{error_code:'RESOURCE_DOES_NOT_EXIST',message:'No runs'}});
      else body={items:[]};
      await route.fulfill({status:req.method()==='POST'?url.pathname.endsWith('/cancel')?200:202:200,json:body});
    });
    await page.goto(baseURL+'/jobs/new?project=project-01');await waitReady(page);
    await expect(page).toHaveURL(/\/jobs\/new\?project=project-01$/);
    await page.reload();await waitReady(page);await expect(page.getByRole('heading',{level:1,name:'Submit a job'})).toBeVisible();
    await page.getByLabel('Dataset',{exact:true}).selectOption('dataset-01');
    await expect(page.getByTestId('job-dataset-version')).toContainText('version 2');
    await page.getByLabel('Dataset version',{exact:true}).selectOption('1');
    await expect(page.getByTestId('job-dataset-version')).toContainText('version 1');
    await page.getByLabel('Strategy',{exact:true}).selectOption('ddp');
    await page.getByRole('button',{name:'Submit training job'}).click();
    await expect(page.getByRole('alert').filter({hasText:'at least 2'})).toBeVisible();assert.equal(requests.length,0);
    await page.getByLabel('Strategy',{exact:true}).selectOption('single');
    await page.getByRole('button',{name:'Submit training job'}).click();
    await expect(page.getByLabel('Project',{exact:true})).toBeDisabled();
    assert.ok(releaseSubmission);releaseSubmission();
    await expect(page.getByRole('alert').filter({hasText:'Cannot reach CloudTrain'})).toBeVisible();
    // Reload and recreate the same form: sessionStorage must preserve the retry identity.
    await page.reload();await waitReady(page);await page.getByLabel('Dataset',{exact:true}).selectOption('dataset-01');await page.getByLabel('Dataset version',{exact:true}).selectOption('1');await expect(page.getByTestId('job-dataset-version')).toContainText('version 1');
    await page.getByRole('button',{name:'Submit training job'}).click();await expect(page).toHaveURL(/\/jobs\/job-104$/);
    await expect(page.getByTestId('live-job-status')).toHaveAttribute('data-status','QUEUED');
    assert.equal(requests.length,2);assert.equal(requests[0].key,requests[1].key);assert.equal(requests[1].body.dataset_version,1);assert.equal(requests[1].body.parallelism.world_size,1);assert.ok(versionReads.includes(1));
    await page.getByRole('button',{name:'Cancel job',exact:true}).click();await page.getByRole('button',{name:'Confirm cancellation'}).click();
    await expect(page.getByTestId('live-job-status')).toHaveAttribute('data-status','CANCELLED');await expect(page.getByTestId('job-history')).toContainText('cancelled by user');
    await expect(page.getByRole('button',{name:'Cancel job',exact:true})).toHaveCount(0);
    unavailable=true;await page.getByRole('button',{name:'Refresh job',exact:true}).click();await expect(page.getByRole('alert').filter({hasText:'Not a project member'})).toBeVisible();await expect(page.getByTestId('job-history')).toHaveCount(0);
    await page.goto(baseURL+'/jobs/new?project=project-01');await waitReady(page);await page.getByLabel('Project',{exact:true}).selectOption('project-02');
    await expect(page.getByLabel('Dataset',{exact:true}).getByRole('option',{name:'Second data (csv)'})).toHaveCount(1);await expect(page.getByLabel('Dataset',{exact:true})).toHaveValue('');await expect(page.getByTestId('job-dataset-version')).toHaveCount(0);
    await page.getByLabel('Dataset',{exact:true}).selectOption('dataset-02');await expect(page.getByTestId('job-dataset-version')).toContainText('dataset-02');
    await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
});

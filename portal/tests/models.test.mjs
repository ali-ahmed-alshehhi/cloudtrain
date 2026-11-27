import { test } from 'node:test';
import assert from 'node:assert/strict';
import { modelsOf, versionsOf, registration, productionOf, predictionOf, predictionForm, registrationKey, successfulJobsOf } from '../lib/models/records.mjs';
import { createGatewayClient } from '../app/lib/gateway.mjs';
const job={job_id:'job-1',project_id:'project-1',status:'SUCCEEDED',spec:{dataset_id:'dataset-1',dataset_version:2,model:'resnet18'}};
const run={runId:'run-1',status:'FINISHED',tags:{job_id:'job-1',project_id:'project-1'}};
const model={model_id:'model-1',name:'Image model',project_id:'project-1',latest_version:2,production_version:1};
const ver={...model,version:2,job_id:'job-1',dataset_id:'dataset-1',dataset_version:2,stage:'none',metrics:{accuracy:.8},mlflow_run_id:'run-1',artifact_uri:'s3://artifacts/model'};
test('model and version reads reject malformed identity and isolate projects',()=>{
 assert.deepEqual(modelsOf({items:[model,{...model,model_id:'model-2',project_id:'project-2'}]},'project-1'),[model]);
 assert.throws(()=>modelsOf({items:[{...model,production_version:'1'}]},'project-1'));
 assert.deepEqual(versionsOf({items:[ver]},'model-1'),[ver]);
 for(const change of [{model_id:'model-2'},{version:0},{metrics:{accuracy:NaN}},{stage:'unknown'},{mlflow_run_id:{}},{artifact_uri:{}}])assert.throws(()=>versionsOf({items:[{...ver,...change}]},'model-1'));
});
test('registration derives fixed lineage and rejects another project, job or unfinished run',()=>{
 const spec=registration('project-1','  Image model ',job,run);
 assert.deepEqual(spec,{project_id:'project-1',name:'Image model',mlflow_run_id:'run-1',job_id:'job-1',dataset_id:'dataset-1',dataset_version:2});
 assert.throws(()=>registration('project-2','Image model',job,run));
 assert.throws(()=>registration('project-1','',job,run));
 assert.throws(()=>registration('project-1','Image model',{...job,status:'RUNNING'},run));
 for(const change of [{status:'RUNNING'},{tags:{project_id:'project-2',job_id:'job-1'}},{tags:{project_id:'project-1',job_id:'job-2'}}])assert.throws(()=>registration('project-1','Image model',job,{...run,...change}));
});
test('registration retry identity survives navigation but changes for a new version request',()=>{
 const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 const spec=registration('project-1','Image model',job,run);
 const first=registrationKey(spec,storage,()=> 'first');
 assert.equal(registrationKey(spec,storage,()=> 'second').key,'first');
 assert.equal(registrationKey({...spec,dataset_version:3},storage,()=> 'third').key,'third');
 values.delete(first.slot);assert.equal(registrationKey(spec,storage,()=> 'new').key,'new');
});
test('prediction uses image multipart data, validates returned model and preserves actual serving version',()=>{
 const file=new File(['image'],'cat.png',{type:'image/png'});
 const form=predictionForm('model-1',file);assert.equal(form.get('model_id'),'model-1');assert.equal(form.get('file').name,'cat.png');
 assert.throws(()=>predictionForm('model-1',new File(['x'],'a.csv',{type:'text/csv'})));
 assert.throws(()=>predictionForm('model-1',new File([],'cat.png',{type:'image/png'})));
 const answer={model_id:'model-1',version:3,predictions:[{label:'cat',score:.9}]};
 assert.equal(predictionOf(answer,'model-1').version,3);
 assert.throws(()=>predictionOf(answer,'model-2'));
 for(const score of [-1,2,NaN,'0.9'])assert.throws(()=>predictionOf({...answer,predictions:[{label:'cat',score}]},'model-1'));
 assert.throws(()=>predictionOf({...answer,predictions:[]},'model-1'));
 assert.throws(()=>productionOf({model_id:'model-2',version:1},'model-1'));
});
test('registry writes and predictions stay on the gateway and preserve retry and multipart headers',async()=>{
 const calls=[];const api=createGatewayClient({gatewayUrl:'http://localhost:5810',getToken:()=> 'fixture-token',fetchImpl:async(url,options)=>{calls.push({url,options});return new Response('{}',{status:200});}});
 await api.listModels('project-1');await api.listModelVersions('model-1');await api.registerModel(registration('project-1','Name',job,run),'stable-key');await api.promoteModel('model-1',2);await api.rollbackModel('model-1');await api.predict(predictionForm('model-1',new File(['x'],'cat.png',{type:'image/png'})));
 assert.deepEqual(calls.map(c=>c.url),['http://localhost:5810/api/v1/models?project_id=project-1','http://localhost:5810/api/v1/models/model-1/versions','http://localhost:5810/api/v1/models','http://localhost:5810/api/v1/models/model-1/versions/2/promote','http://localhost:5810/api/v1/models/model-1/rollback','http://localhost:5810/api/v1/predict']);
 assert.equal(calls[2].options.headers.get('Idempotency-Key'),'stable-key');assert.equal(calls[5].options.headers.has('Content-Type'),false);assert.ok(calls[5].options.body instanceof FormData);assert.ok(calls.every(c=>c.options.headers.get('Authorization')==='Bearer fixture-token'));
});

test('successful-job selection rejects malformed lineage rather than crashing the registration form',()=>{
 assert.deepEqual(successfulJobsOf({items:[job,{...job,job_id:'job-2',project_id:'project-2'}]},'project-1'),[job]);
 for(const bad of [null,{...job,spec:null},{...job,spec:{...job.spec,dataset_version:0}}])assert.throws(()=>successfulJobsOf({items:[bad]},'project-1'));
});

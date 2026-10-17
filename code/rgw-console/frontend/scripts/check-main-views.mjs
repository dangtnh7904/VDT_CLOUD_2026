// Server-side component contract checks, not browser/visual acceptance. No
// web server is started, network requests or stored collections are touched.
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const server=await createServer({configFile:false,server:{middlewareMode:true},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
try {
  const {DaemonWorkbench,ObservationDetails}=await server.ssrLoadModule('/src/DaemonWorkbench.tsx');
  const {SourceWarning}=await server.ssrLoadModule('/src/SourceWarning.tsx');
  const daemon=(key,type)=>({key,type,id:key.split('.').slice(1).join('.'),quality:'PARTIAL',fields:{host:'fixture'},limitations:[],metrics:[{metric_id:'container.memory_usage',value:null,quality:'UNAVAILABLE'}]});
  const observation={id:'fixture',kind:'AS_IS_COLLECTION',cluster_id:'fixture',fsid:'fixture-fsid',quality:'PARTIAL',started_at:'2026-10-14T00:00:00Z',completed_at:'2026-10-14T00:00:01Z',daemons:[daemon('mon.fixture','mon'),daemon('osd.2','osd'),daemon('osd.5','osd')],system:{},sources:{},limitations:[],missing_daemon_keys:[],capabilities:{},phase:'BEFORE'};
  const scoped=renderToStaticMarkup(React.createElement(ObservationDetails,{observation,daemonType:'osd'}));
  assert.ok(scoped.includes('osd.2')&&scoped.includes('osd.5'));
  assert.ok(!scoped.includes('mon.fixture'));
  assert.ok(!scoped.includes('Thông tin hệ thống và nguồn thu'));
  const exact=renderToStaticMarkup(React.createElement(ObservationDetails,{observation,daemonType:'osd',daemonKey:'osd.2'}));
  assert.ok(exact.includes('osd.2')&&!exact.includes('osd.5')&&!exact.includes('mon.fixture'));
  const warning=renderToStaticMarkup(React.createElement(SourceWarning,{observation}));
  assert.ok(warning.includes('aria-label="Xem dữ liệu còn thiếu hoặc cũ"'));
  assert.ok(warning.includes('Chưa có chỉ số hợp lệ'));
  assert.ok(!warning.includes('<pre')&&!warning.includes('CPU/RAM/process/network cần nguồn'));
  const metricView=renderToStaticMarkup(React.createElement(DaemonWorkbench,{mode:'metrics'}));
  assert.ok(metricView.includes('Xem chỉ số mới (0 daemon)'));
  assert.ok(metricView.includes('Xuất 0 daemon (JSON)'));
  assert.ok(!metricView.includes('Nguồn dữ liệu, phạm vi và phần còn thiếu'));
  console.log(JSON.stringify({kind:'SSR_COMPONENT_CONTRACTS_NOT_BROWSER_ACCEPTANCE',assertions:10,status:'PASS'}));
} finally {await server.close();}

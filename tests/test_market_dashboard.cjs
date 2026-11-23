const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync('index.html', 'utf8');
const element = () => ({textContent:'', innerHTML:'', style:{}});
const originalCalendar = JSON.parse(fs.readFileSync('data/market_calendar.json', 'utf8'));

test('page startup loads a historical score, warns it is stale, and polls a newer session', async () => {
  let latest = '2026-11-20';
  let checked = '2026-11-23T08:11:00Z';
  const elements = new Map();
  const timers = [];
  const requests = [];
  const date = class extends Date {
    constructor(...args) { super(...(args.length ? args : ['2026-11-23T08:11:00Z'])); }
  };
  const document = {
    hidden: false,
    getElementById: id => {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
  };
  const fetch = async url => {
    requests.push(url);
    const file = url.split('/').at(-1).split('?')[0];
    let data;
    if (file === 'market_update_status.json') {
      data = {checked_at:checked, expected_session:'2026-11-23', last_valid_session:latest,
        status:latest === '2026-11-20' ? 'STALE' : 'PARTIAL', date_valid:latest === '2026-11-23'};
    } else if (file === 'market_calendar.json') {
      data = originalCalendar;
    } else if (file === 'manifest.json') {
      data = {sources:{index_history:{status:'ok',date:latest}}};
    } else if (file === 'index_history.json') {
      const last = new Date(latest).getTime();
      data = {date:latest, rows:Array.from({length:252}, (_,i)=>({
        date:new Date(last-(251-i)*86400000).toISOString().slice(0,10), close:40000-i*10,
      }))};
    } else {
      return {ok:false, status:404};
    }
    return {ok:true, json:async()=>data};
  };
  vm.runInNewContext(html.match(/<script>\n([\s\S]+?)<\/script>/)[1], {
    document, fetch, Date:date, Intl, location:{hostname:'shenghuang484.github.io'},
    setInterval: callback=>timers.push(callback),
  });
  await new Promise(resolve=>setImmediate(resolve));
  assert.match(elements.get('marketFreshness').textContent, /最後有效交易日 2026-11-20.*STALE/);
  assert.match(elements.get('refreshState').textContent, /已載入 2026-11-20 分數/);
  latest = '2026-11-23';
  checked = '2026-11-23T09:15:00Z';
  await timers[0]();
  assert.match(elements.get('marketFreshness').textContent, /2026-11-23.*部分來源/);
  assert.match(elements.get('refreshState').textContent, /2026-11-23.*研究驗證未完成/);
  assert.ok(requests.every(url=>url.startsWith('https://raw.githubusercontent.com/')));
});

test('same-date optional sources restore weights while stale and incomplete rows stay unscored',async()=>{
  const latest='2026-11-23';
  const elements=new Map();
  const timers=[];
  let ready=false;
  let check='2026-11-23T08:42:00Z';
  const days=Array.from({length:252},(_,i)=>new Date(
    Date.parse(latest)-(251-i)*86400000).toISOString().slice(0,10));
  const previous=days.at(-2);
  const document={hidden:false,getElementById:id=>{
    if(!elements.has(id))elements.set(id,element());
    return elements.get(id);
  }};
  const data={
    market_calendar:originalCalendar,
    index_history:{date:latest,rows:days.map((date,i)=>({date,close:40000-i*10}))},
    manifest:{sources:{index_history:{date:latest,status:'ok'}}},
    taifex_vix:{date:latest,close:55},
    twse_stocks:Array.from({length:501},(_,i)=>(
      {Code:String(1100+i),Date:'1151123',Change:i<100?'1':'-1',TradeVolume:'100'})),
    twse_dated_breadth:{date:latest,limit_down:9},
    breadth_history:[{date:previous,up:200,down:300},{date:latest,up:350,down:150}],
    futures_history:[{date:previous,net:-98000},{date:latest,net:-103432}],
    taifex_futures:[{Date:'20261120',ContractCode:'TX',Item:'外資','OpenInterest(Net)':999}],
    tpex_index:[{Date:'20261123',Close:100,Change:1}],
    twse_foreign:{date:'20261123',fields:['單位名稱','買賣差額'],data:[['外資及陸資(不含外資自營商)',-1000000000]]},
    new_low:{date:latest,status:'research_only',score_eligible:false},
  };
  const fetch=async url=>{
    const key=url.split('/').at(-1).split('?')[0].replace('.json','');
    const dynamic={
      market_update_status:{checked_at:check,expected_session:latest,last_valid_session:latest,
         status:ready?'VALID':'PARTIAL',date_valid:true},
      taifex_putcall:[{Date:ready?'20261123':'20261120','PutCallVolumeRatio%':54.21}],
      margin_maintenance:{date:ready?latest:previous,ratio:139.5},
      twse_dated_margin:days.slice(ready?-21:-20).map((date,i)=>({date,balance_1000_twd:1000-i}))
    };
    const payload=dynamic[key]??data[key];
    return payload===undefined?{ok:false,status:404}:{ok:true,json:async()=>payload};
  };
  const fixedDate=class extends Date{
    constructor(...args){super(...(args.length?args:['2026-11-23T09:00:00Z']));}
  };
  const context=vm.createContext({document,fetch,Date:fixedDate,Intl,
    location:{hostname:'shenghuang484.github.io'},setInterval:callback=>timers.push(callback)});
  vm.runInContext(html.match(/<script>\n([\s\S]+?)<\/script>/)[1], context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('foreignFutures').textContent,'-103,432');
  assert.equal(elements.get('warningCoverage').textContent,'已評分權重 35 / 50');
  assert.equal(elements.get('confirmCoverage').textContent,'已評分權重 40 / 50');

  ready=true;
  check='2026-11-23T12:43:00Z';
  await timers[0]();
  assert.equal(elements.get('warningCoverage').textContent,'已評分權重 50 / 50');
  assert.equal(elements.get('confirmCoverage').textContent,'已評分權重 45 / 50');
  const scored=vm.runInContext('JSON.stringify([score(warning),score(confirm)])',context);
  const [warningResult,confirmResult]=JSON.parse(scored);
  assert.equal(warningResult.value,warningResult.pts/50*100);
  assert.equal(confirmResult.value,confirmResult.pts/45*100);
  assert.match(elements.get('refreshState').textContent,/創新低家數減少（研究驗證未完成）/);
});

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

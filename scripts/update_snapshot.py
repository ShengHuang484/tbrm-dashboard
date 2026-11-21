"""Fetch latest official market snapshots. Never synthesize missing data."""
import json
import os
import urllib.request
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = {
    'twse_index': 'https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX',
    'twse_stocks': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    'twse_margin': 'https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN',
    'twse_breadth': 'https://openapi.twse.com.tw/v1/opendata/twtazu_od',
    'tpex_index': 'https://www.tpex.org.tw/openapi/v1/tpex_index',
    'taifex_putcall': 'https://openapi.taifex.com.tw/v1/PutCallRatio',
    'taifex_futures': 'https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate',
    'twse_foreign': 'https://www.twse.com.tw/fund/BFI82U?response=json',
}

def fetch(url):
    req=urllib.request.Request(url, headers={'User-Agent':'TBRM-research-dashboard/1.6','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:
        if r.status!=200: raise ValueError('HTTP '+str(r.status))
        payload=json.load(r)
    if not isinstance(payload,(list,dict)) or not payload:
        raise ValueError('empty or invalid JSON')
    return payload


def fetch_dated_limit_down(data_dir):
    """Use the TWSE dated close report, not the potentially stale OpenAPI breadth feed."""
    stocks=json.loads((data_dir/'twse_stocks.json').read_text(encoding='utf-8'))
    dates=sorted({str(x.get('Date','')) for x in stocks if isinstance(x,dict) and re.fullmatch(r'\d{7}',str(x.get('Date','')))})
    if not dates: raise ValueError('stock snapshot has no ROC trading date')
    roc=dates[-1]; greg=str(int(roc[:3])+1911)+roc[3:]
    url=f'https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={greg}&type=MS'
    raw=fetch(url)
    if raw.get('stat')!='OK': raise ValueError('TWSE report not OK: '+str(raw.get('stat')))
    # MI_INDEX MS table 8: rows [up/down/flat..., overall-market, stocks].
    tables=[]
    for k,v in raw.items():
        if re.fullmatch(r'data\d+',k) and isinstance(v,list) and v and isinstance(v[0],list):
            tables.append(v)
    def parse_count(cell):
        m=re.search(r'([\d,]+)\s*\(\s*([\d,]+)\s*\)',str(cell))
        return (int(m.group(1).replace(',','')),int(m.group(2).replace(',',''))) if m else None
    candidates=[]
    for table in tables:
        rows={}
        for row in table:
            if len(row)<3:continue
            label=re.sub(r'<[^>]+>','',str(row[0])).strip()
            if '上漲' in label and '漲停' in label:rows['up']=row
            if '下跌' in label and '跌停' in label:rows['down']=row
        if 'up' in rows and 'down' in rows:
            up=parse_count(rows['up'][2]);down=parse_count(rows['down'][2])
            if up and down:candidates.append((up,down))
    if len(candidates)!=1:raise ValueError(f'cannot uniquely identify stocks limit-down table: {len(candidates)}')
    (up,limit_up),(down,limit_down)=candidates[0]
    if not(0<=limit_down<=down and 0<=limit_up<=up and down+up>100):raise ValueError('implausible counts')
    return {'date':f'{greg[:4]}-{greg[4:6]}-{greg[6:]}','up':up,'limit_up':limit_up,'down':down,'limit_down':limit_down,'source_url':url}

def main():
    data_dir=ROOT/'data'; data_dir.mkdir(exist_ok=True)
    summary={'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'sources':{},'errors':{}}
    successful=0
    for key,url in ENDPOINTS.items():
        try:
            payload=fetch(url)
            dest=data_dir/(key+'.json')
            temp=dest.with_suffix('.json.tmp')
            temp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            temp.replace(dest)
            summary['sources'][key]={'status':'ok','records':len(payload) if isinstance(payload,list) else None,'url':url}
            if key == 'twse_breadth' and isinstance(payload,list):
                history_path=data_dir/'history'/'twse_breadth.json'
                history_path.parent.mkdir(exist_ok=True)
                try:
                    old=json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
                    if not isinstance(old,list): old=[]
                except (OSError,ValueError): old=[]
                for record in payload:
                    if isinstance(record,dict) and record.get('出表日期') and record.get('類型'):
                        old=[r for r in old if not (isinstance(r,dict) and r.get('出表日期')==record['出表日期'] and r.get('類型')==record['類型'])]
                        old.append(record)
                history_path.write_text(json.dumps(old[-240:],ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            if key == 'twse_margin':
                # Keep raw snapshots, but never label fetch dates as trading dates.
                archive = data_dir/'history'/'twse_margin.json'
                archive.parent.mkdir(exist_ok=True)
                try:
                    prior=json.loads(archive.read_text(encoding='utf-8')) if archive.exists() else []
                    if not isinstance(prior,list): prior=[]
                except (ValueError,OSError):
                    prior=[]
                today=summary['fetched_at_utc'][:10]
                prior=[r for r in prior if isinstance(r,dict) and str(r.get('fetched_at_utc',''))[:10]!=today]
                prior.append({'fetched_at_utc':summary['fetched_at_utc'],'payload':payload})
                archive.write_text(json.dumps(prior[-90:],ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            # Publish a small field inventory for schema troubleshooting; no credentials or private data.
            inventory=data_dir/'source_schema.json'
            try:
                schemas=json.loads(inventory.read_text(encoding='utf-8')) if inventory.exists() else {}
            except (ValueError,OSError): schemas={}
            if isinstance(payload,list):
                fields=list(payload[0].keys()) if payload and isinstance(payload[0],dict) else []
            else:
                fields=list(payload.get('fields',[])) if isinstance(payload.get('fields'),list) else list(payload.keys())
            schemas[key]={'fetched_at_utc':summary['fetched_at_utc'],'fields':fields,'records':len(payload) if isinstance(payload,list) else None}
            inventory.write_text(json.dumps(schemas,ensure_ascii=False,indent=2),encoding='utf-8')
            successful+=1
            print(key,'ok')
        except Exception as exc:
            summary['sources'][key]={'status':'failed','url':url}
            summary['errors'][key]=str(exc)[:240]
            print(key,'failed:',exc)
    try:
        counts=fetch_dated_limit_down(data_dir)
        (data_dir/'twse_dated_breadth.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
        summary['sources']['twse_dated_breadth']={'status':'ok','date':counts['date'],'url':counts['source_url']}
        print('twse_dated_breadth ok',counts['date'],counts['limit_down'])
    except Exception as exc:
        summary['sources']['twse_dated_breadth']={'status':'failed'}
        summary['errors']['twse_dated_breadth']=str(exc)[:240]
        print('twse_dated_breadth failed:',exc)
    (data_dir/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if successful==0: raise SystemExit('All official endpoints failed; keeping old source files')

if __name__=='__main__': main()

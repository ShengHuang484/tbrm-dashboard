"""Fetch latest official market snapshots. Never synthesize missing data."""
import json
import os
import urllib.request
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
    req=urllib.request.Request(url, headers={'User-Agent':'TBRM-research-dashboard/1.5','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:
        if r.status!=200: raise ValueError('HTTP '+str(r.status))
        payload=json.load(r)
    if not isinstance(payload,(list,dict)) or not payload:
        raise ValueError('empty or invalid JSON')
    return payload

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
    (data_dir/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if successful==0: raise SystemExit('All official endpoints failed; keeping old source files')

if __name__=='__main__': main()

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
    req=urllib.request.Request(url, headers={'User-Agent':'TBRM-research-dashboard/1.3','Accept':'application/json'})
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
            successful+=1
            print(key,'ok')
        except Exception as exc:
            summary['sources'][key]={'status':'failed','url':url}
            summary['errors'][key]=str(exc)[:240]
            print(key,'failed:',exc)
    (data_dir/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if successful==0: raise SystemExit('All official endpoints failed; keeping old source files')

if __name__=='__main__': main()

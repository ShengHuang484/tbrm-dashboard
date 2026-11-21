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
    # TWSE may change table order, row labels and stock-count column positions.
    # Inspect metadata, require explicit stock labeling, and fail closed if ambiguous.
    tables=[]
    for k,v in raw.items():
        if re.fullmatch(r'data\d+',k) and isinstance(v,list) and v and isinstance(v[0],list):
            suffix=k[4:]
            title=str(raw.get('title'+suffix,''))
            fields=raw.get('fields'+suffix,[])
            tables.append({'key':k,'title':title,'fields':fields,'rows':v})
    diagnostic={'report_date':greg,'stat':raw.get('stat'),'tables':[
        {'key':t['key'],'title':t['title'],'fields':t['fields'],
         'sample_rows':t['rows'][:5]} for t in tables]}
    (data_dir/'twse_dated_breadth_diagnostic.json').write_text(
        json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
    def plain(v):return re.sub(r'<[^>]*>','',str(v)).strip()
    def parse_count(v):
        text=plain(v).replace(',','')
        m=re.fullmatch(r'\s*(\d+)\s*\(\s*(\d+)\s*\)\s*',text)
        return (int(m.group(1)),int(m.group(2))) if m else None
    candidates=[]
    for t in tables:
        rows=t['rows']
        for up in rows:
            for down in rows:
                if up is down:continue
                up_label=' '.join(plain(c) for c in up[:2]);down_label=' '.join(plain(c) for c in down[:2])
                if not('上漲' in up_label and '漲停' in up_label and '下跌' in down_label and '跌停' in down_label):continue
                for i in range(1,min(len(up),len(down))):
                    u=parse_count(up[i]);d=parse_count(down[i])
                    if not(u and d):continue
                    if not(0<=u[1]<=u[0] and 0<=d[1]<=d[0] and u[0]+d[0]>100):continue
                    # Stock-only column must be explicitly identified in a header or table title.
                    fields=t['fields'] if isinstance(t['fields'],list) else []
                    column_label=plain(fields[i]) if i<len(fields) else ''
                    if not('股票' in column_label or ('股票' in t['title'] and len(fields)<=2)):
                        continue
                    candidates.append((t['key'],i,u,d))
    unique={(u,d) for _,_,u,d in candidates}
    if len(unique)!=1:
        raise ValueError('stocks limit-down table candidates '+str(len(unique))+
            '; inspect data/twse_dated_breadth_diagnostic.json')
    (up,limit_up),(down,limit_down)=next(iter(unique))

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

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
    req=urllib.request.Request(url, headers={'User-Agent':'TBRM-research-dashboard/1.9','Accept':'application/json'})
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
    # Record the actual response shape BEFORE filtering tables. A status of OK
    # does not imply that the requested statistics are present.
    def preview(value):
        if isinstance(value, dict):
            return {'type':'object','keys':list(value.keys())[:40],
                    'sample':{k:str(v)[:160] for k,v in list(value.items())[:3]}}
        if isinstance(value, list):
            return {'type':'array','length':len(value),
                    'first_item_type':type(value[0]).__name__ if value else None,
                    'sample':value[:2] if len(str(value[:2]))<3000 else [str(x)[:800] for x in value[:2]]}
        return {'type':type(value).__name__,'sample':str(value)[:250]}
    diagnostic={'report_date':greg,'source_url':url,'stat':raw.get('stat'),
                'top_level_keys':list(raw.keys()),
                'top_level_shapes':{k:preview(v) for k,v in raw.items()},
                'tables':[]}
    tables=[]
    # TWSE's modern response uses a top-level `tables` list of objects.
    modern=raw.get('tables')
    if isinstance(modern,list):
        for i,t in enumerate(modern):
            if not isinstance(t,dict):
                diagnostic['tables'].append({'key':f'tables[{i}]','shape':preview(t)})
                continue
            fields=t.get('fields',[])
            rows=t.get('data',[])
            title=str(t.get('title',''))
            diagnostic['tables'].append({'key':f'tables[{i}]','title':title,
                'keys':list(t.keys()),'fields':fields,
                'row_count':len(rows) if isinstance(rows,list) else None,
                'sample_rows':rows[:3] if isinstance(rows,list) else str(rows)[:500]})
            if isinstance(rows,list) and rows and all(isinstance(r,list) for r in rows):
                tables.append({'key':f'tables[{i}]','title':title,'fields':fields,'rows':rows})
    # Backward compatibility for older TWSE data1 / fields1 / title1 format.
    for k,v in raw.items():
        if re.fullmatch(r'data\d+',k) and isinstance(v,list) and v and isinstance(v[0],list):
            suffix=k[4:]
            title=str(raw.get('title'+suffix,''))
            fields=raw.get('fields'+suffix,[])
            tables.append({'key':k,'title':title,'fields':fields,'rows':v})
            diagnostic['tables'].append({'key':k,'title':title,'fields':fields,
                'row_count':len(v),'sample_rows':v[:3]})
    (data_dir/'twse_dated_breadth_diagnostic.json').write_text(
        json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
    if not tables:
        raise ValueError('official report contains no nonempty tabular data; see diagnostic tables')
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



def fetch_dated_margin(data_dir):
    """Fetch official daily aggregate margin balance; never treat a fetch as a trading day."""
    from datetime import date, timedelta
    import time
    stocks=json.loads((data_dir/'twse_stocks.json').read_text(encoding='utf-8'))
    dates=sorted({str(x.get('Date','')) for x in stocks if isinstance(x,dict) and re.fullmatch(r'\d{7}',str(x.get('Date','')))})
    if not dates:raise ValueError('cannot establish TWSE trading date')
    roc=dates[-1]; latest=date(int(roc[:3])+1911,int(roc[3:5]),int(roc[5:]))
    path=data_dir/'twse_dated_margin.json'
    try:
        old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        if not isinstance(old,list):old=[]
    except (ValueError,OSError):old=[]
    by_date={r['date']:r for r in old if isinstance(r,dict) and isinstance(r.get('date'),str) and isinstance(r.get('balance_1000_twd'),(int,float))}
    diagnostics=[]
    # Collect up to 45 calendar days, enough for 20 trading-day intervals.
    # Reuse validated history and limit requests to 30 per execution.
    for i in range(45):
        day=latest-timedelta(days=i)
        if day.weekday()>=5:continue
        iso=day.isoformat()
        if iso in by_date:continue
        if len(diagnostics)>=30:break
        url='https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date='+day.strftime('%Y%m%d')
        try:
            raw=fetch(url)
            if raw.get('stat')!='OK':
                diagnostics.append({'date':iso,'status':'not_available','stat':str(raw.get('stat'))[:90]});continue
            tables=[]
            if isinstance(raw.get('tables'),list):
                for t in raw['tables']:
                    if isinstance(t,dict):tables.append((t.get('fields',[]),t.get('data',[])))
            for key,val in raw.items():
                if re.fullmatch(r'data\d*',key) and isinstance(val,list):
                    suffix=key[4:];tables.append((raw.get('fields'+suffix,[]),val))
            if isinstance(raw.get('data'),list):tables.append((raw.get('fields',[]),raw['data']))
            values=[]
            for fields,rows in tables:
                if not isinstance(rows,list):continue
                for row in rows:
                    if isinstance(row,dict):
                        name=str(next((v for k,v in row.items() if '項目' in k),'')).strip()
                        val=next((v for k,v in row.items() if '今日餘額' in k),None)
                    elif isinstance(row,list):
                        name=str(row[0]) if row else ''
                        j=next((j for j,f in enumerate(fields) if '今日餘額' in str(f)),4 if len(row)>=5 else -1)
                        val=row[j] if j>=0 and j<len(row) else None
                    else:continue
                    name=re.sub(r'<[^>]+>','',name).replace(' ','')
                    if '融資金額' not in name:continue
                    try:amount=float(str(val).replace(',','').strip())
                    except (TypeError,ValueError):continue
                    if amount>0:values.append(amount)
            if len(values)!=1:
                diagnostics.append({'date':iso,'status':'unrecognized','tables':len(tables),'matching_values':len(values),'keys':list(raw)[:20]});continue
            by_date[iso]={'date':iso,'balance_1000_twd':values[0],'source_url':url}
            diagnostics.append({'date':iso,'status':'ok'})
        except Exception as exc:
            diagnostics.append({'date':iso,'status':'error','message':str(exc)[:120]})
        time.sleep(.12)
    entries=sorted(by_date.values(),key=lambda x:x['date'])[-100:]
    path.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    (data_dir/'twse_dated_margin_diagnostic.json').write_text(json.dumps({'latest_index_date':latest.isoformat(),'attempts':diagnostics,'valid_days':len(entries)},ensure_ascii=False,indent=2),encoding='utf-8')
    if not entries or entries[-1]['date']!=latest.isoformat():
        raise ValueError('dated margin balance missing for index trading date; inspect diagnostic')
    return {'date':latest.isoformat(),'valid_days':len(entries)}

def archive_daily(data_dir, name, rows):
    path=data_dir/(name+'.json')
    old=json.loads(path.read_text()) if path.exists() else []
    by_date={r['date']:r for r in old}
    by_date.update({r['date']:r for r in rows})
    path.write_text(json.dumps(sorted(by_date.values(),key=lambda r:r['date'])[-120:],ensure_ascii=False,indent=2),encoding='utf-8')

def archive_futures(data_dir):
    rows=json.loads((data_dir/'taifex_futures.json').read_text())
    grouped={}
    for r in rows:
        if str(r.get('ContractCode','')).strip() not in ('TX','臺股期貨','台股期貨') or '外資' not in str(r.get('Item','')):continue
        d=str(r.get('Date','')).replace('/','-')
        if re.fullmatch(r'[0-9]{8}',d):d=d[:4]+'-'+d[4:6]+'-'+d[6:]
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',d):continue
        try:v=int(str(r['OpenInterest(Net)']).replace(',',''))
        except (ValueError,KeyError):continue
        grouped.setdefault(d,[]).append(v)
    archive_daily(data_dir,'futures_history',[{'date':d,'net':v[0]} for d,v in grouped.items() if len(v)==1])

def parse_vix(raw, month):
    import math
    try: text=raw.decode('utf-8-sig')
    except UnicodeDecodeError: text=raw.decode('cp950')
    lines=text.splitlines()
    if not lines or not (('Daily Index' in lines[0] and 'Last 1 min AVG' in lines[0]) or ('臺指選擇權波動率指數' in lines[0] and '收盤前1分鐘平均指數' in lines[0])):
        raise ValueError('unrecognized VIX header')
    rows={}
    for line in lines[2:]:
        if not line.strip():continue
        parts=line.split()
        if len(parts)!=4 or not re.fullmatch(r'\d{8}',parts[0]) or not parts[0].startswith(month):raise ValueError('invalid VIX row')
        day=datetime.strptime(parts[0],'%Y%m%d').date().isoformat()
        if parts[1]!='13450000':raise ValueError('unexpected VIX closing time')
        v,avg=map(float,parts[2:])
        if not all(math.isfinite(x) and x>0 for x in (v,avg)) or day in rows:raise ValueError('invalid or duplicate VIX value')
        rows[day]={'date':day,'close':v,'last_minute_avg':avg}
    if not rows:raise ValueError('empty VIX data')
    return rows

def fetch_vix(data_dir):
    stocks=json.loads((data_dir/'twse_stocks.json').read_text(encoding='utf-8'))
    dates=sorted({str(x.get('Date','')) for x in stocks if isinstance(x,dict) and re.fullmatch(r'\d{7}',str(x.get('Date','')))})
    if not dates:raise ValueError('no TWSE trading date')
    roc=dates[-1]; day=datetime.strptime(str(int(roc[:3])+1911)+roc[3:],'%Y%m%d').date()
    month=day.strftime('%Y%m'); errors=[]
    for folder in ('log2data','log2data_eng'):
        url=f'https://www.taifex.com.tw/file/taifex/Dailydownload/vix/{folder}/{month}new.txt'
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'TBRM-research-dashboard/2.3'})
            with urllib.request.urlopen(req,timeout=30) as r:
                if r.status!=200:raise ValueError('HTTP '+str(r.status))
                rows=parse_vix(r.read(),month)
            record=rows.get(day.isoformat())
            if record is None:raise ValueError('missing trading date '+day.isoformat())
            return {**record,'source_url':url}
        except Exception as exc:errors.append(str(exc))
    raise ValueError('; '.join(errors))

def dated_maintenance_prices(day):
    date=day.replace('-', '')
    url=f'https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date}&type=ALLBUT0999'
    raw=fetch(url)
    if raw.get('stat')!='OK' or str(raw.get('date',''))!=date:
        raise ValueError('maintenance quote date not verified')
    tables=list(raw.get('tables',[]))
    for k,v in raw.items():
        if re.fullmatch(r'data\d*',k):
            tables.append({'fields':raw.get('fields'+k[4:],[]),'data':v})
    prices={}
    roc=str(int(day[:4])-1911)+day[5:7]+day[8:]
    for t in tables:
        f=[re.sub(r'<[^>]*>|\s','',str(x)) for x in t.get('fields',[])]
        if '證券代號' not in f or '收盤價' not in f:continue
        i,j=f.index('證券代號'),f.index('收盤價')
        for r in t.get('data',[]):
            code=str(r[i]).strip(); price=str(r[j]).strip()
            if code in prices and prices[code]['ClosingPrice']!=price:
                raise ValueError('conflicting same-day close '+code)
            prices[code]={'Code':code,'ClosingPrice':price,'Date':roc}
    if not prices:raise ValueError('dated quote table not found')
    print('maintenance dated quotes',day,len(prices))
    return list(prices.values())

def maintenance(raw, stocks, day, stocks_backup=None):
    from decimal import Decimal
    def n(v):return Decimal(str(v).replace(',','').strip())
    def clean(v):return re.sub(r'<[^>]*>|\s','',str(v))
    if raw.get('stat')!='OK' or str(raw.get('date',''))!=day.replace('-',''):raise ValueError('margin date not verified')
    tables=list(raw.get('tables',[]))
    for k,v in raw.items():
        if re.fullmatch(r'data\d*',k):tables.append({'fields':raw.get('fields'+k[4:],[]),'data':v})
    amounts=[]; totals=[]; balances={}
    seen=set(); schema=[]; labels=[]
    for t in tables:
        signature=json.dumps([t.get('fields',[]),t.get('data',[])],ensure_ascii=False)
        if signature in seen:continue
        seen.add(signature)
        schema.append({'fields':t.get('fields',[]),'rows':len(t.get('data',[]))})
        f=[clean(x) for x in t.get('fields',[])]; rows=t.get('data',[])
        if '項目' in f and '今日餘額' in f:
            j=f.index('今日餘額')
            for r in rows:
                label=clean(r[0]).replace('（','(').replace('）',')')
                if '股票代號' not in f:labels.append([label,str(r[j])])
                if label=='融資金額(仟元)':amounts.append(n(r[j]))
                if label=='融資(交易單位)':totals.append(n(r[j]))
        if ('股票代號' in f or '代號' in f) and '今日餘額' in f:
            j=f.index('今日餘額'); k=f.index('股票代號' if '股票代號' in f else '代號')
            for r in rows:
                code=clean(r[k]); val=n(r[j])
                if code in balances or val<0:raise ValueError('invalid margin balance')
                balances[code]=val
    print('maintenance diagnostics',json.dumps({'schema':schema,'summary_rows':labels[:10],'amounts':[str(x) for x in amounts],'totals':[str(x) for x in totals],'security_count':len(balances),'sum_lots':str(sum(balances.values()))},ensure_ascii=False))
    if len(amounts)!=1 or len(totals)!=1 or amounts[0]<=0 or totals[0]<=0 or sum(balances.values())!=totals[0]:raise ValueError(f'margin totals do not reconcile: amounts={amounts}, totals={totals}, securities={len(balances)}, sum_lots={sum(balances.values())}')
    roc=str(int(day[:4])-1911)+day[5:7]+day[8:]
    prices={str(r['Code']):r['ClosingPrice'] for r in stocks if str(r.get('Date'))==roc and 'Code' in r and 'ClosingPrice' in r}
    def valid(v):
        try:
            x=n(v)
            return x if x.is_finite() and x>0 else None
        except Exception:return None
    selected={code:valid(prices.get(code)) for code,lots in balances.items() if lots>0}
    missing={code for code,p in selected.items() if p is None}
    fallback={}
    print('maintenance missing same-day',sorted(missing))
    # Prefer another verified same-day source, then recent official closes.
    if missing:
        for r in stocks_backup or []:
            code=str(r.get('Code',''))
            if code in missing and str(r.get('Date'))==roc and valid(r.get('ClosingPrice')) is not None:
                selected[code]=valid(r['ClosingPrice']); missing.remove(code)
    if missing:
        from datetime import timedelta
        import time
        anchor=datetime.fromisoformat(day).date()
        for offset in range(1,31):
            prior=(anchor-timedelta(days=offset)).isoformat()
            if datetime.fromisoformat(prior).weekday()>=5:continue
            try: older=dated_maintenance_prices(prior)
            except Exception as exc:
                print('maintenance history unavailable',prior,str(exc)); continue
            for r in older:
                code=r['Code']; price=valid(r['ClosingPrice'])
                if code in missing and price is not None:
                    selected[code]=price; missing.remove(code)
                    fallback[code]={'date':prior,'price':str(price),'lots':str(balances[code]),'age_days':offset,'source':'TWSE MI_INDEX','basis_verified':False,'reason':'extended quote gap; corporate action basis unverified' if offset>7 else 'missing same-day close'}
            if not missing:break
            time.sleep(0.5)
    if missing:raise ValueError('missing reliable closes: '+','.join(sorted(missing)))
    value=sum((balances[c]*p for c,p in selected.items()),Decimal(0))
    fallback_value=sum((balances[c]*selected[c] for c in fallback),Decimal(0))
    # Historical prices are approximate, not same-day marks. Cap their estimated value contribution.
    share=fallback_value/value
    if share>Decimal('0.001'):raise ValueError('historical price share exceeds 0.1%: '+str(share))
    print('maintenance fallback',json.dumps(fallback,ensure_ascii=False),'value share',str(share))
    return {'date':day,'ratio':float(value/amounts[0]*100),'matched_securities':len(selected),'provisional':True,'fallback_prices':fallback,'fallback_value_pct':float(share*100),'extended_gap_codes':sorted(c for c,r in fallback.items() if r['age_days']>7),'price_basis_verified':not bool(fallback)}

def new_low_history(data_dir, day):
    """Raw-close proxy; no corporate-action adjustment claimed."""
    from datetime import date, timedelta
    import time
    from decimal import Decimal, InvalidOperation
    end=date.fromisoformat(day)
    path=data_dir/'history'/'new_low_closes.json'
    path.parent.mkdir(exist_ok=True)
    history=json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(history,dict): raise ValueError('invalid close history')
    dates=[]
    for offset in range(15):
        month=date(end.year+(end.month-1-offset)//12,(end.month-1-offset)%12+1,1)
        raw=fetch('https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date='+month.strftime('%Y%m%d'))
        if raw.get('stat')!='OK' or not isinstance(raw.get('data'),list):raise ValueError('calendar unavailable '+str(month))
        for row in raw['data']:
            m=re.fullmatch(r'(\d{2,3})/(\d{1,2})/(\d{1,2})',str(row[0]))
            if not m:raise ValueError('calendar schema changed')
            d=date(int(m[1])+1911,int(m[2]),int(m[3]))
            if d.year!=month.year or d.month!=month.month:raise ValueError('calendar month mismatch')
            if d<=end:dates.append(d.isoformat())
        time.sleep(.4)
        if len(set(dates))>=262:break
    dates=sorted(set(dates))[-262:]
    if len(dates)!=262 or dates[-1]!=day:raise ValueError('calendar incomplete')
    history={d:v for d,v in history.items() if d in dates}
    errors=[]
    for d in [d for d in reversed(dates) if d not in history][:20]:
        try:
            rows=dated_maintenance_prices(d)
            prices={}
            for r in rows:
                code=r['Code']
                if not re.fullmatch(r'[1-9]\d{3}',code):continue
                try:p=Decimal(r['ClosingPrice'].replace(',',''))
                except InvalidOperation:continue
                if p.is_finite() and p>0:prices[code]=float(p)
            if len(prices)<500:raise ValueError('too few four-digit securities')
            history[d]=prices
        except Exception as exc:
            errors.append(d+': '+str(exc)[:100]);break
        finally:time.sleep(2)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(history,separators=(',',':')));tmp.replace(path)
    result={'date':day,'method':'raw_close_proxy','valid_days':len(history),'required_days':262,'errors':errors,'status':'collecting'}
    if len(history)==262:
        result.update(new_low_counts(history,dates))
    return result


def new_low_counts(history,dates):
    # Fixed cohort with valid closes throughout; strict new low versus prior 252 sessions.
    universe=set.intersection(*(set(history[d]) for d in dates))
    coverage=len(universe)/max(1,len(history[dates[-1]]))
    if len(universe)<500 or coverage<.85:
        return {'status':'insufficient_coverage','eligible':len(universe),'coverage':coverage}
    counts=[0]*10
    for code in universe:
        p=[history[d][code] for d in dates]
        for i in range(252,262):
            counts[i-252]+=p[i]<min(p[i-252:i])
    old=sum(counts[:5])/5; recent=sum(counts[5:])/5
    decline=(old-recent)/old*100 if old else 0
    return {'status':'ok','eligible':len(universe),'coverage':coverage,'counts':counts,'previous_avg':old,'recent_avg':recent,'decline_pct':decline,'points':5 if decline>=50 else 3 if decline>=30 else 1 if decline>=15 else 0}

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
        archive_daily(data_dir,'breadth_history',[counts])
        print('twse_dated_breadth ok',counts['date'],counts['limit_down'])
    except Exception as exc:
        (data_dir/'twse_dated_breadth.json').unlink(missing_ok=True)
        summary['sources']['twse_dated_breadth']={'status':'failed'}
        summary['errors']['twse_dated_breadth']=str(exc)[:240]
        print('twse_dated_breadth failed:',exc)
    try:
        margin=fetch_dated_margin(data_dir)
        summary['sources']['twse_dated_margin']={'status':'ok',**margin}
        print('twse_dated_margin ok',margin)
    except Exception as exc:
        summary['sources']['twse_dated_margin']={'status':'failed'}
        summary['errors']['twse_dated_margin']=str(exc)[:240]
        print('twse_dated_margin failed:',exc)
    try:
        if summary['sources'].get('taifex_futures',{}).get('status')=='ok':archive_futures(data_dir)
    except Exception as exc:summary['errors']['futures_history']=str(exc)[:240]
    try:
        if summary['sources'].get('twse_stocks',{}).get('status')!='ok':raise ValueError('TWSE stock download failed')
        vix=fetch_vix(data_dir)
        (data_dir/'taifex_vix.json').write_text(json.dumps(vix,ensure_ascii=False,indent=2),encoding='utf-8')
        summary['sources']['taifex_vix']={'status':'ok','date':vix['date'],'url':vix['source_url']}
        print('taifex_vix ok',vix['date'],vix['close'])
    except Exception as exc:
        (data_dir/'taifex_vix.json').unlink(missing_ok=True)
        summary['sources']['taifex_vix']={'status':'failed'}
        summary['errors']['taifex_vix']=str(exc)[:240]
        print('taifex_vix failed:',exc)
    try:
        if summary['sources'].get('twse_stocks',{}).get('status')!='ok':raise ValueError('stock download failed')
        stocks=json.loads((data_dir/'twse_stocks.json').read_text())
        dates={str(r.get('Date','')) for r in stocks}
        if len(dates)!=1:raise ValueError('mixed stock dates')
        roc=dates.pop(); day=datetime.strptime(str(int(roc[:3])+1911)+roc[3:],'%Y%m%d').date().isoformat()
        url='https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&selectType=ALL&date='+day.replace('-','')
        raw=fetch(url)
        print('maintenance schema',str([(t.get('fields'),t.get('title')) for t in raw.get('tables',[])])[:3000],list(raw))
        print('maintenance parser v2.4.5')
        report=maintenance(raw,dated_maintenance_prices(day),day,stocks)
        (data_dir/'margin_maintenance.json').write_text(json.dumps(report),encoding='utf-8')
        summary['sources']['margin_maintenance']={'status':'ok',**report,'url':url}
    except Exception as exc:
        (data_dir/'margin_maintenance.json').unlink(missing_ok=True)
        summary['sources']['margin_maintenance']={'status':'failed'}
        summary['errors']['margin_maintenance']=str(exc)[:240]
        print('margin_maintenance failed:',exc)
    try:
        if summary['sources'].get('twse_stocks',{}).get('status')!='ok':raise ValueError('stock download failed')
        stocks=json.loads((data_dir/'twse_stocks.json').read_text())
        dates={str(r.get('Date','')) for r in stocks}
        if len(dates)!=1:raise ValueError('mixed stock dates')
        roc=dates.pop(); day=datetime.strptime(str(int(roc[:3])+1911)+roc[3:],'%Y%m%d').date().isoformat()
        report=new_low_history(data_dir,day)
        (data_dir/'new_low.json').write_text(json.dumps(report,ensure_ascii=False))
        summary['sources']['new_low']=report
        print('new_low',report)
    except Exception as exc:
        (data_dir/'new_low.json').unlink(missing_ok=True)
        summary['sources']['new_low']={'status':'failed'}
        summary['errors']['new_low']=str(exc)[:240]
    (data_dir/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    if successful==0: raise SystemExit('All official endpoints failed; keeping old source files')

if __name__=='__main__': main()

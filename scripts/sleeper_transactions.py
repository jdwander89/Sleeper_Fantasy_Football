#!/usr/bin/env python3
"""Phase 4 transaction extension for the current Sleeper snapshot."""
import json,time,urllib.request,urllib.error,argparse,sys
from datetime import datetime,timezone
from pathlib import Path
BASE='https://api.sleeper.app/v1'; CFG=Path('config/league_config.json')
def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def rj(p):
    with open(p,encoding='utf-8') as f: return json.load(f)
def wj(p,x):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'w',encoding='utf-8') as f: json.dump(x,f,ensure_ascii=False,indent=2); f.write('\n')
def g(x,path,d=None):
    for k in path:
        if not isinstance(x,dict) or k not in x: return d
        x=x[k]
    return x
def get(path,retries=3):
    url=BASE+path; err=None
    for i in range(retries):
        try:
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'Sleeper-Transactions/1.0'})
            with urllib.request.urlopen(req,timeout=45) as r: return json.loads(r.read().decode())
        except Exception as e:
            err=e; time.sleep(1.25*(i+1))
    raise RuntimeError(f'GET failed {url}: {err}')
def cache_players(cache_dir,max_age,force,warn):
    cache_dir.mkdir(parents=True,exist_ok=True); p=cache_dir/'players_nfl_full.json'; meta=cache_dir/'players_nfl_cache_meta.json'
    age=(time.time()-p.stat().st_mtime)/3600 if p.exists() else None
    if p.exists() and not force and age is not None and age<=max_age: return rj(p)
    try:
        players=get('/players/nfl'); assert isinstance(players,dict)
        wj(p,players); wj(meta,{'source':'fresh_fetch','fetched_at':now(),'cache_path':str(p),'player_count':len(players),'full_cache_committed':False}); return players
    except Exception as e:
        if p.exists(): warn.append(f'Using stale player cache: {e}'); return rj(p)
        raise
def compact(pid,players):
    p=players.get(pid)
    if not isinstance(p,dict):
        if pid.isalpha() and 2<=len(pid)<=4: return {'player_id':pid,'name':f'{pid} Defense','team':pid,'position':'DEF','fantasy_positions':['DEF'],'missing_from_full_cache':True}
        return {'player_id':pid,'name':f'Unknown Player {pid}','team':None,'position':None,'fantasy_positions':[],'missing_from_full_cache':True}
    name=p.get('full_name') or ' '.join(str(v).strip() for v in (p.get('first_name'),p.get('last_name')) if v) or str(p.get('search_full_name') or pid)
    return {'player_id':str(p.get('player_id') or pid),'name':name,'first_name':p.get('first_name'),'last_name':p.get('last_name'),'team':p.get('team'),'position':p.get('position'),'fantasy_positions':p.get('fantasy_positions') or [],'status':p.get('status'),'injury_status':p.get('injury_status'),'years_exp':p.get('years_exp'),'age':p.get('age'),'depth_chart_position':p.get('depth_chart_position'),'search_rank':p.get('search_rank')}
def pname(pid,lookup): return str(lookup.get(str(pid),{}).get('name') or pid)
def ts(v):
    try: n=int(v)
    except Exception: return None
    if n>10_000_000_000: n/=1000
    return datetime.fromtimestamp(n,timezone.utc).isoformat().replace('+00:00','Z')
def move_map(m,labels,lookup):
    if not isinstance(m,dict): return []
    return [{'player_id':str(p),'player_name':pname(str(p),lookup),'roster_id':r,'team_label':labels.get(str(r),f'Roster {r}')} for p,r in sorted(m.items(),key=lambda x:str(x[0]))]
def budgets(b,labels):
    out=[]
    for x in b if isinstance(b,list) else []:
        if isinstance(x,dict):
            s,r=x.get('sender'),x.get('receiver')
            out.append({'sender_roster_id':s,'sender_team_label':labels.get(str(s),f'Roster {s}') if s is not None else None,'receiver_roster_id':r,'receiver_team_label':labels.get(str(r),f'Roster {r}') if r is not None else None,'amount':x.get('amount')})
    return out
def pick_list(ps,labels):
    out=[]
    for p in ps if isinstance(ps,list) else []:
        if isinstance(p,dict):
            own,prev,orig=p.get('owner_id'),p.get('previous_owner_id'),p.get('roster_id')
            out.append({'season':p.get('season'),'round':p.get('round'),'original_roster_id':orig,'original_team_label':labels.get(str(orig),f'Roster {orig}') if orig is not None else None,'previous_owner_id':prev,'previous_owner_team_label':labels.get(str(prev),f'Roster {prev}') if prev is not None else None,'owner_id':own,'owner_team_label':labels.get(str(own),f'Roster {own}') if own is not None else None})
    return out
def add_ids(ids,x):
    if isinstance(x,dict):
        for k in x: ids.add(str(k))
def fetch_raw(lid,weeks,warn):
    out={}
    for w in weeks:
        try:
            x=get(f'/league/{lid}/transactions/{w}'); x=[] if x is None else x
            if not isinstance(x,list): raise RuntimeError('response not list')
        except Exception as e:
            warn.append(f'Could not fetch transactions week {w}: {e}'); x=[]
        out[str(w)]={'week':w,'raw':[t for t in x if isinstance(t,dict)]}
    return out
def build(raw,labels,lookup):
    by={}; allx=[]; trades=[]; waivers=[]; fa=[]; by_type={}; by_status={}
    for wk,payload in raw.items():
        w=int(payload.get('week') or wk); items=[]
        for tx in sorted(payload.get('raw',[]),key=lambda x:x.get('created') or 0):
            typ,stat=tx.get('type'),tx.get('status'); by_type[str(typ or 'unknown')]=by_type.get(str(typ or 'unknown'),0)+1; by_status[str(stat or 'unknown')]=by_status.get(str(stat or 'unknown'),0)+1
            rids=tx.get('roster_ids') if isinstance(tx.get('roster_ids'),list) else []; cons=tx.get('consenter_ids') if isinstance(tx.get('consenter_ids'),list) else []
            item={'week':w,'transaction_id':tx.get('transaction_id'),'type':typ,'status':stat,'created':tx.get('created'),'created_at':ts(tx.get('created')),'status_updated':tx.get('status_updated'),'status_updated_at':ts(tx.get('status_updated')),'creator_user_id':tx.get('creator'),'roster_ids':rids,'team_labels':[labels.get(str(r),f'Roster {r}') for r in rids],'consenter_ids':cons,'consenter_team_labels':[labels.get(str(r),f'Roster {r}') for r in cons],'adds':move_map(tx.get('adds'),labels,lookup),'drops':move_map(tx.get('drops'),labels,lookup),'draft_picks':pick_list(tx.get('draft_picks'),labels),'waiver_budget':budgets(tx.get('waiver_budget'),labels),'settings':tx.get('settings') if isinstance(tx.get('settings'),dict) else {},'metadata':tx.get('metadata') if isinstance(tx.get('metadata'),dict) else {}}
            items.append(item); allx.append(item)
            if typ=='trade': trades.append(item)
            elif typ=='waiver': waivers.append(item)
            elif typ in {'free_agent','commissioner'}: fa.append(item)
        by[str(w)]={'week':w,'transactions':items,'counts':{'transactions':len(items),'trades':sum(1 for x in items if x.get('type')=='trade'),'waivers':sum(1 for x in items if x.get('type')=='waiver'),'free_agent_moves':sum(1 for x in items if x.get('type')=='free_agent')}}
    return {'by_week':by,'all':allx,'trades':trades,'waivers':waivers,'free_agent_moves':fa,'counts':{'weeks':len(by),'transactions':len(allx),'trades':len(trades),'waivers':len(waivers),'free_agent_moves':len(fa),'by_type':dict(sorted(by_type.items())),'by_status':dict(sorted(by_status.items()))}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(CFG)); ap.add_argument('--force-refresh-players',action='store_true'); a=ap.parse_args(); warn=[]
    try:
        cfg=rj(Path(a.config)); out=Path(g(cfg,['snapshot','output_dir'],'data/current')); lid=str(g(cfg,['league','league_id'])); manifest=rj(out/'manifest.json') if (out/'manifest.json').exists() else {}; weeks=manifest.get('included_weeks') or list(range(1,19))
        teams=rj(out/'teams.json') if (out/'teams.json').exists() else []; labels={str(t.get('roster_id')):str(t.get('display_label') or f"Roster {t.get('roster_id')}") for t in teams if isinstance(t,dict)}
        lookup=rj(out/'player_lookup_compact.json') if (out/'player_lookup_compact.json').exists() else {}; raw=fetch_raw(lid,weeks,warn); ids=set()
        for wk in raw.values():
            for tx in wk.get('raw',[]): add_ids(ids,tx.get('adds')); add_ids(ids,tx.get('drops'))
        players=cache_players(Path(g(cfg,['raw_cache','directory'],'raw_cache')),int(g(cfg,['player_cache','max_age_hours'],24)),a.force_refresh_players,warn)
        for x in sorted(ids): lookup.setdefault(x,compact(x,players))
        txs=build(raw,labels,lookup); wj(out/'transactions.json',txs); wj(out/'player_lookup_compact.json',lookup)
        bundle=rj(out/'chatgpt_bundle.json') if (out/'chatgpt_bundle.json').exists() else {}; bundle['transactions']=txs; bundle.setdefault('players',{})['by_id']=lookup; wj(out/'chatgpt_bundle.json',bundle)
        manifest.setdefault('counts',{}).update({'transactions':txs['counts']['transactions'],'trades':txs['counts']['trades'],'waivers':txs['counts']['waivers'],'free_agent_moves':txs['counts']['free_agent_moves'],'compact_player_lookup':len(lookup)}); manifest.setdefault('data_quality',{}).setdefault('warnings',[]).extend(warn); manifest['phase']='phase_4_transactions_extension'; wj(out/'manifest.json',manifest)
        print(f"Wrote transactions: {txs['counts']['transactions']} total, {txs['counts']['trades']} trades, {txs['counts']['waivers']} waivers"); return 0
    except Exception as e:
        print(f'Transaction export failed: {e}',file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())

#!/usr/bin/env python3
"""Phase 5 draft and traded-pick extension for the current Sleeper snapshot."""
import argparse,json,sys,time,urllib.request
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
            req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'Sleeper-Drafts/1.0'})
            with urllib.request.urlopen(req,timeout=45) as r: return json.loads(r.read().decode())
        except Exception as e:
            err=e; time.sleep(1.25*(i+1))
    raise RuntimeError(f'GET failed {url}: {err}')
def ts(v):
    try: n=int(v)
    except Exception: return None
    if n>10_000_000_000: n/=1000
    return datetime.fromtimestamp(n,timezone.utc).isoformat().replace('+00:00','Z')
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
    p=players.get(str(pid))
    if not isinstance(p,dict):
        return {'player_id':str(pid),'name':f'Unknown Player {pid}','team':None,'position':None,'fantasy_positions':[],'missing_from_full_cache':True}
    name=p.get('full_name') or ' '.join(str(v).strip() for v in (p.get('first_name'),p.get('last_name')) if v) or str(p.get('search_full_name') or pid)
    return {'player_id':str(p.get('player_id') or pid),'name':name,'first_name':p.get('first_name'),'last_name':p.get('last_name'),'team':p.get('team'),'position':p.get('position'),'fantasy_positions':p.get('fantasy_positions') or [],'status':p.get('status'),'injury_status':p.get('injury_status'),'years_exp':p.get('years_exp'),'age':p.get('age'),'depth_chart_position':p.get('depth_chart_position'),'search_rank':p.get('search_rank')}
def pname(pid,lookup): return str(lookup.get(str(pid),{}).get('name') or pid)
def labels_from_teams(teams): return {str(t.get('roster_id')):str(t.get('display_label') or f"Roster {t.get('roster_id')}") for t in teams if isinstance(t,dict) and t.get('roster_id') is not None}
def safe_list(x): return x if isinstance(x,list) else []
def roster_label(rid,labels): return labels.get(str(rid),f'Roster {rid}') if rid is not None else None
def normalize_pick(p,labels,lookup):
    pid=p.get('player_id')
    return {'pick_no':p.get('pick_no'),'round':p.get('round'),'draft_slot':p.get('draft_slot'),'roster_id':p.get('roster_id'),'team_label':roster_label(p.get('roster_id'),labels),'player_id':str(pid) if pid is not None else None,'player_name':pname(str(pid),lookup) if pid is not None else None,'metadata':p.get('metadata') if isinstance(p.get('metadata'),dict) else {},'is_keeper':p.get('is_keeper'),'picked_by':p.get('picked_by')}
def normalize_tp(p,labels):
    orig,prev,own=p.get('roster_id'),p.get('previous_owner_id'),p.get('owner_id')
    return {'season':p.get('season'),'round':p.get('round'),'draft_id':p.get('draft_id'),'original_roster_id':orig,'original_team_label':roster_label(orig,labels),'previous_owner_id':prev,'previous_owner_team_label':roster_label(prev,labels),'owner_id':own,'owner_team_label':roster_label(own,labels)}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(CFG)); ap.add_argument('--force-refresh-players',action='store_true'); a=ap.parse_args(); warn=[]
    try:
        cfg=rj(Path(a.config)); out=Path(g(cfg,['snapshot','output_dir'],'data/current')); lid=str(g(cfg,['league','league_id'])); teams=rj(out/'teams.json') if (out/'teams.json').exists() else []; labels=labels_from_teams(teams); lookup=rj(out/'player_lookup_compact.json') if (out/'player_lookup_compact.json').exists() else {}
        league_drafts=safe_list(get(f'/league/{lid}/drafts')); league_traded=safe_list(get(f'/league/{lid}/traded_picks'))
        draft_ids=[d.get('draft_id') for d in league_drafts if isinstance(d,dict) and d.get('draft_id')]
        raw_picks={}; raw_draft_tps={}; pick_ids=set()
        for did in draft_ids:
            try: picks=safe_list(get(f'/draft/{did}/picks'))
            except Exception as e: warn.append(f'Could not fetch draft picks for {did}: {e}'); picks=[]
            try: tps=safe_list(get(f'/draft/{did}/traded_picks'))
            except Exception as e: warn.append(f'Could not fetch draft traded picks for {did}: {e}'); tps=[]
            raw_picks[str(did)]=[p for p in picks if isinstance(p,dict)]; raw_draft_tps[str(did)]=[p for p in tps if isinstance(p,dict)]
            for p in raw_picks[str(did)]:
                if p.get('player_id') is not None: pick_ids.add(str(p.get('player_id')))
        if pick_ids:
            players=cache_players(Path(g(cfg,['raw_cache','directory'],'raw_cache')),int(g(cfg,['player_cache','max_age_hours'],24)),a.force_refresh_players,warn)
            for pid in sorted(pick_ids): lookup.setdefault(pid,compact(pid,players))
            wj(out/'player_lookup_compact.json',lookup)
        drafts=[]; total_picks=0; total_draft_tp=0
        for d in league_drafts:
            if not isinstance(d,dict): continue
            did=str(d.get('draft_id')); picks=[normalize_pick(p,labels,lookup) for p in raw_picks.get(did,[])]; tps=[normalize_tp(p,labels) for p in raw_draft_tps.get(did,[])]
            total_picks+=len(picks); total_draft_tp+=len(tps)
            by_round={}
            for p in picks: by_round.setdefault(str(p.get('round')),[]).append(p)
            drafts.append({'draft_id':d.get('draft_id'),'type':d.get('type'),'status':d.get('status'),'season':d.get('season'),'season_type':d.get('season_type'),'sport':d.get('sport'),'created':d.get('created'),'created_at':ts(d.get('created')),'start_time':d.get('start_time'),'start_time_at':ts(d.get('start_time')),'settings':d.get('settings') if isinstance(d.get('settings'),dict) else {},'metadata':d.get('metadata') if isinstance(d.get('metadata'),dict) else {},'draft_order':d.get('draft_order') if isinstance(d.get('draft_order'),dict) else {},'slot_to_roster_id':d.get('slot_to_roster_id') if isinstance(d.get('slot_to_roster_id'),dict) else {},'picks':picks,'picks_by_round':dict(sorted(by_round.items(),key=lambda x:int(x[0]) if str(x[0]).isdigit() else 999)),'traded_picks':tps,'counts':{'picks':len(picks),'traded_picks':len(tps)}})
        traded={'league_traded_picks':[normalize_tp(p,labels) for p in league_traded if isinstance(p,dict)],'draft_traded_picks_by_draft_id':{did:[normalize_tp(p,labels) for p in ps] for did,ps in raw_draft_tps.items()},'counts':{'league_traded_picks':len([p for p in league_traded if isinstance(p,dict)]),'draft_traded_picks':total_draft_tp}}
        drafts_payload={'drafts':drafts,'counts':{'drafts':len(drafts),'draft_picks':total_picks,'draft_traded_picks':total_draft_tp}}
        wj(out/'drafts.json',drafts_payload); wj(out/'traded_picks.json',traded)
        bundle=rj(out/'chatgpt_bundle.json') if (out/'chatgpt_bundle.json').exists() else {}; bundle['drafts']=drafts; bundle['traded_picks']=traded; bundle.setdefault('players',{})['by_id']=lookup; wj(out/'chatgpt_bundle.json',bundle)
        manifest=rj(out/'manifest.json') if (out/'manifest.json').exists() else {}; manifest.setdefault('counts',{}).update({'drafts':len(drafts),'draft_picks':total_picks,'draft_traded_picks':total_draft_tp,'league_traded_picks':traded['counts']['league_traded_picks'],'compact_player_lookup':len(lookup)}); manifest.setdefault('data_quality',{}).setdefault('warnings',[]).extend(warn); manifest['phase']='phase_5_drafts_extension'; wj(out/'manifest.json',manifest)
        print(f"Wrote drafts: {len(drafts)} drafts, {total_picks} picks, {traded['counts']['league_traded_picks']} league traded picks"); return 0
    except Exception as e:
        print(f'Draft export failed: {e}',file=sys.stderr); return 1
if __name__=='__main__': raise SystemExit(main())

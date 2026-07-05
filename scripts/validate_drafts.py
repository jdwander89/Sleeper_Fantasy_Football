#!/usr/bin/env python3
"""Validate draft and traded-pick output added by scripts/sleeper_drafts.py."""
import argparse,json
from pathlib import Path
CFG=Path('config/league_config.json')
def rj(p):
    with open(p,encoding='utf-8') as f: return json.load(f)
def g(x,path,d=None):
    for k in path:
        if not isinstance(x,dict) or k not in x: return d
        x=x[k]
    return x
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(CFG)); ap.add_argument('--snapshot-dir',default=None); a=ap.parse_args(); errors=[]; warnings=[]
    try:
        cfg=rj(Path(a.config)); out=Path(a.snapshot_dir or g(cfg,['snapshot','output_dir'],'data/current'))
        paths={'drafts':out/'drafts.json','traded':out/'traded_picks.json','bundle':out/'chatgpt_bundle.json','manifest':out/'manifest.json','lookup':out/'player_lookup_compact.json'}
        for name,p in paths.items():
            if not p.exists(): errors.append(f'Missing file: {p}')
        if errors: raise RuntimeError('missing files')
        drafts=rj(paths['drafts']); traded=rj(paths['traded']); bundle=rj(paths['bundle']); manifest=rj(paths['manifest']); lookup=rj(paths['lookup'])
        if not isinstance(drafts,dict): errors.append('drafts.json must be an object')
        if not isinstance(traded,dict): errors.append('traded_picks.json must be an object')
        if isinstance(drafts,dict):
            if not isinstance(drafts.get('drafts'),list): errors.append('drafts.json drafts must be a list')
            if not isinstance(drafts.get('counts'),dict): errors.append('drafts.json counts must be an object')
        ids=set(); draft_list=drafts.get('drafts',[]) if isinstance(drafts,dict) else []
        for d in draft_list if isinstance(draft_list,list) else []:
            if not isinstance(d,dict): errors.append('drafts contains non-object item'); continue
            for k in ('draft_id','picks','traded_picks','counts'):
                if k not in d: errors.append(f'draft missing {k}')
            for p in d.get('picks',[]) if isinstance(d.get('picks'),list) else []:
                if not isinstance(p,dict): errors.append(f'draft {d.get("draft_id")} has non-object pick'); continue
                if p.get('player_id') is not None: ids.add(str(p['player_id']))
        if isinstance(lookup,dict):
            missing=sorted(ids-set(str(k) for k in lookup.keys()))
            if missing: errors.append(f'draft player IDs missing from player lookup: {missing}')
        else: errors.append('player_lookup_compact.json must be an object')
        if isinstance(traded,dict):
            if not isinstance(traded.get('league_traded_picks'),list): errors.append('traded_picks.json league_traded_picks must be a list')
            if not isinstance(traded.get('draft_traded_picks_by_draft_id'),dict): errors.append('traded_picks.json draft_traded_picks_by_draft_id must be an object')
        if isinstance(bundle,dict):
            if not isinstance(bundle.get('drafts'),list): errors.append('chatgpt_bundle.json drafts must be a list')
            if not isinstance(bundle.get('traded_picks'),dict): errors.append('chatgpt_bundle.json traded_picks must be an object')
            if isinstance(drafts,dict) and len(bundle.get('drafts',[]))!=len(drafts.get('drafts',[])): warnings.append('bundle draft count differs from drafts.json')
        else: errors.append('chatgpt_bundle.json must be an object')
        if isinstance(manifest,dict) and isinstance(manifest.get('counts'),dict) and isinstance(drafts,dict):
            if manifest['counts'].get('drafts')!=g(drafts,['counts','drafts']): warnings.append('manifest counts.drafts differs from drafts.json')
            if manifest['counts'].get('draft_picks')!=g(drafts,['counts','draft_picks']): warnings.append('manifest counts.draft_picks differs from drafts.json')
        else: errors.append('manifest.json counts must be an object')
    except RuntimeError: pass
    except Exception as e: errors.append(f'Validation failed unexpectedly: {e}')
    print('Draft validation passed.' if not errors else 'Draft validation failed.')
    if errors:
        print('\nErrors:'); [print(f'- {e}') for e in errors]
    if warnings:
        print('\nWarnings:'); [print(f'- {w}') for w in warnings]
    print(f'\nSummary: {len(errors)} error(s), {len(warnings)} warning(s)')
    return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())

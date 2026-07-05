#!/usr/bin/env python3
"""Validate transaction output added by scripts/sleeper_transactions.py."""
import argparse,json,sys
from pathlib import Path
CFG=Path('config/league_config.json')
def rj(p):
    with open(p,encoding='utf-8') as f: return json.load(f)
def g(x,path,d=None):
    for k in path:
        if not isinstance(x,dict) or k not in x: return d
        x=x[k]
    return x
def err(errors,msg): errors.append(msg)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=str(CFG)); ap.add_argument('--snapshot-dir',default=None); a=ap.parse_args(); errors=[]; warnings=[]
    try:
        cfg=rj(Path(a.config)); out=Path(a.snapshot_dir or g(cfg,['snapshot','output_dir'],'data/current'))
        tx_path=out/'transactions.json'; bundle_path=out/'chatgpt_bundle.json'; manifest_path=out/'manifest.json'; lookup_path=out/'player_lookup_compact.json'
        for p in (tx_path,bundle_path,manifest_path,lookup_path):
            if not p.exists(): err(errors,f'Missing file: {p}')
        if errors: raise SystemExit
        tx=rj(tx_path); bundle=rj(bundle_path); manifest=rj(manifest_path); lookup=rj(lookup_path)
        if not isinstance(tx,dict): err(errors,'transactions.json must be an object')
        for k in ('by_week','all','trades','waivers','free_agent_moves','counts'):
            if k not in tx: err(errors,f'transactions.json missing {k}')
        ids=set()
        if isinstance(tx.get('by_week'),dict):
            for wk,payload in tx['by_week'].items():
                if not isinstance(payload,dict): err(errors,f'transactions week {wk} must be an object'); continue
                if not isinstance(payload.get('transactions'),list): err(errors,f'transactions week {wk} transactions must be a list'); continue
                for item in payload['transactions']:
                    if not isinstance(item,dict): err(errors,f'transactions week {wk} contains non-object item'); continue
                    for side in ('adds','drops'):
                        if not isinstance(item.get(side),list): err(errors,f'transaction {item.get("transaction_id")} {side} must be a list'); continue
                        for move in item[side]:
                            if isinstance(move,dict) and move.get('player_id') is not None: ids.add(str(move['player_id']))
        if isinstance(lookup,dict):
            missing=sorted(ids-set(str(x) for x in lookup.keys()))
            if missing: err(errors,f'transaction player IDs missing from player lookup: {missing}')
        else: err(errors,'player_lookup_compact.json must be an object')
        if g(bundle,['transactions','counts'])!=tx.get('counts'): warnings.append('bundle transactions.counts differs from transactions.json')
        if isinstance(manifest.get('counts'),dict):
            for k in ('transactions','trades','waivers','free_agent_moves'):
                if manifest['counts'].get(k)!=g(tx,['counts',k]): warnings.append(f'manifest counts.{k} differs from transactions.json')
    except SystemExit: pass
    except Exception as e: err(errors,f'Validation failed unexpectedly: {e}')
    print('Transaction validation passed.' if not errors else 'Transaction validation failed.')
    if errors:
        print('\nErrors:'); [print(f'- {e}') for e in errors]
    if warnings:
        print('\nWarnings:'); [print(f'- {w}') for w in warnings]
    print(f'\nSummary: {len(errors)} error(s), {len(warnings)} warning(s)')
    return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())

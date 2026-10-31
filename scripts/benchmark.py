"""Reproducible maximum-size domain benchmark with synthetic data only."""
import json
import tempfile
import time
from pathlib import Path
from inventory.core import Store


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'bench.db');metrics={}
        started=time.perf_counter()
        raw=('商品番号,名称,数量\n'+''.join(f'{i:06},架空資材{i},10\n' for i in range(5000))).encode()
        s=store.create(raw,['A'],'benchmark');metrics['import_5000_s']=time.perf_counter()-started
        started=time.perf_counter()
        for version in range(4):
            for begin in range(0,5000,1000):
                records=[dict(id=f'{version}-{i}',device='bench',code=f'{i:06}',location='A',quantity='8',operator='benchmark',supersedes=[f'{version-1}-{i}'] if version else []) for i in range(begin,begin+1000)]
                s=store.change(s['id'],s['revision'],'receive','benchmark',records)
        metrics['write_20000_history_s']=time.perf_counter()-started
        started=time.perf_counter();rows=store.summary(s);metrics['summary_5000_s']=time.perf_counter()-started
        assert len(rows)==5000 and all(r['difference']=='-2' for r in rows)
        started=time.perf_counter();s=store.change(s['id'],s['revision'],'complete','benchmark',{'location':'A'});s=store.change(s['id'],s['revision'],'finalize','benchmark',None);metrics['complete_finalize_s']=time.perf_counter()-started
        metrics['db_bytes']=(Path(tmp)/'bench.db').stat().st_size;store.close();print(json.dumps(metrics,indent=2))


if __name__=='__main__':main()

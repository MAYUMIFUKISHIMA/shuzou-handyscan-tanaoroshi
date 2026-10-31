"""Synthetic host demo; no BT-W250 SDK or device required."""
import argparse
import json
from pathlib import Path
from .core import Store
from .handheld import distribution,TerminalSimulator,receive_batch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='data/handheld-demo');args=parser.parse_args()
    root=Path(args.output)
    root.mkdir(parents=True,exist_ok=False)
    pc=Store(root/'pc.sqlite3')
    try:
        raw='商品番号,名称,数量\n000001,架空の発送箱,10\n'.encode()
        s=pc.create(raw,['A'],'模擬担当');package=distribution(s)
        (root/'distribution.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
        terminal=TerminalSimulator(root/'terminal.sqlite3',package,'SIM-01')
        terminal.count('000001','8','A','模擬担当');terminal.close()
        terminal=TerminalSimulator(root/'terminal.sqlite3',package,'SIM-01')
        try:
            batch=terminal.batch()
            receive_batch(pc,batch,'回収担当') # Response lost: do not acknowledge yet.
            receipt=receive_batch(pc,terminal.batch(),'回収担当')
            terminal.acknowledge(batch,receipt)
            for name,data in [('batch',batch),('receipt',receipt)]:
                (root/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            summary=pc.summary(pc.load(s['id']))
            assert summary[0]['count']=='8' and len(pc.load(s['id'])['records'])==1
            print(json.dumps(dict(mode='host_simulation_only',summary=summary),ensure_ascii=False,indent=2))
        finally:terminal.close()
    finally:pc.close()


if __name__=='__main__':main()

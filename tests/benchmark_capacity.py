"""Synthetic capacity measurements over actual local HTTP; never real research data."""
import argparse
import concurrent.futures
import http.client
import json
import math
import platform
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.app import Application,handler_class
from server.platform.config import load_config
from server.platform.store import Store


def run(output):
    with tempfile.TemporaryDirectory(prefix='world-insight-capacity-fixture-') as directory:
        config=load_config(data_dir=directory,port=8868);store=Store(config['db_path'])
        started=time.perf_counter()
        with store.transaction():
            for n in range(10):
                store.create('topic',{'question':f'[容量夹具] 研究议题 {n}','followed':True,'status':'active'},f'topic-{n}')
            for n in range(20000):
                tid=f'topic-{n%10}';eid=f'evidence-{n}'
                store.create('evidence',{'topic_id':tid,'topic_ids':[tid],'source_id':'fixture','title':f'[容量夹具] 官方政策记录 {n} · policy review',
                                        'url':f'https://fixture.example/material/{n}','source_record_id':str(n),'excerpt':'明确标识的模拟材料，仅用于容量性能验证。'*10,
                                        'rights':{'store':True,'display':True,'export':True},'status':'unverified','published_at':'2026-09-10',
                                        'collected_at':store.now(),'language':'zh','channels':[],'is_fixture':True},eid)
                store.create('change',{'topic_id':tid,'topic_ids':[tid],'type':'evidence.created','aggregate_id':eid,
                                      'title':'[容量夹具] 新增材料，待核查','discovered_at':store.now(),'occurred_at':None,'needs_review':False},f'change-{n}')
            for n in range(5000):
                store.create('event',{'topic_id':f'topic-{n%10}','title':f'[容量夹具] 事件 {n}','time_precision':'day','occurred_at':'2026-09-10',
                                     'location':{'country_code':'CHN','precision':'country'},'verification_status':'unverified','claim_ids':[]},f'event-{n}')
        seed_seconds=time.perf_counter()-started
        app=Application(config,store,{'instance_id':'capacity-fixture'})
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_class(app));config['port']=server.server_port
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02});thread.start()
        def reader(session):
            samples=[]
            for i in range(8):
                category='dashboard' if i%2==0 else 'filter'
                path='/api/dashboard?window=7d&limit=20' if category=='dashboard' else f'/api/evidence?topic_id=topic-{session}&limit=50&offset={i*50}'
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
                start=time.perf_counter();conn.request('GET',path);response=conn.getresponse();raw=response.read();elapsed=time.perf_counter()-start;conn.close()
                if response.status!=200:raise RuntimeError(f'Benchmark request failed {response.status}')
                body=json.loads(raw)
                if category=='filter' and body.get('total')!=2000:raise RuntimeError('Incorrect filter result')
                samples.append({'session':session,'category':category,'seconds':round(elapsed,6),'bytes':len(raw)})
            return samples
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                samples=[sample for result in pool.map(reader,range(5)) for sample in result]
        finally:
            server.shutdown();server.server_close();thread.join();store.close()
        summaries={}
        for category in ('dashboard','filter'):
            values=sorted(s['seconds'] for s in samples if s['category']==category)
            summaries[category]={'count':len(values),'p95_seconds':values[math.ceil(len(values)*.95)-1],'max_seconds':max(values)}
        report={'date':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'environment':{'platform':platform.platform(),'architecture':platform.machine(),
                 'python':platform.python_version(),'cpu_count':__import__('os').cpu_count(),'network':'loopback only; no upstream requests',
                 'cache':'SQLite warm after fixture generation'},'fixture':{'topics':10,'evidence':20000,'events':5000,'changes':20000,'concurrent_sessions':5},
                'seed_seconds':round(seed_seconds,3),'summaries':summaries,'samples':samples,
                'boundaries':'Synthetic actual HTTP API benchmark; dashboard API latency is not browser first usable content or seven-day real observation.'}
        Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('environment','fixture','summaries','boundaries')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();run(args.output)

"""Loopback-only server. A single process owns each research data directory."""
import argparse
import fcntl
import importlib
import json
import mimetypes
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from server.platform.config import ROOT, ensure_data, load_config
from server.platform.errors import ApiError
from server.platform.migrations import SCHEMA_VERSION
from server.platform.store import Store

VERSION = (ROOT/'VERSION').read_text().strip()
TEMPLATES = [
    {'name':'地区冲突与外交','question':'哪些公开行动可能改变冲突与外交进程？','keywords':[]},
    {'name':'制裁与贸易政策','question':'政策条文与实施行为发生了什么变化？','keywords':[]},
    {'name':'能源与航道','question':'哪些可核查变化影响能源供应与航运？','keywords':[]},
    {'name':'主要国家政策变化','question':'公开政策目标与实际执行有哪些差异？','keywords':[]},
]


def module(name):
    return importlib.import_module('server.modules.'+name)


class Application:
    def __init__(self, config, store, identity):
        self.config,self.store,self.identity = config,store,identity
        self.modules = [module(n) for n in ('knowledge.lifecycle','knowledge','research','sources','activity')]

    def dispatch(self, method, path, body, query):
        segments = [s for s in path.split('/') if s][1:]
        if segments == ['health'] and method=='GET':
            return {'status':'ok','app':'world-insight','version':VERSION,'schema_version':SCHEMA_VERSION,
                    'instance_id':self.identity['instance_id'],'data_dir':str(self.store.data_dir),
                    'pid':os.getpid(),'maintenance':(self.store.data_dir/'maintenance.json').exists()}
        if segments == ['bootstrap'] and method=='GET':
            return {'version':VERSION,'schema_version':SCHEMA_VERSION,'data_dir':str(self.store.data_dir),
                    'backup_dir':str(self.config['backup_dir']),'templates':TEMPLATES,
                    'capabilities':{k:{'status':'not_configured','enabled':False} for k in ('ai','aviation','shipping','market_data')},
                    'paid_enabled':False,'ai_enabled':False,'timezone':'Asia/Shanghai'}
        if segments and segments[0] in ('tracks','ai','market-data'):
            return {'status':'not_configured','data_status':'unavailable','items':[],
                    'reason':'P0 未接入，默认禁用；空列表不表示现实中不存在活动'}
        if method not in ('GET','HEAD') and (self.store.data_dir/'maintenance.json').exists():
            raise ApiError(503,'maintenance','系统正在维护，写入与采集已暂停；现有资料仍可阅读')
        for mod in self.modules:
            handler = getattr(mod,'handle',None)
            if handler:
                value = handler(self.store,method,segments,body,query)
                if value is not None:
                    return value
        raise ApiError(404,'route_not_found','请求的功能不存在')

    def drain(self):
        consumers = [getattr(mod,'on_event') for mod in (module('research'),module('activity')) if hasattr(mod,'on_event')]
        if consumers:
            return self.store.drain(consumers)
        return 0

    def maintain(self):
        """One bounded retention batch, with a persistent deadline across restarts."""
        if (self.store.data_dir/'maintenance.json').exists():
            return None
        key='evidence-retention'
        try:checkpoint=self.store.get('maintenance_checkpoint',key)
        except ApiError as error:
            if error.status!=404:raise
            checkpoint=None
        now=time.time()
        if checkpoint and checkpoint.get('next_check_at',0)>now:return None
        result=module('knowledge.lifecycle').run_retention(self.store,{'operation_id':f'scheduled-{int(now//300)}'})
        data={'last_check_at':self.store.now(),'next_check_at':now+(300 if result.get('remaining') or result.get('state')!='complete' else 86400),
              'state':result['state'],'operation_id':result['operation_id'],'remaining':result.get('remaining',0)}
        if checkpoint:self.store.update('maintenance_checkpoint',key,data,checkpoint['version'])
        else:self.store.create('maintenance_checkpoint',data,key)
        return result


def handler_class(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            # Browser idle/keep-alive sockets must not prevent a normal Mac stop/update.
            self.connection.settimeout(5)

        def log_message(self, fmt, *args):
            # Request URLs can contain private query text. Log only method/status.
            pass

        def do_GET(self): self.respond('GET')
        def do_HEAD(self): self.respond('HEAD')
        def do_POST(self): self.respond('POST')
        def do_PATCH(self): self.respond('PATCH')
        def do_DELETE(self): self.respond('DELETE')

        def send_content(self, status, content, content_type='application/json; charset=utf-8'):
            data = content if isinstance(content,bytes) else json.dumps(content,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store')
            self.send_header('Connection','close')
            self.close_connection = True
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)

        def respond(self, method):
            try:
                valid_hosts = {f'127.0.0.1:{app.config["port"]}',f'localhost:{app.config["port"]}'}
                host = self.headers.get('Host','')
                if host not in valid_hosts:
                    raise ApiError(403,'invalid_host','仅接受本机应用地址')
                origin = self.headers.get('Origin')
                if origin and origin not in {'http://'+h for h in valid_hosts}:
                    raise ApiError(403,'invalid_origin','拒绝来自其他站点的请求')
                parsed = urlparse(self.path)
                if parsed.path.startswith('/api/'):
                    body = {}
                    if method not in ('GET','HEAD'):
                        try: length = int(self.headers.get('Content-Length','0'))
                        except ValueError: raise ApiError(400,'invalid_length','请求长度无效')
                        if length < 0 or length > 2_000_000: raise ApiError(413,'body_too_large','请求内容超过 2 MB 限制')
                        if length:
                            if not self.headers.get('Content-Type','').startswith('application/json'):
                                raise ApiError(415,'json_required','请使用 JSON 请求')
                            def invalid_number(value):
                                raise ValueError('Non-finite JSON number')
                            try: body = json.loads(self.rfile.read(length),parse_constant=invalid_number)
                            except (ValueError,UnicodeError): raise ApiError(400,'invalid_json','JSON 格式错误')
                            if not isinstance(body,dict): raise ApiError(400,'object_required','请求应为 JSON 对象')
                    query = {k:v[-1] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
                    # Modules own transaction scope, in particular collector network I/O must stay outside it.
                    result = app.dispatch('GET' if method=='HEAD' else method,parsed.path,body,query)
                    if method not in ('GET','HEAD'): app.drain()
                    self.send_content(200,result)
                elif method in ('GET','HEAD'):
                    webroot = (app.config['root']/'web').resolve()
                    filepath = (webroot/unquote(parsed.path).lstrip('/')).resolve()
                    if not filepath.is_relative_to(webroot): raise ApiError(403,'forbidden','路径不可访问')
                    if filepath.is_dir(): filepath = filepath/'index.html'
                    if not filepath.exists():
                        if '.' not in filepath.name: filepath=webroot/'index.html'
                        if not filepath.is_file(): raise ApiError(404,'not_found','页面不存在')
                    content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
                    if filepath.suffix=='.js': content_type='text/javascript'
                    self.send_content(200,filepath.read_bytes(),content_type+'; charset=utf-8')
                else:
                    raise ApiError(405,'method_not_allowed','不支持此操作')
            except ApiError as exc:
                self.send_content(exc.status,exc.as_dict())
            except (BrokenPipeError,ConnectionResetError):
                pass
            except Exception as exc:
                print(json.dumps({'error':type(exc).__name__,'at':app.store.now()}),flush=True)
                self.send_content(500,{'error':{'code':'internal_error','message':'本地服务处理失败，请查看脱敏运行日志','details':None}})
    return Handler


def serve(config, initialize=False, scheduler_enabled=True):
    identity = ensure_data(config,initialize)
    config['data_dir'].mkdir(parents=True,exist_ok=True)
    lock = (config['data_dir']/'service.lock').open('a+')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise RuntimeError('该数据目录已有运行实例，不创建第二个服务或采集器')
    store = Store(config['db_path'])
    (config['data_dir']/'instance.json').write_text(json.dumps(identity))
    app = Application(config,store,identity)
    sources=module('sources')
    if hasattr(sources,'seed_sources'): sources.seed_sources(store)
    server = ThreadingHTTPServer((config['host'],config['port']),handler_class(app))
    server.daemon_threads = False
    scheduler = sources.start_scheduler(store) if scheduler_enabled and hasattr(sources,'start_scheduler') else None
    stop_event = threading.Event()
    def worker():
        while not stop_event.wait(1):
            try:
                app.drain()
                app.maintain()
            except Exception as exc: print(json.dumps({'worker_error':type(exc).__name__}),flush=True)
    thread = threading.Thread(target=worker,daemon=True,name='outbox'); thread.start()
    runtime = {'pid':os.getpid(),'port':config['port'],'data_dir':str(config['data_dir']),
               'root':str(config['root']),'instance_id':identity['instance_id'],'version':VERSION,'started_at':store.now()}
    (config['data_dir']/'runtime.json').write_text(json.dumps(runtime))
    def stop(*_):
        stop_event.set()
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    print(json.dumps({'status':'ready',**runtime},ensure_ascii=False),flush=True)
    try: server.serve_forever(poll_interval=.25)
    finally:
        stop_event.set()
        if scheduler and hasattr(sources,'stop_scheduler'): sources.stop_scheduler(scheduler)
        server.server_close(); thread.join(timeout=5); store.close()
        (config['data_dir']/'runtime.json').unlink(missing_ok=True)
        fcntl.flock(lock,fcntl.LOCK_UN); lock.close()


def main():
    parser=argparse.ArgumentParser(description='World Insight 本地研究看板')
    parser.add_argument('--data-dir'); parser.add_argument('--port',type=int)
    parser.add_argument('--init',action='store_true',help='显式创建新研究数据目录')
    parser.add_argument('--no-scheduler',action='store_true')
    args=parser.parse_args()
    try: serve(load_config(data_dir=args.data_dir,port=args.port),args.init,not args.no_scheduler)
    except Exception as exc:
        # Known local setup errors contain paths/instructions, not credentials.
        if isinstance(exc,(ValueError,RuntimeError,OSError)): print('启动失败：'+str(exc),flush=True)
        else: print('启动失败：'+type(exc).__name__,flush=True)
        raise SystemExit(1)


if __name__=='__main__': main()

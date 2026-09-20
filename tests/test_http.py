import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.app import Application,handler_class
from server.platform.config import load_config
from server.platform.store import Store


class LocalHttpCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name)
        self.config=load_config(data_dir=self.data,port=8870)
        self.store=Store(self.config['db_path'])
        self.app=Application(self.config,self.store,{'instance_id':'http-fixture'})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_class(self.app))
        self.config['port']=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.02});self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.close();self.tmp.cleanup()
    def request(self,path,method='GET',body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        content=json.dumps(body).encode() if body is not None else None
        conn.request(method,path,body=content,headers={'Content-Type':'application/json',**(headers or {})})
        response=conn.getresponse();status=response.status;data=response.read();conn.close()
        return status,json.loads(data)


class LocalHttpTests(LocalHttpCase):
    def test_health_and_disabled_capabilities(self):
        self.assertEqual(self.request('/api/health')[1]['instance_id'],'http-fixture')
        for capability in ('tracks','ai','market-data'):
            status,data=self.request('/api/'+capability)
            self.assertEqual(status,200);self.assertEqual(data['status'],'not_configured')
            self.assertNotEqual(data.get('empty_reason'),'no_matches')
    def test_other_site_and_host_cannot_access_local_research(self):
        self.assertEqual(self.request('/api/health',headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/health',headers={'Host':'evil.example'})[0],403)
    def test_static_path_cannot_escape_web(self):
        self.assertEqual(self.request('/%2e%2e/docs/PRD.md')[0],403)
    def test_maintenance_rejects_write_but_keeps_reading(self):
        (self.data/'maintenance.json').write_text('{}')
        self.assertEqual(self.request('/api/topics','POST',{'question':'fixture'})[0],503)
        self.assertEqual(self.request('/api/health')[0],200)


if __name__=='__main__':unittest.main()

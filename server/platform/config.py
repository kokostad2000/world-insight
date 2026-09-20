import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = Path.home() / 'Library' / 'Application Support' / 'World Insight'


def read_env(root=ROOT):
    values = {}
    env_file = Path(root)/'.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            if '=' not in line: raise ValueError('配置格式错误：每行应为 KEY=value；具体值已隐藏')
            key,value = line.split('=',1)
            if not key.strip().replace('_','').isalnum(): raise ValueError('配置名称无效')
            values[key.strip()] = value.strip().strip('\"\'')
    values.update({k:v for k,v in os.environ.items() if k.startswith('WORLD_INSIGHT_')})
    return values


def load_config(root=ROOT, data_dir=None, port=None):
    env = read_env(root)
    data = Path(data_dir or env.get('WORLD_INSIGHT_DATA_DIR') or DEFAULT_DATA_DIR).expanduser().resolve()
    port = int(port or env.get('WORLD_INSIGHT_PORT','8766'))
    if not 1024 <= port <= 65535: raise ValueError('端口范围应为 1024—65535')
    return {'root':Path(root).resolve(),'data_dir':data,'db_path':data/'world-insight.sqlite',
            'backup_dir':Path(env.get('WORLD_INSIGHT_BACKUP_DIR') or data.parent/(data.name+' Backups')).expanduser().resolve(),
            'port':port,'host':'127.0.0.1','open_browser':env.get('WORLD_INSIGHT_OPEN_BROWSER','1')=='1',
            'ai_enabled':False,'paid_enabled':False}


def ensure_data(config, initialize=False):
    data = config['data_dir']; marker = data/'instance.json'
    if marker.exists():
        if not config['db_path'].exists():
            raise ValueError('既有数据目录缺少数据库，停止启动。请恢复备份或明确选择新的空目录')
        return json.loads(marker.read_text())
    if not initialize:
        raise ValueError(f'数据目录尚未确认：{data}。首次运行请使用 --init；已有研究请配置原数据目录，不要创建空库')
    if config['db_path'].exists():
        raise ValueError('目录已有数据库但缺少实例身份，请通过恢复检查后绑定；未覆盖原数据')
    data.mkdir(parents=True,exist_ok=True)
    for child in ('attachments','cache','logs'): (data/child).mkdir(exist_ok=True)
    identity = {'instance_id':str(uuid.uuid4()),'format':1}
    # marker is committed only once database creation succeeds in app.start.
    return identity

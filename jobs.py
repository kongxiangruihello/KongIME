"""One background configuration job; HTTP mutations are blocked until it completes."""
import threading
import uuid
import workflow
LOCK=threading.Lock()
JOB={'running':False,'stage':'idle'}

def status():
    with LOCK:return dict(JOB)

def start(kind):
    if kind not in ('deploy','recover','pick'):raise ValueError('未知任务')
    with LOCK:
        if JOB['running']:raise ValueError('正在处理配置，请等待完成')
        JOB.clear();JOB.update(id=uuid.uuid4().hex,running=True,stage='backup',kind=kind)
    def progress(stage):
        with LOCK:JOB['stage']=stage
    def run():
        try:
            result=workflow.pick_directory() if kind=='pick' else (workflow.deploy if kind=='deploy' else workflow.recover)(progress)
            with LOCK:JOB.update(running=False,stage='done',result=result)
        except Exception as e:
            with LOCK:JOB.update(running=False,stage='failed',error=str(e))
    threading.Thread(target=run,daemon=False).start()
    return status()

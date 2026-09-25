"""Smoke-check the compiled engine without touching live sessions or learning data."""
import json,shutil,subprocess,tempfile,time
from pathlib import Path
import core

def run(app,enabled):
 helper=core.ROOT/'engine-check'
 if not helper.is_file():helper=core.ROOT/'client/build/engine-check'
 if not helper.is_file():raise ValueError('缺少输入检查程序，请重新安装当前版本')
 with tempfile.TemporaryDirectory(prefix='kongime-engine-check-') as tmp:
  root=Path(tmp);(root/'build').mkdir()
  for name in ['qingyan.schema.yaml','qingyan.table.bin','qingyan.prism.bin','qingyan.reverse.bin']:
   source=core.RIME/'build'/name
   if not source.is_file():raise ValueError('缺少已编译词库，请重新应用配置')
   shutil.copy2(source,root/'build'/name)
  # No custom phrase files or learned data: verify the pinyin engine itself.
  # Copy only the local Lua modules needed by the compiled configuration.
  shutil.copytree(core.ROOT/'runtime',root/'lua')
  result=subprocess.run([str(helper),str(app/'Contents/Frameworks/librime.1.dylib'),tmp,'on' if enabled else 'off'],capture_output=True,text=True,timeout=30)
  try:report=json.loads(result.stdout)
  except (ValueError,TypeError):raise ValueError('输入检查未能完成，请重新应用；若仍失败请重新安装当前版本')
  if not isinstance(report,dict) or type(report.get('ok')) is not bool:raise ValueError('输入检查结果无效')
  report.update(time=time.strftime('%Y-%m-%d %H:%M:%S'),abbreviation=enabled)
  if result.returncode!=0 or not report['ok']:raise ValueError('拼音或简拼检查未通过，请重新应用配置；管理页数据和学习记录仍保留')
  return report

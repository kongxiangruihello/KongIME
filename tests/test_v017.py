import sys,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core,quick,profile_backup,restore_review as review,workflow,library_tools,local_snapshots
class V017Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=core.DATA,core.RIME
  core.DATA=Path(self.tmp.name)/'data';core.RIME=Path(self.tmp.name)/'rime';review.PENDING.clear()
 def tearDown(self):core.DATA,core.RIME=self.old;self.tmp.cleanup()
 def test_running_version_never_assumes_installed_version(self):
  r=workflow.runtime_summary(workflow.VERSION,{'runtimes':[{'version':None,'pid':1}]})
  self.assertEqual(r['running_versions'],[]);self.assertTrue(r['needs_restart'])
  r=workflow.runtime_summary(workflow.VERSION,{'runtimes':[{'version':'0.16.0','pid':2}]})
  self.assertTrue(r['needs_restart']);self.assertEqual(r['running_versions'],['0.16.0'])
  self.assertFalse(workflow.runtime_summary(workflow.VERSION,{'runtimes':[{'version':workflow.VERSION}]})['needs_restart'])
  self.assertIn('无法检测',workflow.runtime_summary(workflow.VERSION,{})['runtime_detail'])
 def changed_backup(self):
  value=profile_backup.snapshot();value['manager']['state']['personal']=[dict(word='轻言',pinyin='qing yan',weight=500,pinned=True)]
  value['manager']['state']['phrases']=[dict(code='yx',text='name@example.com')]
  value['manager']['state']['settings']['show_pinyin']=False
  return value
 def test_preview_is_read_only_and_reports_content(self):
  before=profile_backup.snapshot();p=review.preview({'backup':self.changed_backup()})
  self.assertEqual(profile_backup.snapshot(),before)
  groups={x['label']:x for x in p['categories']}
  self.assertEqual(groups['短语']['added'],1);self.assertEqual(groups['置顶']['added'],1)
  self.assertEqual(groups['个性化设置']['changed'],1)
  result=review.confirm(p['id']);self.assertTrue(result['verified'])
  self.assertFalse(review.last_report()['changed_since'])
 def test_stale_settings_rejected_before_restore(self):
  p=review.preview({'backup':self.changed_backup()});s=core.state();s['settings']['page_size']=7;core.save(s)
  before=profile_backup.snapshot()
  with self.assertRaisesRegex(ValueError,'重新预览'):review.confirm(p['id'])
  self.assertEqual(profile_backup.snapshot(),before)
 def test_stale_quick_order_rejected(self):
  p=review.preview({'backup':self.changed_backup()});quick.change('pin','nihao','你好',core.RIME)
  with self.assertRaisesRegex(ValueError,'重新预览'):review.confirm(p['id'])
  self.assertEqual(quick.read(core.RIME)[0][0]['word'],'你好')
 def test_rollback_also_previewed_and_verified(self):
  before=review.canonical(profile_backup.snapshot());p=review.preview({'backup':self.changed_backup()});review.confirm(p['id'])
  r=review.preview({'source':'rollback'});self.assertTrue(review.confirm(r['id'])['verified'])
  self.assertEqual(review.canonical(profile_backup.snapshot()),before)
 def test_library_uuid_changes_do_not_fake_differences(self):
  library_tools.save({'name':'测试','text':'轻言\tqing yan\t100'})
  value=profile_backup.snapshot();p=review.preview({'backup':value});self.assertEqual(p['changes'],0)
  self.assertTrue(review.confirm(p['id'])['verified'])
 def test_same_count_weight_change_detected(self):
  library_tools.save({'name':'测试','text':'轻言\tqing yan\t100'});value=profile_backup.snapshot()
  next(iter(value['manager']['libraries'].values()))[0]['weight']=800
  p=review.preview({'backup':value});groups={x['label']:x for x in p['categories']}
  self.assertEqual(groups['词库']['changed'],1);self.assertEqual(groups['已启用词条与个人词语']['changed'],1)
  self.assertTrue(review.confirm(p['id'])['verified'])
 def test_expired_invalid_preview_preserves_state(self):
  value=profile_backup.snapshot();bad=copy.deepcopy(value);bad['manager']['state']['settings']['page_size']=99
  with self.assertRaises(ValueError):review.preview({'backup':bad})
  p=review.preview({'backup':value});review.PENDING[p['id']]['time']-=601
  with self.assertRaisesRegex(ValueError,'过期'):review.confirm(p['id'])
  self.assertEqual(value,profile_backup.snapshot())
 def test_snapshot_and_legacy_sources(self):
  snapshot=local_snapshots.create('test');p=review.preview({'source':'snapshot','name':snapshot['name']});self.assertEqual(p['changes'],0)
  quick.change('pin','nihao','你好',core.RIME)
  p=review.preview({'backup':core.backup_value()});review.confirm(p['id'])
  self.assertEqual(quick.read(core.RIME)[0][0]['word'],'你好')

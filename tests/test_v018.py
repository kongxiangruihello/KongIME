import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class InstallerBackupTests(unittest.TestCase):
 def test_upgrade_backs_up_client_on_selected_volume_only(self):
  with tempfile.TemporaryDirectory() as d:
   volume=Path(d)/'Test Volume';app=volume/'Library/Input Methods/Squirrel.app';app.mkdir(parents=True)
   (app/'version').write_text('old client')
   personal=volume/'Users/example/Library/Rime';personal.mkdir(parents=True);(personal/'dictionary').write_text('keep personal data')
   subprocess.run(['/bin/sh',str(ROOT/'branding/installer-scripts/preinstall'),'package','install-location',str(volume)],check=True)
   backups=list((volume/'Library/Application Support/KongIME/backups').glob('*/Squirrel.app/version'))
   self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),'old client')
   self.assertEqual((app/'version').read_text(),'old client');self.assertEqual((personal/'dictionary').read_text(),'keep personal data')
 def test_first_install_needs_no_existing_client(self):
  with tempfile.TemporaryDirectory() as d:
   subprocess.run(['/bin/sh',str(ROOT/'branding/installer-scripts/preinstall'),'package','install-location',d],check=True)
   self.assertEqual(list(Path(d).iterdir()),[])

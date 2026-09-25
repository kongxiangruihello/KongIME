from pathlib import Path
import shutil,subprocess,plistlib,zipfile
import build_installer
root=Path(__file__).resolve().parent
out=root/'release/KongIME-0.25';out.mkdir(parents=True,exist_ok=False)
stage=root/'client/build/payload-v025';stage.mkdir(exist_ok=False)
client=stage/'Squirrel.app'
shutil.copytree(root/'branding/payload/Squirrel.app',client,symlinks=True)
shutil.copy2(root/'client/build/Squirrel',client/'Contents/MacOS/Squirrel')
helper=client/'Contents/Helpers/KongIME设置.app'
(helper/'Contents/MacOS').mkdir(parents=True)
shutil.copy2(root/'client/build/KongIMESettings',helper/'Contents/MacOS/Qingyan')
manager=helper/'Contents/Resources/manager'
manager.mkdir(parents=True)
shutil.copytree(root/'vendor/rime-ice',manager/'vendor/rime-ice',ignore=shutil.ignore_patterns('.git','__pycache__'))
shutil.copytree(root/'licenses',manager/'licenses')
shutil.copy2(root/'sgpu_pinyin.json',manager/'sgpu_pinyin.json')
shutil.copy2(root/'client/build/choose-folder',manager/'choose-folder')
for name in ['app.py','core.py','workflow.py','jobs.py','quick.py','profile_backup.py','cloud_client.py','library_tools.py','personal_data.py','local_snapshots.py','learning.py','restore_review.py','phrase_tools.py','engine_check.py','upgrade_check.py','complete_backup.py']:shutil.copy2(root/name,manager/name)
shutil.copy2(root/'client/build/credential-store',manager/'credential-store')
shutil.copy2(root/'client/build/learning-tool',manager/'learning-tool')
shutil.copy2(root/'client/build/ime-status',manager/'ime-status')
shutil.copy2(root/'client/build/engine-check',manager/'engine-check')
shutil.copy2(root/'branding/rime.pdf',client/'Contents/Resources/rime.pdf')
shutil.copytree(root/'runtime',manager/'runtime')
shutil.copytree(root/'web',manager/'web')
p=helper/'Contents/Info.plist';info={'CFBundleExecutable':'Qingyan','CFBundleIdentifier':'local.qingyan.manager','CFBundlePackageType':'APPL','LSMinimumSystemVersion':'13.0','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'NSHighResolutionCapable':True};info['CFBundleURLTypes']=[{'CFBundleURLName':'KongIME settings','CFBundleURLSchemes':['kongime-settings']}]
info.update(CFBundleShortVersionString='0.25.0',CFBundleVersion='250',CFBundleDisplayName='KongIME设置',CFBundleName='KongIME',LSUIElement=True);p.write_bytes(plistlib.dumps(info))
p=client/'Contents/Info.plist';info=plistlib.loads(p.read_bytes());info['KongIMEVersion']='0.25.0';info['tsInputMethodIconFileKey']='rime.pdf';info['CFBundleVersion']='12500';info['CFBundleShortVersionString']='1.1.2-KongIME.0.25';info.pop('SUFeedURL',None);info['SUEnableAutomaticChecks']=False;p.write_bytes(plistlib.dumps(info))
# This custom client uses manual KongIME updates; upstream updates would remove the integration.
shutil.rmtree(client/'Contents/Frameworks/Sparkle.framework')
subprocess.run(['codesign','--force','--deep','--options','0','--sign','-',str(client)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(client)],check=True)
components=[{'RootRelativeBundlePath':'Squirrel.app','BundleHasStrictIdentifier':True,'BundleIsRelocatable':False,'BundleIsVersionChecked':False,'BundleOverwriteAction':'upgrade'}]
componentFile=root/'client/build/components.plist';componentFile.write_bytes(plistlib.dumps(components))
subprocess.run(['pkgbuild','--root',str(stage),'--install-location','/Library/Input Methods','--identifier','local.kongime.inputmethod','--version','0.25.0','--component-plist',str(componentFile),'--scripts',str(root/'branding/installer-scripts'),str(root/'client/build/KongIME-component.pkg')],check=True)
build_installer.build(root/'client/build/KongIME-component.pkg',out/'安装KongIME.pkg',root/'client/build/installer-v025','0.25.0')
shutil.copy2(root/'README-0.25.md',out/'开始使用.txt')
source=out/'源码';source.mkdir()
for n in ['LearningTool.cpp','EngineCheck.cpp','Launcher.swift','CredentialStore.swift','ChooseFolder.swift','IMEStatus.swift','app.py','core.py','workflow.py','jobs.py','quick.py','profile_backup.py','cloud_client.py','library_tools.py','personal_data.py','local_snapshots.py','learning.py','restore_review.py','phrase_tools.py','engine_check.py','upgrade_check.py','complete_backup.py','sgpu_pinyin.json','build_integrated.py','build_installer.py','build_client.sh','README-0.25.md','VALIDATION-0.25.md']:shutil.copy2(root/n,source/n)
for n in ['web','licenses','tests','runtime','cloud']:shutil.copytree(root/n,source/n,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(root/'client/sources',source/'client/sources')
shutil.copy2(root/'client/LICENSE.txt',source/'client/LICENSE.txt')
shutil.copytree(root/'branding/installer-scripts',source/'branding/installer-scripts')
for name in ['MakeIcon.swift','rime.pdf']:shutil.copy2(root/'branding'/name,source/'branding'/name)
shutil.copytree(root/'client/build/installer-v025',source/'branding/installer')
archive=root.parent/'KongIME-0.25-Mac.zip'
subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(out),str(archive)],check=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert not any(n.endswith('/state.json') for n in z.namelist())
print(archive)

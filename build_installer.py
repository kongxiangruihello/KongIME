"""Build the native, branded product archive from a signed KongIME component."""
from pathlib import Path
from html import escape
import subprocess
import xml.etree.ElementTree as ET

STYLE='''body{font-family:-apple-system,"PingFang SC",sans-serif;font-size:13px;line-height:1.65;color:#263029;background:#fafbf8;margin:22px}h1{font-size:25px;line-height:1.2;margin:10px 0}h2{font-size:15px;color:#526b40;margin:18px 0 6px}p{margin:8px 0}.muted{color:#687069;font-size:11px}.brand{font-size:15px;letter-spacing:1px;color:#526b40}.mark{font-size:26px;font-weight:700;margin-right:10px}.note{padding:10px 14px;background:#edf1e7;border-left:3px solid #6c8056}li{margin:6px 0}@media(prefers-color-scheme:dark){body{color:#e7eae2;background:#20251f}.brand,h2{color:#bccba9}.muted{color:#adb6a8}.note{background:#2e3829;border-color:#a9bd8d}}'''

def page(title,body,version):
 return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>'+escape(title)+'</title><style>'+STYLE+'</style></head><body><div class="brand"><span class="mark">K</span> KongIME ---- 自由输入，专注表达。</div><h1>'+escape(title)+'</h1>'+body+'<p class="muted">KongIME '+escape(version)+' · 孔祥瑞</p></body></html>'

def resources(folder,version):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 bodies={
 'welcome.html':('欢迎使用 KongIME','<p>欢迎安装 <b>KongIME '+escape(version)+'</b>，你的简洁全拼输入法。</p><p>以雾凇词库与 Rime 为基础，支持搜狗词库导入、个人短语、候选排序和个性化设置。</p><h2>这次更新</h2><p>候选窗口避让拼音输入行，支持调整窗口间距；加入全新的品牌标语。</p><div class="note">适用于 Apple Silicon Mac · macOS 13 及以上<br>安装后请保存工作，注销并重新登录。</div>'),
 'readme.html':('升级之前，放心准备。','<h2>已有 KongIME</h2><p>本次将系统客户端更新至 <b>'+escape(version)+'</b>。安装前可在旧版“设置 → 版本状态”查看当前版本，并使用“备份全部配置”另存一份。</p><h2>个人数据会保留</h2><p>安装程序只更新客户端，不清空个人词库、短语、配置或 Rime 学习记录。旧客户端会先复制到本机备份目录；这份程序备份不能代替个人数据备份。</p><p>学习词频需在“备份与恢复”中单独备份；普通配置备份不包含它。</p><h2>首次安装</h2><p>安装完成后在系统键盘设置中添加 KongIME，再导入词库并应用配置。</p><p class="muted">本包需要管理员授权。客户端为本地签名开发构建，安装包尚未使用 Developer ID 签名或 Apple 公证。</p>'),
 'conclusion.html':('再走三步，开始输入。','<p>请以安装器上方显示的安装结果为准。安装成功后：</p><ol><li><b>保存工作，注销并重新登录。</b><br>确保新版输入法启动，更新菜单栏图标缓存。</li><li><b>切换到 KongIME。</b><br>首次使用：系统设置 → 键盘 → 文本输入 → 编辑 → ＋，找到并添加 KongIME。</li><li><b>打开输入法菜单“设置…”并应用配置。</b><br>刷新版本状态，确认设置、已安装、正在运行均为 '+escape(version)+'，然后输入 nihao 试打。</li></ol><div class="note">字号、拼音显示、模糊音与候选样式：<br>设置 → 个性化</div><p class="muted">安装器不会自动注销，也不会自动覆盖你的输入习惯。</p>')}
 for filename,(title,body) in bodies.items():
  if filename=='welcome.html':
   html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>KongIME</title></head><body style="font-family:-apple-system,PingFang SC,sans-serif;margin:32px"><h1 style="font-size:30px;line-height:1.5">KongIME ---- 自由输入，专注表达。</h1><p style="font-size:15px">版本：'+escape(version)+'</p><p style="font-size:15px">开发者：孔祥瑞</p></body></html>'
  else:html=page(title,body,version)
  (folder/filename).write_text(html)
 return folder

def distribution(path,version,component='KongIME-component.pkg'):
 root=ET.Element('installer-gui-script',{'minSpecVersion':'2'})
 ET.SubElement(root,'title').text='KongIME '+version
 ET.SubElement(root,'options',{'customize':'never','require-scripts':'false','hostArchitectures':'arm64'})
 ET.SubElement(root,'domains',{'enable_anywhere':'false','enable_currentUserHome':'false','enable_localSystem':'true'})
 for tag in ['welcome','readme','conclusion']:ET.SubElement(root,tag,{'file':tag+'.html','mime-type':'text/html'})
 check=ET.SubElement(root,'volume-check');allowed=ET.SubElement(check,'allowed-os-versions');ET.SubElement(allowed,'os-version',{'min':'13.0'})
 outline=ET.SubElement(root,'choices-outline');ET.SubElement(outline,'line',{'choice':'kongime'})
 choice=ET.SubElement(root,'choice',{'id':'kongime','title':'KongIME 全拼输入法','description':'系统输入法与内置设置；个人词库和配置保留。','visible':'false','selected':'true'})
 ET.SubElement(choice,'pkg-ref',{'id':'local.kongime.inputmethod'})
 ET.SubElement(root,'pkg-ref',{'id':'local.kongime.inputmethod','version':version,'onConclusion':'None'}).text=component
 ET.indent(root);ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

def build(component,output,work,version):
 work=Path(work);work.mkdir(parents=True,exist_ok=True)
 res=resources(work/'Resources',version);dist=work/'Distribution.xml';distribution(dist,version,Path(component).name)
 subprocess.run(['productbuild','--distribution',str(dist),'--resources',str(res),'--package-path',str(Path(component).parent),str(output)],check=True)

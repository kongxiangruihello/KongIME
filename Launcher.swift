import Cocoa
import WebKit

class App: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKDownloadDelegate, WKScriptMessageHandler, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process!
    var closeCheckPending = false
    var closingApproved = false
    var terminationPending = false
    var requestedPage = "libraries"
    var pendingPhrase: [String:String]?
    var phrasePageReady = false
    var pendingDownloads: [WKDownload: URL] = [:]
    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let item = NSMenuItem(); menu.addItem(item)
        let submenu = NSMenu(); submenu.addItem(withTitle:"退出 KongIME", action:#selector(NSApplication.terminate(_:)), keyEquivalent:"q");item.submenu=submenu
        let editItem=NSMenuItem();menu.addItem(editItem);let edit=NSMenu(title:"编辑");editItem.submenu=edit
        edit.addItem(withTitle:"剪切",action:#selector(NSText.cut(_:)),keyEquivalent:"x")
        edit.addItem(withTitle:"复制",action:#selector(NSText.copy(_:)),keyEquivalent:"c")
        edit.addItem(withTitle:"粘贴",action:#selector(NSText.paste(_:)),keyEquivalent:"v")
        edit.addItem(withTitle:"全选",action:#selector(NSText.selectAll(_:)),keyEquivalent:"a")
        NSApp.mainMenu=menu
        window = NSWindow(contentRect:NSRect(x:0,y:0,width:860,height:660),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.delegate = self
        window.title="KongIME · 设置";window.minSize=NSSize(width:720,height:540);window.center()
        let config=WKWebViewConfiguration();config.userContentController.add(self,name:"chooseDirectory");config.userContentController.add(self,name:"closeSettings");config.userContentController.add(self,name:"pageChanged");config.userContentController.add(self,name:"closeDecision");config.userContentController.add(self,name:"phraseReady")
        web=WKWebView(frame:window.contentView!.bounds,configuration:config);web.autoresizingMask=[.width,.height];web.uiDelegate=self;web.navigationDelegate=self
        window.contentView=web;window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        let resources=Bundle.main.resourceURL!.appendingPathComponent("manager")
        server=Process();server.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
        server.arguments=["-B",resources.appendingPathComponent("app.py").path,"--no-open","--port","0"]
        var env=ProcessInfo.processInfo.environment
        env["KONGIME_LEGACY_DIR"]=Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("用户数据").path
        env["QINGYAN_DATA"]=env["QINGYAN_DATA"] ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/KongIME/manager").path
        server.environment=env
        let pipe=Pipe();server.standardOutput=pipe;server.standardError=FileHandle.standardError
        do {
            try server.run()
            DispatchQueue.global().async {
                let data=pipe.fileHandleForReading.availableData
                let text=String(data:data,encoding:.utf8)?.trimmingCharacters(in:.whitespacesAndNewlines) ?? ""
                DispatchQueue.main.async {
                    if let url=URL(string:text),url.host=="127.0.0.1" { var parts=URLComponents(url:url,resolvingAgainstBaseURL:false)!;parts.fragment=self.requestedPage;self.web.load(URLRequest(url:parts.url!)) }
                    else { self.failure("设置未能启动。请确认系统已安装 Python 3，或重新安装 KongIME。") }
                }
            }
        } catch { failure("启动失败：\(error.localizedDescription)") }
    }
    func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage){
        guard ["chooseDirectory", "closeSettings", "pageChanged", "closeDecision", "phraseReady"].contains(message.name),message.frameInfo.isMainFrame,
              message.frameInfo.securityOrigin.host == "127.0.0.1" else {return}
        if message.name == "phraseReady" { phrasePageReady = true; deliverPhrase(); return }
        if message.name == "closeDecision" {
            closeCheckPending = false
            let approved = message.body as? Bool == true
            closingApproved = approved
            if terminationPending { terminationPending = false; NSApp.reply(toApplicationShouldTerminate: approved) }
            else if approved { window.close() }
            return
        }
        if message.name == "pageChanged" {
            if let page=message.body as? String, let title=["libraries":"设置","words":"我的词语","personalization":"设置","settings":"安装与备份","review":"特殊词条","history":"最近修改","sync":"备份与恢复"][page] {window.title="KongIME · " + title}
            return
        }
        if message.name == "closeSettings" { NSApp.terminate(nil); return }
        let panel=NSOpenPanel();panel.title="选择旧版数据文件夹";panel.prompt="检查此文件夹"
        panel.canChooseFiles=false;panel.canChooseDirectories=true;panel.allowsMultipleSelection=false
        panel.beginSheetModal(for:window){result in
            let selected:Any = result == .OK ? (panel.url?.path as Any? ?? NSNull()) : NSNull()
            if let data=try? JSONSerialization.data(withJSONObject:[selected]),let json=String(data:data,encoding:.utf8){
                self.web.evaluateJavaScript("window.onDirectorySelected(\(json)[0])",completionHandler:nil)
            }
        }
    }
    func failure(_ text:String){let alert=NSAlert();alert.messageText=text;alert.runModal();NSApp.terminate(nil)}
    func application(_ application: NSApplication, open urls: [URL]) {
        if let url = urls.first, let payload = CandidatePhraseLink.payload(url) {
            pendingPhrase = payload; requestedPage = "words"; deliverPhrase()
            window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return
        }
        guard let url=urls.first, url.scheme == "kongime-settings", let page=url.host, ["settings","personalization","libraries"].contains(page) else {return}
        requestedPage=page
        if web?.url != nil { web.evaluateJavaScript("navigatePage('" + page + "')", completionHandler:nil) }
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps:true)
    }
    func deliverPhrase() {
        guard phrasePageReady, let value = pendingPhrase, let data = try? JSONSerialization.data(withJSONObject: value), let json = String(data: data, encoding: .utf8) else { return }
        pendingPhrase = nil
        web.evaluateJavaScript("window.openCandidatePhrase(" + json + ")", completionHandler: nil)
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        return true
    }
    func requestCloseCheck() {
        guard !closeCheckPending else { return }
        closeCheckPending = true
        web.evaluateJavaScript("typeof window.requestSettingsClose === 'function' ? (window.requestSettingsClose(), true) : false") { result, error in
            if error != nil || result as? Bool != true {
                self.closeCheckPending = false
                let alert = NSAlert(); alert.messageText = "设置页面未响应"; alert.informativeText = "关闭可能丢失未保存的修改。"; alert.addButton(withTitle: "继续编辑"); alert.addButton(withTitle: "仍然关闭")
                alert.beginSheetModal(for: self.window) { response in
                    let approved = response == .alertSecondButtonReturn
                    self.closingApproved = approved
                    if self.terminationPending { self.terminationPending = false; NSApp.reply(toApplicationShouldTerminate: approved) }
                    else if approved { self.window.close() }
                }
            }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if closingApproved { return true }
        requestCloseCheck(); return false
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if closingApproved || web == nil { return .terminateNow }
        terminationPending = true; requestCloseCheck(); return .terminateLater
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {true}
    func applicationWillTerminate(_ notification:Notification){if server?.isRunning == true {server.terminate()}}
    func webView(_ webView: WKWebView, decidePolicyFor action:WKNavigationAction, decisionHandler:@escaping(WKNavigationActionPolicy)->Void){
        if let url=action.request.url,url.host != "127.0.0.1" {
            if url.scheme == "https" {NSWorkspace.shared.open(url)}
            decisionHandler(.cancel);return
        }
        decisionHandler(action.shouldPerformDownload ? .download : .allow)
    }
    func webView(_ webView:WKWebView,decidePolicyFor response:WKNavigationResponse,decisionHandler:@escaping(WKNavigationResponsePolicy)->Void){
        if let r=response.response as? HTTPURLResponse, r.value(forHTTPHeaderField:"Content-Disposition")?.contains("attachment") == true {decisionHandler(.download)}else{decisionHandler(.allow)}
    }
    func webView(_ webView:WKWebView,navigationAction:WKNavigationAction,didBecome download:WKDownload){download.delegate=self}
    func webView(_ webView:WKWebView,navigationResponse:WKNavigationResponse,didBecome download:WKDownload){download.delegate=self}
    func download(_ download:WKDownload,decideDestinationUsing response:URLResponse,suggestedFilename:String,completionHandler:@escaping(URL?)->Void){
        let panel=NSSavePanel();panel.nameFieldStringValue=suggestedFilename
        panel.beginSheetModal(for:window){result in completionHandler(result == .OK ? panel.url : nil)}
    }
    func webView(_ webView:WKWebView,runOpenPanelWith parameters:WKOpenPanelParameters,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping([URL]?)->Void){
        let panel=NSOpenPanel();panel.allowsMultipleSelection=parameters.allowsMultipleSelection;panel.canChooseDirectories=false
        panel.beginSheetModal(for:window){result in completionHandler(result == .OK ? panel.urls : nil)}
    }
    func webView(_ webView:WKWebView,runJavaScriptConfirmPanelWithMessage message:String,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping(Bool)->Void){
        let alert=NSAlert();alert.messageText=message;alert.addButton(withTitle:"确认");alert.addButton(withTitle:"取消")
        alert.beginSheetModal(for:window){response in completionHandler(response == .alertFirstButtonReturn)}
    }
}
@main struct SettingsMain {
    static func main() {
        let app=NSApplication.shared
        let delegate=App();app.delegate=delegate;app.setActivationPolicy(.accessory);app.run()
    }
}

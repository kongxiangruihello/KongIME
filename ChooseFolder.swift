import Cocoa
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.activate(ignoringOtherApps: true)
let panel = NSOpenPanel()
panel.title = "选择旧版 KongIME 数据文件夹"
panel.message = "选择“用户数据”文件夹，或包含它的旧版应用目录。"
panel.prompt = "检查此文件夹"
panel.canChooseDirectories = true
panel.canChooseFiles = false
panel.allowsMultipleSelection = false
if panel.runModal() == .OK, let url = panel.url {
    print(url.path)
} else { exit(2) }

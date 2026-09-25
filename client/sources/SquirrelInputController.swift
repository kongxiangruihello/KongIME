//
//  SquirrelInputController.swift
//  Squirrel
//
//  Created by Leo Liu on 5/7/24.
//

import InputMethodKit

final class SquirrelInputController: IMKInputController {
  private static let keyRollOver = 50
  private static var unknownAppCnt: UInt = 0

  private weak var client: IMKTextInput?
  private let rimeAPI: RimeApi_stdbool = rime_get_api_stdbool().pointee
  private var preedit: String = ""
  private var selRange: NSRange = .empty
  private var caretPos: Int = 0
  private var lastModifiers: NSEvent.ModifierFlags = .init()
  private var session: RimeSessionId = 0
  private var schemaId: String = ""
  private var inlinePreedit = false
  private var inlineCandidate = false
  // for chord-typing
  private var chordKeyCodes: [UInt32] = .init(repeating: 0, count: SquirrelInputController.keyRollOver)
  private var chordModifiers: [UInt32] = .init(repeating: 0, count: SquirrelInputController.keyRollOver)
  private var chordKeyCount: Int = 0
  private var chordTimer: Timer?
  private var chordDuration: TimeInterval = 0
  private var currentApp: String = ""
  private var expandedCandidates = false
  private var expansionInput = ""
  private var displayedCandidateCount = 0
  private var displayedCandidateOffset = 0
  private var hasExpansionControl = false
  var expansionAvailable: Bool { hasExpansionControl }
  var expansionIsOpen: Bool { expandedCandidates }
  @discardableResult func toggleExpansion() -> Bool {
    guard hasExpansionControl else { return false }
    expandedCandidates.toggle(); rimeUpdate(); return true
  }


  var expansionShortcutLabel: String {
    let key=NSApp.squirrelAppDelegate.config?.getString("kongime/expand_key") ?? "Tab"
    return ["Control+Tab":"Control＋Tab","Control+grave":"Control＋`","Control+p":"Control＋P","Control+o":"Control＋O","none":"快捷键已关闭"][key] ?? key
  }
  private func matchesShortcut(_ event:NSEvent,name:String)->Bool {
    let choices:[String:(UInt16,NSEvent.ModifierFlags)]=["Tab":(48,[]),"Control+Tab":(48,.control),"Control+grave":(50,.control),"Control+p":(35,.control),"Control+o":(31,.control)]
    guard let (key,flags)=choices[name] else {return false}
    return event.keyCode==key && event.modifierFlags.intersection([.command,.option,.control,.shift])==flags
  }
  // swiftlint:disable:next cyclomatic_complexity
  override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
    guard let event = event else { return false }
    let modifiers = event.modifierFlags
    let changes = lastModifiers.symmetricDifference(modifiers)

    // Return true to indicate the the key input was received and dealt with.
    // Key processing will not continue in that case.  In other words the
    // system will not deliver a key down event to the application.
    // Returning false means the original key down will be passed on to the client.
    var handled = false

    if session == 0 || !rimeAPI.find_session(session) {
      createSession()
      if session == 0 {
        return false
      }
    }

    self.client ?= sender as? IMKTextInput
    if event.type == .keyDown && displayedCandidateCount > 0 {
      if event.keyCode == 36 && event.modifierFlags.intersection([.command,.option,.control,.shift]) == .control, NSApp.squirrelAppDelegate.panel?.toggleCandidateDetail() == true { return true }
      let config=NSApp.squirrelAppDelegate.config
      if matchesShortcut(event, name:config?.getString("kongime/expand_key") ?? "Tab"), hasExpansionControl {return toggleExpansion()}
      if matchesShortcut(event, name:config?.getString("kongime/pin_key") ?? "Control+p") {
        var context=RimeContext_stdbool.rimeStructInit()
        if rimeAPI.get_context(session,&context) {
          let index=Int(context.menu.highlighted_candidate_index)
          if index>=0 && index<Int(context.menu.num_candidates), quickReorderingAvailable(candidateIndex:index), let value=context.menu.candidates?[index].text, let code=quickInput(candidateIndex:index) {
            let word=String(cString:value); _ = rimeAPI.free_context(&context)
            adjustQuickCandidate(word:word,code:code,action:"pin");return true
          }
          _ = rimeAPI.free_context(&context)
        }
      }
    }
    if let app = client?.bundleIdentifier(), currentApp != app {
      rememberLanguage()
      currentApp = app
      updateAppOptions()
    }

    switch event.type {
    case .flagsChanged:
      if lastModifiers == modifiers {
        handled = true
        break
      }
      // print("[DEBUG] FLAGSCHANGED client: \(sender ?? "nil"), modifiers: \(modifiers)")
      var rimeModifiers: UInt32 = SquirrelKeycode.osxModifiersToRime(modifiers: modifiers)
      // For flags-changed event, keyCode is available since macOS 10.17
      // (#715)
      let rimeKeycode: UInt32 = SquirrelKeycode.osxKeycodeToRime(keycode: event.keyCode, keychar: nil, shift: false, caps: false)

      if changes.contains(.capsLock) {
        // NOTE: rime assumes XK_Caps_Lock to be sent before modifier changes,
        // while NSFlagsChanged event has the flag changed already.
        // so it is necessary to revert kLockMask.
        rimeModifiers ^= kLockMask.rawValue
        _ = processKey(rimeKeycode, modifiers: rimeModifiers)
      }

      // Need to process release before modifier down. Because
      // sometimes release event is delayed to next modifier keydown.
      var buffer = [(keycode: UInt32, modifier: UInt32)]()
      for flag in [NSEvent.ModifierFlags.shift, .control, .option, .command] where changes.contains(flag) {
        if modifiers.contains(flag) { // New modifier
          buffer.append((keycode: rimeKeycode, modifier: rimeModifiers))
        } else { // Release
          buffer.insert((keycode: rimeKeycode, modifier: rimeModifiers | kReleaseMask.rawValue), at: 0)
        }
      }
      for (keycode, modifier) in buffer {
        _ = processKey(keycode, modifiers: modifier)
      }

      lastModifiers = modifiers
      rimeUpdate()

    case .keyDown:
      // ignore Command+X hotkeys.
      if modifiers.contains(.command) {
        break
      }

      if handlePairedPunctuation(event) { return true }
      let keyCode = event.keyCode
      var keyChars = event.charactersIgnoringModifiers
      let capitalModifiers = modifiers.isSubset(of: [.shift, .capsLock])
      if let code = keyChars?.first,
         (capitalModifiers && !code.isLetter) || (!capitalModifiers && !code.isASCII) {
        keyChars = event.characters
      }
      // print("[DEBUG] KEYDOWN client: \(sender ?? "nil"), modifiers: \(modifiers), keyCode: \(keyCode), keyChars: [\(keyChars ?? "empty")]")

      // translate osx keyevents to rime keyevents
      if let char = keyChars?.first {
        let rimeKeycode = SquirrelKeycode.osxKeycodeToRime(keycode: keyCode, keychar: char,
                                                           shift: modifiers.contains(.shift),
                                                           caps: modifiers.contains(.capsLock))
        if rimeKeycode != 0 {
          let rimeModifiers = SquirrelKeycode.osxModifiersToRime(modifiers: modifiers)
          handled = processKey(rimeKeycode, modifiers: rimeModifiers)
          rimeUpdate()
        }
      }

    default:
      break
    }

    return handled
  }

  private func handlePairedPunctuation(_ event: NSEvent) -> Bool {
    guard event.modifierFlags.intersection([.command, .control, .option]).isEmpty,
          let client, preedit.isEmpty,
          rimeAPI.get_input(session).map({ String(cString: $0).isEmpty }) ?? true else { return false }
    let english = rimeAPI.get_option(session, "ascii_mode")
    guard NSApp.squirrelAppDelegate.config?.getBool(english ? "kongime/pair_english" : "kongime/pair_chinese") == true,
          client.supportsProperty(TSMDocumentPropertyTag(kTSMDocumentSupportDocumentAccessPropertyTag)) else { return false }
    let selection = client.selectedRange()
    guard selection.location != NSNotFound, selection.length == 0 else { return false }
    let ascii = english || rimeAPI.get_option(session, "ascii_punct")
    func text(_ range: NSRange) -> String? {
      var actual = NSRange(location: NSNotFound, length: 0)
      let value = client.string(from: range, actualRange: &actual)
      return actual == range ? value : nil
    }
    if event.keyCode == 51, selection.location > 0,
       let around = text(NSRange(location: selection.location - 1, length: 2)),
       PunctuationPairs.isEmptyPair(around, ascii: ascii) {
      client.insertText("", replacementRange: NSRange(location: selection.location - 1, length: 2))
      return true
    }
    let previous = selection.location > 0 ? text(NSRange(location: selection.location - 1, length: 1)) ?? "" : ""
    guard let pair = PunctuationPairs.pair(for: event.characters ?? "", ascii: ascii, previous: previous) else { return false }
    PunctuationPairs.insert(pair, at: selection.location, replace: { client.insertText($0, replacementRange: $1) }, locate: {
      client.setMarkedText("", selectionRange: NSRange(location: 0, length: 0), replacementRange: $0)
    })
    return true
  }

  func quickInput(candidateIndex:Int) -> String? {
    guard candidateIndex >= 0 && candidateIndex < displayedCandidateCount else {return nil}
    guard let value=rimeAPI.get_input(session) else {return nil}
    let code=String(cString:value)
    guard !code.isEmpty,code.count<=80,code.allSatisfy({"abcdefghijklmnopqrstuvwxyz' ".contains($0)}) else {return nil}
    return code
  }
  func quickReorderingAvailable(candidateIndex: Int) -> Bool {
    candidateIndex >= 0 && candidateIndex + displayedCandidateOffset < 200
  }
  func hasCandidatePhrase(word: String, code: String, comment: String) -> Bool {
    let path = ProcessInfo.processInfo.environment["QINGYAN_DATA"] ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/KongIME/manager").path
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path).appendingPathComponent("state.json")), let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let rows = state["phrases"] as? [[String: Any]] else { return false }
    return CandidatePhraseLink.existing(word: word, code: code, comment: comment, rows: rows)
  }
  func openCandidatePhrase(word: String, code: String, comment: String, action: String) {
    guard let url = CandidatePhraseLink.url(word: word, code: code, comment: comment, action: action), CandidatePhraseLink.payload(url) != nil else { return }
    // Finish the uncommitted composition before focus changes; deactivateServer normally commits raw pinyin.
    rimeAPI.clear_composition(session)
    rimeUpdate()
    NSApp.squirrelAppDelegate.openKongIMEManager(request: url)
  }

  func adjustQuickCandidate(word:String,code:String,action:String) {
    let script=Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/KongIME设置.app/Contents/Resources/manager/quick.py")
    let process=Process();process.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
    process.arguments=["-B",script.path,action,code,word]
    let errors=Pipe();process.standardError=errors;process.standardOutput=FileHandle.nullDevice
    process.terminationHandler={ p in
      DispatchQueue.main.async {
        if p.terminationStatus==0 {
          NSApp.squirrelAppDelegate.panel?.updateStatus(long:action == "block" ? "已屏蔽，下次输入生效" : "排序已保存，下次输入生效",short:"已保存")
        } else {
          let alert=NSAlert();alert.messageText="快捷调整未保存";alert.informativeText=String(data:errors.fileHandleForReading.availableData,encoding:.utf8) ?? "请重试";alert.runModal()
        }
      }
    }
    do {try process.run()} catch {let alert=NSAlert();alert.messageText="无法保存快捷调整";alert.informativeText=error.localizedDescription;alert.runModal()}
  }

  func selectCandidate(_ index: Int) -> Bool {
    guard index >= 0 && index < displayedCandidateCount else {return false}
    let success = rimeAPI.select_candidate(session, displayedCandidateOffset + index)
    if success {
      rimeUpdate()
    }
    return success
  }

  // swiftlint:disable:next identifier_name
  func page(up: Bool) -> Bool {
    var handled = false
    handled = rimeAPI.change_page(session, up)
    if handled {
      rimeUpdate()
    }
    return handled
  }

  func moveCaret(forward: Bool) -> Bool {
    let currentCaretPos = rimeAPI.get_caret_pos(session)
    guard let input = rimeAPI.get_input(session) else { return false }
    if forward {
      if currentCaretPos <= 0 {
        return false
      }
      rimeAPI.set_caret_pos(session, currentCaretPos - 1)
    } else {
      let inputStr = String(cString: input)
      if currentCaretPos >= inputStr.utf8.count {
        return false
      }
      rimeAPI.set_caret_pos(session, currentCaretPos + 1)
    }
    rimeUpdate()
    return true
  }

  override func recognizedEvents(_ sender: Any!) -> Int {
    // print("[DEBUG] recognizedEvents:")
    return Int(NSEvent.EventTypeMask.Element(arrayLiteral: .keyDown, .flagsChanged).rawValue)
  }

  override func activateServer(_ sender: Any!) {
    self.client ?= sender as? IMKTextInput
    if session == 0 || !rimeAPI.find_session(session) { createSession() }
    if let app = client?.bundleIdentifier(), currentApp != app {
      rememberLanguage(); currentApp = app; updateAppOptions()
    } else { restoreRememberedLanguage() }
    // print("[DEBUG] activateServer:")
    var keyboardLayout = NSApp.squirrelAppDelegate.config?.getString("keyboard_layout") ?? ""
    if keyboardLayout == "last" || keyboardLayout == "" {
      keyboardLayout = ""
    } else if keyboardLayout == "default" {
      keyboardLayout = "com.apple.keylayout.ABC"
    } else if !keyboardLayout.hasPrefix("com.apple.keylayout.") {
      keyboardLayout = "com.apple.keylayout.\(keyboardLayout)"
    }
    if keyboardLayout != "" {
      client?.overrideKeyboard(withKeyboardNamed: keyboardLayout)
    }
    preedit = ""
    if session != 0, NSApp.squirrelAppDelegate.config?.getBool("kongime/language_hint") ?? true {
      let label = rimeAPI.get_option(session, "ascii_mode") ? "EN" : "中"
      NSApp.squirrelAppDelegate.panel?.updateStatus(long: label, short: label)
      rimeUpdate()
    }
  }

  override init!(server: IMKServer!, delegate: Any!, client: Any!) {
    self.client = client as? IMKTextInput
    // print("[DEBUG] initWithServer: \(server ?? .init()) delegate: \(delegate ?? "nil") client:\(client ?? "nil")")
    super.init(server: server, delegate: delegate, client: client)
    createSession()
  }

  override func deactivateServer(_ sender: Any!) {
    // print("[DEBUG] deactivateServer: \(sender ?? "nil")")
    rememberLanguage()
    hidePalettes()
    commitComposition(sender)
    client = nil
  }

  override func hidePalettes() {
    NSApp.squirrelAppDelegate.panel?.hide()
    super.hidePalettes()
  }

  /*!
   @method
   @abstract   Called when a user action was taken that ends an input session.
   Typically triggered by the user selecting a new input method
   or keyboard layout.
   @discussion When this method is called your controller should send the
   current input buffer to the client via a call to
   insertText:replacementRange:.  Additionally, this is the time
   to clean up if that is necessary.
   */
  override func commitComposition(_ sender: Any!) {
    self.client ?= sender as? IMKTextInput
    // print("[DEBUG] commitComposition: \(sender ?? "nil")")
    //  commit raw input
    if session != 0 {
      if let input = rimeAPI.get_input(session) {
        commit(string: String(cString: input))
        rimeAPI.clear_composition(session)
      }
    }
  }

  override func menu() -> NSMenu! {
    let deploy = NSMenuItem(title: NSLocalizedString("Deploy", comment: "Menu item"), action: #selector(deploy), keyEquivalent: "`")
    deploy.target = self
    deploy.keyEquivalentModifierMask = [.control, .option]
    let sync = NSMenuItem(title: NSLocalizedString("Sync user data", comment: "Menu item"), action: #selector(syncUserData), keyEquivalent: "")
    sync.target = self
    let logDir = NSMenuItem(title: NSLocalizedString("Logs...", comment: "Menu item"), action: #selector(openLogFolder), keyEquivalent: "")
    logDir.target = self
    let wiki = NSMenuItem(title: NSLocalizedString("Rime Wiki...", comment: "Menu item"), action: #selector(openWiki), keyEquivalent: "")
    wiki.target = self


    let menu = NSMenu()
    let manager = NSMenuItem(title: "设置…", action: #selector(openKongIMEManager), keyEquivalent: "")
    manager.target = self
    menu.addItem(manager)
    menu.addItem(.separator())
    menu.addItem(deploy)
    menu.addItem(sync)
    menu.addItem(logDir)
    menu.addItem(wiki)
    menu.addItem(.separator())
    let version = Bundle.main.object(forInfoDictionaryKey: "KongIMEVersion") as? String ?? "0.17.0"
    let versionItem = NSMenuItem(title: "版本：" + version, action: #selector(showKongIMEVersion), keyEquivalent: "")
    versionItem.target = self
    let developerItem = NSMenuItem(title: "开发者：孔祥瑞", action: #selector(showKongIMEDeveloper), keyEquivalent: "")
    developerItem.target = self
    menu.addItem(versionItem)
    menu.addItem(developerItem)

    return menu
  }

  @objc func showKongIMEVersion() {
    let alert = NSAlert()
    alert.messageText = "KongIME " + (Bundle.main.object(forInfoDictionaryKey: "KongIMEVersion") as? String ?? "0.17.0")
    alert.informativeText = "KongIME 全拼\n基于 Rime 与雾凇拼音"
    alert.runModal()
  }

  @objc func showKongIMEDeveloper() {
    let alert = NSAlert()
    alert.messageText = "开发者：孔祥瑞"
    alert.informativeText = "KongIME · 让文字，顺着你的习惯。"
    alert.runModal()
  }

  @objc func deploy() {
    NSApp.squirrelAppDelegate.deploy()
  }

  @objc func syncUserData() {
    NSApp.squirrelAppDelegate.syncUserData()
  }

  @objc func openLogFolder() {
    NSApp.squirrelAppDelegate.openLogFolder()
  }

  @objc func openGraphicalSettings() {
    NSApp.squirrelAppDelegate.openKongIMEManager(page: "libraries")
  }

  @objc func openRimeFolder() {
    NSApp.squirrelAppDelegate.openRimeFolder()
  }

  @objc func openKongIMEManager() {
    NSApp.squirrelAppDelegate.openKongIMEManager()
  }

  @objc func openWiki() {
    NSApp.squirrelAppDelegate.openWiki()
  }

  deinit {
    destroySession()
  }
}

private extension SquirrelInputController {

  func onChordTimer(_: Timer) {
    // chord release triggered by timer
    var processedKeys = false
    if chordKeyCount > 0 && session != 0 {
      // simulate key-ups
      for i in 0..<chordKeyCount {
        let handled = rimeAPI.process_key(session, Int32(chordKeyCodes[i]), Int32(chordModifiers[i] | kReleaseMask.rawValue))
        if handled {
          processedKeys = true
        }
      }
    }
    clearChord()
    if processedKeys {
      rimeUpdate()
    }
  }

  func updateChord(keycode: UInt32, modifiers: UInt32) {
    // print("[DEBUG] update chord: {\(chordKeyCodes)} << \(keycode)")
    for i in 0..<chordKeyCount where chordKeyCodes[i] == keycode {
      return
    }
    if chordKeyCount >= Self.keyRollOver {
      // you are cheating. only one human typist (fingers <= 10) is supported.
      return
    }
    chordKeyCodes[chordKeyCount] = keycode
    chordModifiers[chordKeyCount] = modifiers
    chordKeyCount += 1
    // reset timer
    if let timer = chordTimer, timer.isValid {
      timer.invalidate()
    }
    chordDuration = 0.1
    if let duration = NSApp.squirrelAppDelegate.config?.getDouble("chord_duration"), duration > 0 {
      chordDuration = duration
    }
    chordTimer = Timer.scheduledTimer(withTimeInterval: chordDuration, repeats: false, block: onChordTimer)
  }

  func clearChord() {
    chordKeyCount = 0
    if let timer = chordTimer {
      if timer.isValid {
        timer.invalidate()
      }
      chordTimer = nil
    }
  }

  func createSession() {
    let app = client?.bundleIdentifier() ?? {
      SquirrelInputController.unknownAppCnt &+= 1
      return "UnknownApp\(SquirrelInputController.unknownAppCnt)"
    }()
    print("createSession: \(app)")
    currentApp = app
    session = rimeAPI.create_session()
    schemaId = ""

    if session != 0 {
      updateAppOptions()
    }
  }

  func rememberLanguage() {
    guard session != 0, rimeAPI.find_session(session) else { return }
    let enabled = NSApp.squirrelAppDelegate.config?.getBool("kongime/remember_apps/" + currentApp) == true
    AppLanguageMemory.shared.record(currentApp, ascii: rimeAPI.get_option(session, "ascii_mode"), enabled: enabled)
  }

  func restoreRememberedLanguage() {
    guard session != 0, NSApp.squirrelAppDelegate.config?.getBool("kongime/remember_apps/" + currentApp) == true else { return }
    rimeAPI.set_option(session, "ascii_mode", AppLanguageMemory.shared.remembered(currentApp) ?? false)
  }

  func updateAppOptions() {
    if currentApp == "" {
      return
    }
    if let appOptions = NSApp.squirrelAppDelegate.config?.getAppOptions(currentApp) {
      for (key, value) in appOptions {
        print("set app option: \(key) = \(value)")
        rimeAPI.set_option(session, key, value)
      }
    }
    restoreRememberedLanguage()
  }

  func destroySession() {
    rememberLanguage()
    // print("[DEBUG] destroySession:")
    if session != 0 {
      _ = rimeAPI.destroy_session(session)
      session = 0
    }
    clearChord()
  }

  func processKey(_ rimeKeycode: UInt32, modifiers rimeModifiers: UInt32) -> Bool {
    // TODO add special key event preprocessing here

    // with linear candidate list, arrow keys may behave differently.
    if let panel = NSApp.squirrelAppDelegate.panel {
      if panel.linear != rimeAPI.get_option(session, "_linear") {
        rimeAPI.set_option(session, "_linear", panel.linear)
      }
      // with vertical text, arrow keys may behave differently.
      if panel.vertical != rimeAPI.get_option(session, "_vertical") {
        rimeAPI.set_option(session, "_vertical", panel.vertical)
      }
    }

    let handled = rimeAPI.process_key(session, Int32(rimeKeycode), Int32(rimeModifiers))
    // print("[DEBUG] rime_keycode: \(rimeKeycode), rime_modifiers: \(rimeModifiers), handled = \(handled)")

    // TODO add special key event postprocessing here

    if !handled {
      let isVimBackInCommandMode = rimeKeycode == XK_Escape || ((rimeModifiers & kControlMask.rawValue != 0) && (rimeKeycode == XK_c || rimeKeycode == XK_C || rimeKeycode == XK_bracketleft))
      if isVimBackInCommandMode && rimeAPI.get_option(session, "vim_mode") &&
          !rimeAPI.get_option(session, "ascii_mode") {
        rimeAPI.set_option(session, "ascii_mode", true)
        // print("[DEBUG] turned Chinese mode off in vim-like editor's command mode")
      }
    } else {
      let isChordingKey = switch Int32(rimeKeycode) {
      case XK_space...XK_asciitilde, XK_Control_L, XK_Control_R, XK_Alt_L, XK_Alt_R, XK_Shift_L, XK_Shift_R:
        true
      default:
        false
      }
      if isChordingKey && rimeAPI.get_option(session, "_chord_typing") {
        updateChord(keycode: rimeKeycode, modifiers: rimeModifiers)
      } else if (rimeModifiers & kReleaseMask.rawValue) == 0 {
        // non-chording key pressed
        clearChord()
      }
    }

    rememberLanguage()
    return handled
  }

  func rimeConsumeCommittedText() {
    var commitText = RimeCommit.rimeStructInit()
    if rimeAPI.get_commit(session, &commitText) {
      if let text = commitText.text {
        commit(string: String(cString: text))
      }
      _ = rimeAPI.free_commit(&commitText)
    }
  }

  // swiftlint:disable:next cyclomatic_complexity
  func rimeUpdate() {
    // print("[DEBUG] rimeUpdate")
    rimeConsumeCommittedText()

    var status = RimeStatus_stdbool.rimeStructInit()
    if rimeAPI.get_status(session, &status) {
      // enable schema specific ui style
      // swiftlint:disable:next identifier_name
      if let schema_id = status.schema_id, schemaId == "" || schemaId != String(cString: schema_id) {
        schemaId = String(cString: schema_id)
        NSApp.squirrelAppDelegate.loadSettings(for: schemaId)
        // inline preedit
        if let panel = NSApp.squirrelAppDelegate.panel {
          inlinePreedit = (panel.inlinePreedit && !rimeAPI.get_option(session, "no_inline")) || rimeAPI.get_option(session, "inline")
          inlineCandidate = panel.inlineCandidate && !rimeAPI.get_option(session, "no_inline")
          // if not inline, embed soft cursor in preedit string
          rimeAPI.set_option(session, "soft_cursor", !inlinePreedit)
        }
      }
      _ = rimeAPI.free_status(&status)
    }

    var ctx = RimeContext_stdbool.rimeStructInit()
    if rimeAPI.get_context(session, &ctx) {
      // update preedit text
      let preedit = ctx.composition.preedit.map({ String(cString: $0) }) ?? ""

      let start = String.Index(preedit.utf8.index(preedit.utf8.startIndex, offsetBy: Int(ctx.composition.sel_start)), within: preedit) ?? preedit.startIndex
      let end = String.Index(preedit.utf8.index(preedit.utf8.startIndex, offsetBy: Int(ctx.composition.sel_end)), within: preedit) ?? preedit.startIndex
      let caretPos = String.Index(preedit.utf8.index(preedit.utf8.startIndex, offsetBy: Int(ctx.composition.cursor_pos)), within: preedit) ?? preedit.startIndex

      if inlineCandidate {
        var candidatePreview = ctx.commit_text_preview.map { String(cString: $0) } ?? ""
        let endOfCandidatePreview = candidatePreview.endIndex
        if inlinePreedit {
          // 左移光標後的情形：
          // preedit:             ^已選某些字[xiang zuo yi dong]|guangbiao$
          // commit_text_preview: ^已選某些字向左移動$
          // candidate_preview:   ^已選某些字[向左移動]|guangbiao$
          // 繼續翻頁至指定更短字詞的情形：
          // preedit:             ^已選某些字[xiang zuo]yidong|guangbiao$
          // commit_text_preview: ^已選某些字向左yidong$
          // candidate_preview:   ^已選某些字[向左]yidong|guangbiao$
          // 光標移至當前段落最左端的情形：
          // preedit:             ^已選某些字|[xiang zuo yi dong guang biao]$
          // commit_text_preview: ^已選某些字向左移動光標$
          // candidate_preview:   ^已選某些字|[向左移動光標]$
          // 討論：
          // preedit 與 commit_text_preview 中“已選某些字”部分一致
          // 因此，選中範圍即正在翻譯的碼段“向左移動”中，兩者的 start 值一致
          // 光標位置的範圍是 start ..= endOfCandidatePreview
          if caretPos >= end && caretPos < preedit.endIndex {
            // 從 preedit 截取光標後未翻譯的編碼“guangbiao”
            candidatePreview += preedit[caretPos...]
          }
        } else {
          // 翻頁至指定更短字詞的情形：
          // preedit:             ^已選某些字[xiang zuo]yidong|guangbiao$
          // commit_text_preview: ^已選某些字向左yidongguangbiao$
          // candidate_preview:   ^已選某些字[向左???]|$
          // 光標移至當前段落最左端，繼續翻頁至指定更短字詞的情形：
          // preedit:             ^已選某些字|[xiang zuo]yidongguangbiao$
          // commit_text_preview: ^已選某些字向左yidongguangbiao$
          // candidate_preview:   ^已選某些字|[向左]???$
          // FIXME: add librime APIs to support preview candidate without remaining code.
        }
        // preedit can contain additional prompt text before start:
        // ^(prompt)[selection]$
        let start = min(start, candidatePreview.endIndex)
        // caret can be either before or after the selected range.
        let caretPos = caretPos <= start ? caretPos : endOfCandidatePreview
        show(preedit: candidatePreview,
             selRange: NSRange(location: start.utf16Offset(in: candidatePreview),
                               length: candidatePreview.utf16.distance(from: start, to: candidatePreview.endIndex)),
             caretPos: caretPos.utf16Offset(in: candidatePreview))
      } else {
        if inlinePreedit {
          show(preedit: preedit, selRange: NSRange(location: start.utf16Offset(in: preedit), length: preedit.utf16.distance(from: start, to: end)), caretPos: caretPos.utf16Offset(in: preedit))
        } else {
          // TRICKY: display a non-empty string to prevent iTerm2 from echoing
          // each character in preedit. note this is a full-shape space U+3000;
          // using half shape characters like "..." will result in an unstable
          // baseline when composing Chinese characters.
          show(preedit: preedit.isEmpty ? "" : "　", selRange: NSRange(location: 0, length: 0), caretPos: 0)
        }
      }

      // update candidates
      let rawInput = rimeAPI.get_input(session).map {String(cString:$0)} ?? ""
      if expansionInput != rawInput {expandedCandidates=false;expansionInput=rawInput}
      let numCandidates = Int(ctx.menu.num_candidates)
      var candidates = [String]()
      var comments = [String]()
      for i in 0..<numCandidates {
        let candidate = ctx.menu.candidates[i]
        candidates.append(candidate.text.map { String(cString: $0) } ?? "")
        comments.append(candidate.comment.map { String(cString: $0) } ?? "")
      }
      var labels = [String]()
      // swiftlint:disable identifier_name
      if let select_keys = ctx.menu.select_keys {
        labels = String(cString: select_keys).map { String($0) }
      } else if let select_labels = ctx.select_labels {
        let pageSize = Int(ctx.menu.page_size)
        for i in 0..<pageSize {
          labels.append(select_labels[i].map { String(cString: $0) } ?? "")
        }
      }
      // swiftlint:enable identifier_name
      displayedCandidateOffset=Int(ctx.menu.page_no)*Int(ctx.menu.page_size)
      if expandedCandidates {
        var iterator=RimeCandidateListIterator()
        if rimeAPI.candidate_list_from_index(session,&iterator,Int32(displayedCandidateOffset+numCandidates)) {
          while candidates.count < max(9,Int(ctx.menu.page_size)*2) && rimeAPI.candidate_list_next(&iterator) {
            candidates.append(iterator.candidate.text.map {String(cString:$0)} ?? "")
            comments.append(iterator.candidate.comment.map {String(cString:$0)} ?? "")
          }
          rimeAPI.candidate_list_end(&iterator)
        }
      }
      displayedCandidateCount=candidates.count
      // Only the engine's current page has number shortcuts. Extra rows use mouse selection.
      labels=(0..<candidates.count).map {i in i < numCandidates ? (i < labels.count ? labels[i] : String(i+1)) : "·"}
      hasExpansionControl = !candidates.isEmpty && (!ctx.menu.is_last_page || expandedCandidates)
      let page = Int(ctx.menu.page_no)
      let lastPage = ctx.menu.is_last_page

      let selRange = NSRange(location: start.utf16Offset(in: preedit), length: preedit.utf16.distance(from: start, to: end))
      showPanel(preedit: inlinePreedit ? "" : preedit, selRange: selRange, caretPos: caretPos.utf16Offset(in: preedit),
                candidates: candidates, comments: comments, labels: labels, highlighted: Int(ctx.menu.highlighted_candidate_index),
                page: page, lastPage: lastPage)
      _ = rimeAPI.free_context(&ctx)
    } else {
      hasExpansionControl = false
      hidePalettes()
    }
  }

  func commit(string: String) {
    guard let client = client else { return }
    // print("[DEBUG] commitString: \(string)")
    client.insertText(string, replacementRange: .empty)
    preedit = ""
    expandedCandidates=false;expansionInput="";hasExpansionControl=false
    hidePalettes()
  }

  func show(preedit: String, selRange: NSRange, caretPos: Int) {
    guard let client = client else { return }
    // print("[DEBUG] showPreeditString: '\(preedit)'")
    if self.preedit == preedit && self.caretPos == caretPos && self.selRange == selRange {
      return
    }

    self.preedit = preedit
    self.caretPos = caretPos
    self.selRange = selRange

    // print("[DEBUG] selRange.location = \(selRange.location), selRange.length = \(selRange.length); caretPos = \(caretPos)")
    let start = selRange.location
    let attrString = NSMutableAttributedString(string: preedit)
    if start > 0 {
      let attrs = mark(forStyle: kTSMHiliteConvertedText, at: NSRange(location: 0, length: start))! as! [NSAttributedString.Key: Any]
      attrString.setAttributes(attrs, range: NSRange(location: 0, length: start))
    }
    let remainingRange = NSRange(location: start, length: preedit.utf16.count - start)
    let attrs = mark(forStyle: kTSMHiliteSelectedRawText, at: remainingRange)! as! [NSAttributedString.Key: Any]
    attrString.setAttributes(attrs, range: remainingRange)
    client.setMarkedText(attrString, selectionRange: NSRange(location: caretPos, length: 0), replacementRange: .empty)
  }

  // swiftlint:disable:next function_parameter_count
  func showPanel(preedit: String, selRange: NSRange, caretPos: Int, candidates: [String], comments: [String], labels: [String], highlighted: Int, page: Int, lastPage: Bool) {
    // print("[DEBUG] showPanelWithPreedit:...:")
    guard let client = client else { return }
    var inputPos = NSRect()
    client.attributes(forCharacterIndex: 0, lineHeightRectangle: &inputPos)
    if let panel = NSApp.squirrelAppDelegate.panel {
      panel.position = inputPos
      panel.inputController = self
      panel.update(preedit: preedit, selRange: selRange, caretPos: caretPos, candidates: candidates, comments: comments, labels: labels,
                   highlighted: highlighted, page: page, lastPage: lastPage, update: true)
    }
  }
}

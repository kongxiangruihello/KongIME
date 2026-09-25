//
//  SquirrelPanel.swift
//  Squirrel
//
//  Created by Leo Liu on 5/10/24.
//

import AppKit

final class SquirrelPanel: NSPanel {
  private let view: SquirrelView
  private let back: NSVisualEffectView
  private let expansionButton = NSButton()
  private let detailButton = NSButton()
  private let detailScroll = NSScrollView()
  private let detailText = NSTextView()
  private var detailOpen = false
  private let scrollView = NSScrollView()
  private let canvas = NSView()
  private var resetScroll = true
  var inputController: SquirrelInputController?

  var position: NSRect
  private var screenRect: NSRect = .zero
  private var maxHeight: CGFloat = 0

  private var statusMessage: String = ""
  private var statusTimer: Timer?

  private var preedit: String = ""
  private var selRange: NSRange = .empty
  private var caretPos: Int = 0
  private var candidates: [String] = .init()
  private var comments: [String] = .init()
  private var labels: [String] = .init()
  private var index: Int = 0
  private var cursorIndex: Int = 0
  private var scrollDirection: CGVector = .zero
  private var scrollTime: Date = .distantPast
  private var page: Int = 0
  private var lastPage: Bool = true
  private var pagingUp: Bool?

  init(position: NSRect) {
    self.position = position
    self.view = SquirrelView(frame: position)
    self.back = NSVisualEffectView()
    super.init(contentRect: position, styleMask: .nonactivatingPanel, backing: .buffered, defer: true)
    self.level = .init(Int(CGShieldingWindowLevel()))
    self.hasShadow = true
    self.isOpaque = false
    self.backgroundColor = .clear
    back.blendingMode = .behindWindow
    back.material = .hudWindow
    back.state = .active
    back.wantsLayer = true
    back.layer?.mask = view.shape
    let contentView = NSView()
    canvas.addSubview(back)
    canvas.addSubview(view)
    canvas.addSubview(view.textView)
    scrollView.documentView = canvas
    scrollView.drawsBackground = false
    scrollView.scrollerStyle = .overlay
    scrollView.hasVerticalScroller = true
    scrollView.autohidesScrollers = true
    contentView.addSubview(scrollView)
    expansionButton.title = "▾"
    expansionButton.isBordered = false
    expansionButton.bezelStyle = .inline
    expansionButton.target = self
    expansionButton.action = #selector(toggleExpansion)
    expansionButton.toolTip = "展开／收起候选（Tab）"
    expansionButton.setAccessibilityLabel("展开候选（Tab）")
    contentView.addSubview(expansionButton)
    detailButton.title = "全文"
    detailButton.isBordered = false
    detailButton.target = self
    detailButton.action = #selector(toggleCandidateDetail)
    detailButton.toolTip = "查看／收起高亮候选全文（Control＋Return）"
    detailButton.setAccessibilityLabel("查看高亮候选全文")
    detailText.isEditable = false
    detailText.isSelectable = false
    detailText.font = .systemFont(ofSize: 14)
    detailText.textContainerInset = NSSize(width: 8, height: 8)
    detailText.isVerticallyResizable = true
    detailText.autoresizingMask = [.width]
    detailText.textContainer?.widthTracksTextView = true
    detailScroll.documentView = detailText
    detailScroll.hasVerticalScroller = true
    detailScroll.autohidesScrollers = true
    contentView.addSubview(detailButton)
    contentView.addSubview(detailScroll)
    self.contentView = contentView
  }

  @objc private func toggleExpansion() { inputController?.toggleExpansion() }
  @objc @discardableResult func toggleCandidateDetail() -> Bool {
    guard candidates.indices.contains(cursorIndex), candidates[cursorIndex].count > 28 else { return false }
    detailOpen.toggle()
    show()
    return true
  }

  @objc private func quickCandidateAction(_ item:NSMenuItem) {
    guard let value=item.representedObject as? [String:String],let word=value["word"],let code=value["code"],let action=value["action"] else {return}
    if action == "phrase-new" || action == "phrase-edit" {
      inputController?.openCandidatePhrase(word: word, code: code, comment: value["comment"] ?? "", action: action == "phrase-edit" ? "edit" : "new")
    } else { inputController?.adjustQuickCandidate(word:word,code:code,action:action) }
  }

  var linear: Bool {
    view.currentTheme.linear
  }
  var vertical: Bool {
    view.currentTheme.vertical
  }
  var inlinePreedit: Bool {
    view.currentTheme.inlinePreedit
  }
  var inlineCandidate: Bool {
    view.currentTheme.inlineCandidate
  }

  // swiftlint:disable:next cyclomatic_complexity
  override func sendEvent(_ event: NSEvent) {
    let point = contentView!.convert(convertPoint(fromScreen: NSEvent.mouseLocation), from: nil)
    if (!detailButton.isHidden && detailButton.frame.contains(point)) || (!detailScroll.isHidden && detailScroll.frame.contains(point)) { super.sendEvent(event); return }
    if !expansionButton.isHidden && expansionButton.frame.contains(point) { super.sendEvent(event); return }
    if event.type == .scrollWheel && canvas.frame.height > scrollView.contentSize.height + 1 { super.sendEvent(event); return }
    switch event.type {
    case .rightMouseDown:
      let (candidateIndex, _, _) = view.click(at: mousePosition())
      guard let candidateIndex, candidateIndex>=0, candidateIndex<candidates.count,
            let code=inputController?.quickInput(candidateIndex:candidateIndex) else {return}
      let menu=NSMenu(); menu.autoenablesItems = false
      for (title,action) in [("置顶","pin"),("取消置顶","unpin"),("降低优先级","lower"),("不再推荐这个词","block")] {
        let item=NSMenuItem(title:title,action:#selector(quickCandidateAction(_:)),keyEquivalent:"")
        item.isEnabled = action == "block" || inputController?.quickReorderingAvailable(candidateIndex: candidateIndex) == true
        item.target=self;item.representedObject=["word":candidates[candidateIndex],"code":code,"action":action];menu.addItem(item)
      }
      menu.addItem(.separator())
      var phraseActions = [("保存为短语…", "phrase-new")]
      let comment = comments.indices.contains(candidateIndex) ? comments[candidateIndex] : ""
      if inputController?.hasCandidatePhrase(word: candidates[candidateIndex], code: code, comment: comment) == true { phraseActions.append(("编辑对应短语…", "phrase-edit")) }
      for (title, action) in phraseActions {
        let item = NSMenuItem(title: title, action: #selector(quickCandidateAction(_:)), keyEquivalent: "")
        item.target = self; item.representedObject = ["word": candidates[candidateIndex], "code": code, "comment": comment, "action": action]
        item.isEnabled = candidates[candidateIndex].count <= 500
        menu.addItem(item)
      }
      menu.popUp(positioning:nil,at:NSEvent.mouseLocation,in:nil)
      return
    case .leftMouseDown:
      let (index, _, pagingUp) =  view.click(at: mousePosition())
      if let pagingUp {
        self.pagingUp = pagingUp
      } else {
        self.pagingUp = nil
      }
      if let index, index >= 0 && index < candidates.count {
        self.index = index
      }
    case .leftMouseUp:
      let (index, preeditIndex, pagingUp) = view.click(at: mousePosition())

      if let pagingUp, pagingUp == self.pagingUp {
        _ = inputController?.page(up: pagingUp)
      } else {
        self.pagingUp = nil
      }
      if let preeditIndex, preeditIndex >= 0 && preeditIndex < preedit.utf16.count {
        if preeditIndex < caretPos {
          _ = inputController?.moveCaret(forward: true)
        } else if preeditIndex > caretPos {
          _ = inputController?.moveCaret(forward: false)
        }
      }
      if let index, index == self.index && index >= 0 && index < candidates.count {
        _ = inputController?.selectCandidate(index)
      }
    case .mouseEntered:
      acceptsMouseMovedEvents = true
    case .mouseExited:
      acceptsMouseMovedEvents = false
      if cursorIndex != index {
        update(preedit: preedit, selRange: selRange, caretPos: caretPos, candidates: candidates, comments: comments, labels: labels, highlighted: index, page: page, lastPage: lastPage, update: false)
      }
      pagingUp = nil
    case .mouseMoved:
      let (index, _, _) = view.click(at: mousePosition())
      if let index = index, cursorIndex != index && index >= 0 && index < candidates.count {
        update(preedit: preedit, selRange: selRange, caretPos: caretPos, candidates: candidates, comments: comments, labels: labels, highlighted: index, page: page, lastPage: lastPage, update: false)
      }
    case .scrollWheel:
      if event.phase == .began {
        scrollDirection = .zero
        // Scrollboard span
      } else if event.phase == .ended || (event.phase == .init(rawValue: 0) && event.momentumPhase != .init(rawValue: 0)) {
        if abs(scrollDirection.dx) > abs(scrollDirection.dy) && abs(scrollDirection.dx) > 10 {
          _ = inputController?.page(up: (scrollDirection.dx < 0) == vertical)
        } else if abs(scrollDirection.dx) < abs(scrollDirection.dy) && abs(scrollDirection.dy) > 10 {
          _ = inputController?.page(up: scrollDirection.dy > 0)
        }
        scrollDirection = .zero
        // Mouse scroll wheel
      } else if event.phase == .init(rawValue: 0) && event.momentumPhase == .init(rawValue: 0) {
        if scrollTime.timeIntervalSinceNow < -1 {
          scrollDirection = .zero
        }
        scrollTime = .now
        if (scrollDirection.dy >= 0 && event.scrollingDeltaY > 0) || (scrollDirection.dy <= 0 && event.scrollingDeltaY < 0) {
          scrollDirection.dy += event.scrollingDeltaY
        } else {
          scrollDirection = .zero
        }
        if abs(scrollDirection.dy) > 10 {
          _ = inputController?.page(up: scrollDirection.dy > 0)
          scrollDirection = .zero
        }
      } else {
        scrollDirection.dx += event.scrollingDeltaX
        scrollDirection.dy += event.scrollingDeltaY
      }
    default:
      break
    }
    super.sendEvent(event)
  }

  func hide() {
    detailOpen = false
    statusTimer?.invalidate()
    statusTimer = nil
    orderOut(nil)
    maxHeight = 0
  }

  // Main function to add attributes to text output from librime
  // swiftlint:disable:next cyclomatic_complexity function_parameter_count
  func update(preedit: String, selRange: NSRange, caretPos: Int, candidates: [String], comments: [String], labels: [String], highlighted index: Int, page: Int, lastPage: Bool, update: Bool) {
    if update {
      if self.candidates != candidates { detailOpen = false }
      resetScroll = true
      self.preedit = preedit
      self.selRange = selRange
      self.caretPos = caretPos
      self.candidates = candidates
      self.comments = comments
      self.labels = labels
      self.index = index
      self.page = page
      self.lastPage = lastPage
    }
    cursorIndex = index

    if !candidates.isEmpty || !preedit.isEmpty {
      statusMessage = ""
      statusTimer?.invalidate()
      statusTimer = nil
    } else {
      if !statusMessage.isEmpty {
        show(status: statusMessage)
        statusMessage = ""
      } else if statusTimer == nil {
        hide()
      }
      return
    }

    let theme = view.currentTheme
    currentScreen()

    let text = NSMutableAttributedString()
    let preeditRange: NSRange
    let highlightedPreeditRange: NSRange

    // preedit
    if !preedit.isEmpty {
      preeditRange = NSRange(location: 0, length: preedit.utf16.count)
      highlightedPreeditRange = selRange

      let line = NSMutableAttributedString(string: preedit)
      line.addAttributes(theme.preeditAttrs, range: preeditRange)
      line.addAttributes(theme.preeditHighlightedAttrs, range: selRange)
      text.append(line)

      text.addAttribute(.paragraphStyle, value: theme.preeditParagraphStyle, range: NSRange(location: 0, length: text.length))
      if !candidates.isEmpty {
        text.append(NSAttributedString(string: "\n", attributes: theme.preeditAttrs))
      }
    } else {
      preeditRange = .empty
      highlightedPreeditRange = .empty
    }

    // candidates
    var candidateRanges = [NSRange]()
    for i in 0..<candidates.count {
      let attrs = i == index ? theme.highlightedAttrs : theme.attrs
      let labelAttrs = i == index ? theme.labelHighlightedAttrs : theme.labelAttrs
      let commentAttrs = i == index ? theme.commentHighlightedAttrs : theme.commentAttrs

      let label = if theme.candidateFormat.contains(/\[label\]/) {
        if labels.count > 1 && i < labels.count {
          labels[i]
        } else if labels.count == 1 && i < labels.first!.count {
          // custom: A. B. C...
          String(labels.first![labels.first!.index(labels.first!.startIndex, offsetBy: i)])
        } else {
          // default: 1. 2. 3...
          "\(i+1)"
        }
      } else {
        ""
      }

      let fullCandidate = candidates[i].precomposedStringWithCanonicalMapping
      let candidate = fullCandidate.count > 28 ? String(fullCandidate.prefix(28)) + "…" : fullCandidate
      let comment = comments[i].precomposedStringWithCanonicalMapping

      let templateLabel = ["日期", "时间", "落款", "模板"].contains(comment)
      let format = templateLabel && !theme.candidateFormat.contains("[comment]") ? theme.candidateFormat + " [comment]" : theme.candidateFormat
      let line = NSMutableAttributedString(string: format, attributes: labelAttrs)
      for range in line.string.ranges(of: /\[candidate\]/) {
        let convertedRange = convert(range: range, in: line.string)
        line.addAttributes(attrs, range: convertedRange)
        if candidate.count <= 5 {
          line.addAttribute(.noBreak, value: true, range: NSRange(location: convertedRange.location+1, length: convertedRange.length-1))
        }
      }
      for range in line.string.ranges(of: /\[comment\]/) {
        line.addAttributes(commentAttrs, range: convert(range: range, in: line.string))
      }
      line.mutableString.replaceOccurrences(of: "[label]", with: label, range: NSRange(location: 0, length: line.length))
      let labeledLine = line.copy() as! NSAttributedString
      line.mutableString.replaceOccurrences(of: "[candidate]", with: candidate, range: NSRange(location: 0, length: line.length))
      line.mutableString.replaceOccurrences(of: "[comment]", with: comment, range: NSRange(location: 0, length: line.length))

      if line.length <= 10 {
        line.addAttribute(.noBreak, value: true, range: NSRange(location: 1, length: line.length-1))
      }

      let lineSeparator = NSAttributedString(string: linear ? "  " : "\n", attributes: attrs)
      if i > 0 {
        text.append(lineSeparator)
      }
      let str = lineSeparator.mutableCopy() as! NSMutableAttributedString
      if vertical {
        str.addAttribute(.verticalGlyphForm, value: 1, range: NSRange(location: 0, length: str.length))
      }
      view.separatorWidth = str.boundingRect(with: .zero).width

      let paragraphStyleCandidate = (i == 0 ? theme.firstParagraphStyle : theme.paragraphStyle).mutableCopy() as! NSMutableParagraphStyle
      if linear {
        paragraphStyleCandidate.paragraphSpacingBefore -= theme.linespace
        paragraphStyleCandidate.lineSpacing = theme.linespace
      }
      if !linear, let labelEnd = labeledLine.string.firstMatch(of: /\[(candidate|comment)\]/)?.range.lowerBound {
        let labelString = labeledLine.attributedSubstring(from: NSRange(location: 0, length: labelEnd.utf16Offset(in: labeledLine.string)))
        let labelWidth = labelString.boundingRect(with: .zero, options: [.usesLineFragmentOrigin]).width
        paragraphStyleCandidate.headIndent = labelWidth
      }
      line.addAttribute(.paragraphStyle, value: paragraphStyleCandidate, range: NSRange(location: 0, length: line.length))

      candidateRanges.append(NSRange(location: text.length, length: line.length))
      text.append(line)
    }

    // text done!
    view.textView.textContentStorage?.attributedString = text
    view.textView.setLayoutOrientation(vertical ? .vertical : .horizontal)
    view.drawView(candidateRanges: candidateRanges, hilightedIndex: index, preeditRange: preeditRange, highlightedPreeditRange: highlightedPreeditRange, canPageUp: page > 0, canPageDown: !lastPage)
    show()
  }

  func updateStatus(long longMessage: String, short shortMessage: String) {
    let theme = view.currentTheme
    switch theme.statusMessageType {
    case .mix:
      statusMessage = shortMessage.isEmpty ? longMessage : shortMessage
    case .long:
      statusMessage = longMessage
    case .short:
      if !shortMessage.isEmpty {
        statusMessage = shortMessage
      } else if let initial = longMessage.first {
        statusMessage = String(initial)
      } else {
        statusMessage = ""
      }
    }
  }

  func load(config: SquirrelConfig, forDarkMode isDark: Bool) {
    if isDark {
      view.darkTheme = SquirrelTheme()
      view.darkTheme.load(config: config, dark: true)
    } else {
      view.lightTheme = SquirrelTheme()
      view.lightTheme.load(config: config, dark: isDark)
    }
  }
}

private extension SquirrelPanel {
  func mousePosition() -> NSPoint {
    var point = NSEvent.mouseLocation
    point = self.convertPoint(fromScreen: point)
    return view.convert(point, from: nil)
  }

  func currentScreen() {
    let screens = NSScreen.screens
    if let index = CandidateGeometry.screenIndex(anchor: position, frames: screens.map { $0.frame }) {
      screenRect = screens[index].visibleFrame
    } else {
      screenRect = NSRect(x: 0, y: 0, width: 1024, height: 768)
    }
  }

  func maxTextWidth() -> CGFloat {
    let theme = view.currentTheme
    let font: NSFont = theme.font
    let fontScale = font.pointSize / 12
    let textWidthRatio = min(1, 1 / (vertical ? 4 : 3) + fontScale / 12)
    let maxWidth = if vertical {
      screenRect.height * textWidthRatio - theme.edgeInset.height * 2
    } else {
      screenRect.width * textWidthRatio - theme.edgeInset.width * 2
    }
    return maxWidth
  }

  // Get the window size, the windows will be the dirtyRect in
  // SquirrelView.drawRect
  // swiftlint:disable:next cyclomatic_complexity
  func show() {
    currentScreen()
    let theme = view.currentTheme
    if theme.native || view.darkTheme.available {
      self.appearance = NSApp.effectiveAppearance
    } else {
      // user configured only a light theme, set window appearance to light.
      self.appearance = NSAppearance(named: .aqua)
    }

    // Break line if the text is too long, based on screen size.
    let textWidth = maxTextWidth()
    let maxTextHeight = vertical ? screenRect.width - theme.edgeInset.width * 2 : screenRect.height - theme.edgeInset.height * 2
    view.textContainer.size = NSSize(width: textWidth, height: vertical ? maxTextHeight : 100000)

    var panelRect = NSRect.zero
    // in vertical mode, the width and height are interchanged
    var contentRect = view.contentRect
    if theme.memorizeSize && (vertical && (position.midY - screenRect.minY) / screenRect.height < 0.5) ||
        (vertical && position.minX + max(contentRect.width, maxHeight) + theme.edgeInset.width * 2 > screenRect.maxX) {
      if contentRect.width >= maxHeight {
        maxHeight = contentRect.width
      } else {
        contentRect.size.width = maxHeight
        view.textContainer.size = NSSize(width: maxHeight, height: maxTextHeight)
      }
    }

    if vertical {
      panelRect.size = NSSize(width: min(0.95 * screenRect.width, contentRect.height + theme.edgeInset.height * 2),
                              height: min(0.95 * screenRect.height, contentRect.width + theme.edgeInset.width * 2) + theme.pagingOffset)

      // To avoid jumping up and down while typing, use the lower screen when
      // typing on upper, and vice versa
      if (position.midY - screenRect.minY) / screenRect.height >= 0.5 {
        panelRect.origin.y = position.minY - SquirrelTheme.offsetHeight - panelRect.height + theme.pagingOffset
      } else {
        panelRect.origin.y = position.maxY + SquirrelTheme.offsetHeight
      }
      // Make the first candidate fixed at the left of cursor
      panelRect.origin.x = position.minX - panelRect.width - SquirrelTheme.offsetHeight
      if view.preeditRange.length > 0, let preeditTextRange = view.convert(range: view.preeditRange) {
        let preeditRect = view.contentRect(range: preeditTextRange)
        panelRect.origin.x += preeditRect.height + theme.edgeInset.width
      }
    } else {
      panelRect.size = NSSize(width: min(0.95 * screenRect.width, contentRect.width + theme.edgeInset.width * 2),
                              height: min(0.95 * screenRect.height, contentRect.height + theme.edgeInset.height * 2))
      panelRect.size.width += theme.pagingOffset
      panelRect.origin = NSPoint(x: position.minX - theme.pagingOffset, y: position.minY - SquirrelTheme.offsetHeight - panelRect.height)
    }
    let showExpansion = statusMessage.isEmpty && !candidates.isEmpty && inputController?.expansionAvailable == true && statusTimer == nil
    let showDetail = statusMessage.isEmpty && candidates.indices.contains(cursorIndex) && candidates[cursorIndex].count > 28 && !vertical
    let requestedDetailHeight: CGFloat = showDetail && detailOpen ? 120 : 0
    var footer: CGFloat = (showExpansion || showDetail) && !vertical ? 24 + requestedDetailHeight : 0
    panelRect.size.height = min(screenRect.height, panelRect.height + footer)
    panelRect.size.width = min(screenRect.width, max(showDetail ? 280 : 44, panelRect.width))
    if panelRect.maxX > screenRect.maxX {
      panelRect.origin.x = screenRect.maxX - panelRect.width
    }
    if panelRect.minX < screenRect.minX {
      panelRect.origin.x = screenRect.minX
    }
    if panelRect.minY < screenRect.minY {
      if vertical {
        panelRect.origin.y = screenRect.minY
      } else {
        panelRect.origin.y = position.maxY + SquirrelTheme.offsetHeight
      }
    }
    if panelRect.maxY > screenRect.maxY {
      panelRect.origin.y = screenRect.maxY - panelRect.height
    }
    if panelRect.minY < screenRect.minY {
      panelRect.origin.y = screenRect.minY
    }
    if vertical {
      panelRect = CandidateGeometry.contained(panelRect, in: screenRect)
    } else {
      panelRect = CandidateGeometry.avoidingLine(panelRect, anchor: position, in: screenRect, gap: theme.candidateGap)
    }
    self.setFrame(panelRect, display: true)
    footer = min(footer, max(0, panelRect.height - 24))
    let detailHeight = min(requestedDetailHeight, max(0, footer - 24))

    // rotate the view, the core in vertical mode!
    if vertical {
      contentView!.boundsRotation = -90
      contentView!.setBoundsOrigin(NSPoint(x: 0, y: panelRect.width))
    } else {
      contentView!.boundsRotation = 0
      contentView!.setBoundsOrigin(.zero)
    }
    view.textView.boundsRotation = 0
    view.textView.setBoundsOrigin(.zero)

    scrollView.frame = contentView!.bounds
    scrollView.frame.origin.y += footer
    scrollView.frame.size.height -= footer
    canvas.frame = NSRect(origin: .zero, size: NSSize(width: scrollView.contentSize.width, height: vertical ? scrollView.contentSize.height : max(scrollView.contentSize.height, contentRect.height + theme.edgeInset.height * 2)))
    expansionButton.isHidden = !showExpansion || vertical
    expansionButton.title = inputController?.expansionIsOpen == true ? "▴" : "▾"
    expansionButton.toolTip = "展开／收起候选（"+(inputController?.expansionShortcutLabel ?? "Tab")+"）"
    expansionButton.setAccessibilityLabel((inputController?.expansionIsOpen == true ? "收起候选" : "展开候选")+"（"+(inputController?.expansionShortcutLabel ?? "Tab")+"）")
    expansionButton.frame = NSRect(x: max(0, contentView!.bounds.width - 32), y: detailHeight, width: 28, height: min(24, footer))
    detailButton.isHidden = !showDetail
    detailButton.title = detailOpen ? "收起全文" : "全文"
    detailButton.frame = NSRect(x: 4, y: detailHeight, width: 76, height: min(24, footer))
    detailScroll.isHidden = detailHeight == 0
    detailScroll.frame = NSRect(x: 4, y: 0, width: max(0, contentView!.bounds.width - 8), height: detailHeight)
    if showDetail {
      detailText.string = candidates[cursorIndex]
      detailText.setAccessibilityValue(candidates[cursorIndex])
      detailText.frame.size.width = detailScroll.contentSize.width
      detailText.sizeToFit()
    }
    view.frame = canvas.bounds
    view.textView.frame = canvas.bounds
    view.textView.frame.size.width -= theme.pagingOffset
    view.textView.frame.origin.x += theme.pagingOffset
    view.textView.textContainerInset = theme.edgeInset

    if theme.translucency {
      back.frame = canvas.bounds
      back.frame.size.width += theme.pagingOffset
      back.appearance = NSApp.effectiveAppearance
      back.isHidden = false
    } else {
      back.isHidden = true
    }
    if resetScroll { canvas.scroll(NSPoint(x: 0, y: max(0, canvas.frame.height - scrollView.contentSize.height))); resetScroll = false }
    alphaValue = theme.alpha
    invalidateShadow()
    orderFront(nil)
    // voila!
  }

  func show(status message: String) {
    let theme = view.currentTheme
    let text = NSMutableAttributedString(string: message, attributes: theme.attrs)
    text.addAttribute(.paragraphStyle, value: theme.paragraphStyle, range: NSRange(location: 0, length: text.length))
    view.textContentStorage.attributedString = text
    view.textView.setLayoutOrientation(vertical ? .vertical : .horizontal)
    view.drawView(candidateRanges: [NSRange(location: 0, length: text.length)], hilightedIndex: -1,
                  preeditRange: .empty, highlightedPreeditRange: .empty, canPageUp: false, canPageDown: false)
    show()

    statusTimer?.invalidate()
    statusTimer = Timer.scheduledTimer(withTimeInterval: SquirrelTheme.showStatusDuration, repeats: false) { _ in
      self.hide()
    }
  }

  func convert(range: Range<String.Index>, in string: String) -> NSRange {
    let startPos = range.lowerBound.utf16Offset(in: string)
    let endPos = range.upperBound.utf16Offset(in: string)
    return NSRange(location: startPos, length: endPos - startPos)
  }
}

// Isolated native layout smoke test: production panel/view/theme, no Rime session or user data.
import AppKit
final class SquirrelInputController {
 var expansionShortcutLabel = "Tab"
 var expansionAvailable = true
 var expansionIsOpen = false
 func toggleExpansion() { expansionIsOpen.toggle() }
 func hasCandidatePhrase(word: String, code: String, comment: String) -> Bool { false }
 func openCandidatePhrase(word: String, code: String, comment: String, action: String) {}
 func quickInput(candidateIndex: Int) -> String? { nil }
 func quickReorderingAvailable(candidateIndex: Int) -> Bool { true }
 func adjustQuickCandidate(word: String,code: String,action: String) {}
 func page(up: Bool) -> Bool { true }
 func moveCaret(forward: Bool) -> Bool { true }
 func selectCandidate(_ index: Int) -> Bool { true }
}
@main struct PanelSmoke {
 static func main() {
  _ = NSApplication.shared
  let controller = SquirrelInputController()
  let panel = SquirrelPanel(position: .zero); panel.inputController = controller
  precondition(!NSScreen.screens.isEmpty, "Native display access required")
  var count = 0
  for screen in NSScreen.screens {
   let area = screen.visibleFrame
   for point in [NSPoint(x: area.minX,y: area.minY), NSPoint(x: area.maxX-1,y: area.minY),NSPoint(x: area.minX,y: area.maxY-20),NSPoint(x: area.maxX-1,y: area.maxY-20),NSPoint(x:area.midX,y:area.midY)] {
    for size in [1,5,18] {
     controller.expansionAvailable = size > 1
     panel.position = NSRect(origin:point,size:NSSize(width:1,height:18))
     let words = (0..<size).map { "候选\($0)" + String(repeating:"长词显示测试",count:12) }
     panel.update(preedit:"changci",selRange:NSRange(location:0,length:7),caretPos:7,candidates:words,comments:Array(repeating:"chang ci",count:size),labels:(1...size).map(String.init),highlighted:0,page:0,lastPage:false,update:true)
     precondition(panel.frame.minX >= area.minX && panel.frame.maxX <= area.maxX + 0.5)
     precondition(panel.frame.minY >= area.minY && panel.frame.maxY <= area.maxY + 0.5)
     precondition(panel.frame.maxY <= panel.position.minY-8 || panel.frame.minY >= panel.position.maxY+8,"Native panel overlaps input line")
     let scroll = panel.contentView!.subviews.compactMap { $0 as? NSScrollView }.first!
     precondition(scroll.documentView!.frame.height >= scroll.contentSize.height)
     let button = panel.contentView!.subviews.compactMap { $0 as? NSButton }.first!
     precondition(button.isHidden == (size == 1) && button.frame.maxY <= scroll.frame.minY)
     precondition(scroll.documentView!.frame.height.isFinite)
     precondition(panel.toggleCandidateDetail())
     precondition(panel.frame.minX >= area.minX && panel.frame.maxX <= area.maxX + 0.5)
     precondition(panel.frame.maxY <= panel.position.minY-8 || panel.frame.minY >= panel.position.maxY+8)
     let details = panel.contentView!.subviews.compactMap { $0 as? NSScrollView }.last!
     precondition((details.documentView as? NSTextView)?.string == words[0])
     precondition(!details.isHidden && details.frame.maxY <= scroll.frame.minY)
     precondition(panel.toggleCandidateDetail())
     panel.hide();count += 1
    }
   }
  }
  print("Native long-candidate / screen-edge layout checks passed: \(count); physical screens: \(NSScreen.screens.count)")
 }
}

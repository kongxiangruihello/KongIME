import AppKit
final class UndoTextView: NSTextView {
 let history=UndoManager()
 override var undoManager: UndoManager? { history }
}
@main struct PunctuationWrapSmoke {
 static func main() {
  let view=UndoTextView(frame:.zero);view.allowsUndo=true;view.history.groupsByEvent=false
  func replace(_ value:String,_ range:NSRange){view.insertText(value,replacementRange:range)}
  func locate(_ range:NSRange){view.setMarkedText("",selectedRange:NSRange(location:0,length:0),replacementRange:range)}
  for ascii in [true,false] {
   for (key,pair) in ascii ? PunctuationPairs.english : PunctuationPairs.chinese {
    for selected in ["", "中文😀\n第二行", "word"] {
     view.string="前"+selected+"后";let original=view.string
     let range=NSRange(location:1,length:selected.utf16.count);view.setSelectedRange(range)
     view.history.removeAllActions();view.breakUndoCoalescing()
     view.history.beginUndoGrouping()
     PunctuationPairs.wrap(pair,text:selected,range:range,replace:replace,locate:locate)
     view.history.endUndoGrouping();view.breakUndoCoalescing()
     precondition(view.string=="前"+String(pair.first!)+selected+String(pair.last!)+"后")
     precondition(view.selectedRange()==NSRange(location:2+selected.utf16.count,length:0))
     precondition(!view.hasMarkedText());precondition(view.history.canUndo)
     view.history.undo();precondition(view.string==original,"undo failed for \(key)")
    }
   }
   for key in [")","]","}","\"","'"] {
    let closing=PunctuationPairs.closing(for:key,ascii:ascii)!
    view.string="前"+closing+"后";view.setSelectedRange(NSRange(location:1,length:0))
    view.history.beginUndoGrouping()
    PunctuationPairs.move(to:2,replace:replace,locate:locate)
    view.history.endUndoGrouping()
    precondition(view.string=="前"+closing+"后" && view.selectedRange().location==2)
    precondition(!view.hasMarkedText())
   }
  }
  precondition(PunctuationPairs.pair(for:"'",ascii:false,previous:"你")=="‘’")
  precondition(PunctuationPairs.pair(for:"'",ascii:true,previous:"n")==nil)
  precondition(PunctuationPairs.closing(for:">",ascii:true)==nil)
  print("PASS: selection wrap, Chinese/emoji/multiline UTF-16, single-event undo, closing skip and contractions")
 }
}

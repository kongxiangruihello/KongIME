import AppKit
@main struct PunctuationPairsSmoke {
 static func main() {
  let view=NSTextView(frame:.zero)
  for ascii in [true,false] {
   for (key,pair) in ascii ? PunctuationPairs.english : PunctuationPairs.chinese {
    view.string="你好😀abc";let position=(view.string as NSString).length
    precondition(PunctuationPairs.pair(for:key,ascii:ascii,previous:"")==pair)
    view.setSelectedRange(NSRange(location:position,length:0))
    PunctuationPairs.insert(pair,at:position,replace:{view.insertText($0,replacementRange:$1)},locate:{view.setMarkedText("",selectedRange:NSRange(location:0,length:0),replacementRange:$0)})
    precondition(view.string=="你好😀abc"+pair)
    precondition(view.selectedRange()==NSRange(location:position+1,length:0))
    precondition(!view.hasMarkedText())
    precondition(PunctuationPairs.isEmptyPair(pair,ascii:ascii))
    view.insertText("",replacementRange:NSRange(location:position,length:2))
    precondition(view.string=="你好😀abc" && view.selectedRange().location==position)
   }
  }
  precondition(PunctuationPairs.pair(for:"'",ascii:true,previous:"n")==nil)
  precondition(PunctuationPairs.pair(for:"a",ascii:false,previous:"")==nil)
  print("PASS: Chinese/English pairs, NSTextView caret placement, empty-pair deletion, UTF-16 offsets and contractions")
 }
}

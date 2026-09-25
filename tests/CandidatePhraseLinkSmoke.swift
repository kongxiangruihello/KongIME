import Foundation
@main struct LinkSmoke {
 static func main() {
  let text = "孔祥瑞 · \"引号\" & <script> ' \\ 日期 😊"
  let url = CandidatePhraseLink.url(word: text, code: "rq", comment: "日期", action: "new")!
  let value = CandidatePhraseLink.payload(url)!
  precondition(value["text"] == text && value["code"] == "rq")
  let rows: [[String:Any]] = [["code":"rq","text":"{W}","dynamic":true,"label":"日期"],["code":"yx","text":"name@example.com"]]
  precondition(CandidatePhraseLink.existing(word:"星期二",code:"rq",comment:"日期",rows:rows))
  precondition(!CandidatePhraseLink.existing(word:"日期",code:"rq",comment:"ri qi",rows:rows))
  precondition(CandidatePhraseLink.existing(word:"name@example.com",code:"yx",comment:"",rows:rows))
  precondition(CandidatePhraseLink.payload(URL(string:"https://example.com")!) == nil)
  precondition(CandidatePhraseLink.payload(URL(string:url.absoluteString+"&action=edit")!) == nil)
  precondition(CandidatePhraseLink.payload(CandidatePhraseLink.url(word:"bad\ntext",code:"rq",comment:"",action:"new")!) == nil)
  let json = String(data:try! JSONSerialization.data(withJSONObject:value),encoding:.utf8)!
  precondition((try! JSONSerialization.jsonObject(with:Data(json.utf8)) as! [String:String])["text"] == text)
  print("Candidate phrase link: Unicode/escaping, static/dynamic matching, invalid URL and duplicate field checks passed")
 }
}

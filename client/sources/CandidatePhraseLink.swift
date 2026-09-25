import Foundation

enum CandidatePhraseLink {
  static func existing(word: String, code: String, comment: String, rows: [[String: Any]]) -> Bool {
    rows.contains { row in
      guard row["code"] as? String == code else { return false }
      if row["dynamic"] as? Bool == true { return (row["label"] as? String ?? "模板") == comment }
      return row["text"] as? String == word
    }
  }
  static func url(word: String, code: String, comment: String, action: String) -> URL? {
    var parts = URLComponents()
    parts.scheme = "kongime-settings"; parts.host = "phrase"
    parts.queryItems = [URLQueryItem(name: "text", value: word), URLQueryItem(name: "code", value: code), URLQueryItem(name: "comment", value: comment), URLQueryItem(name: "action", value: action)]
    return parts.url
  }
  static func payload(_ url: URL) -> [String: String]? {
    guard url.scheme == "kongime-settings", url.host == "phrase", let parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return nil }
    var result = [String: String]()
    for item in parts.queryItems ?? [] {
      guard ["text", "code", "comment", "action"].contains(item.name), result[item.name] == nil, let value = item.value else { return nil }
      result[item.name] = value
    }
    guard let word = result["text"], !word.isEmpty, word.count <= 500, !word.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }),
          let code = result["code"], !code.isEmpty, code.count <= 80, code.allSatisfy({ "abcdefghijklmnopqrstuvwxyz' ".contains($0) }),
          let comment = result["comment"], comment.count <= 500,
          let action = result["action"], ["new", "edit"].contains(action) else { return nil }
    return result
  }
}

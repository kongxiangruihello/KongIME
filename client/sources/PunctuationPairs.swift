import Foundation

enum PunctuationPairs {
  static let chinese = ["(": "（）", "[": "【】", "{": "｛｝", "<": "《》", "\"": "“”", "'": "‘’"]
  static let english = ["(": "()", "[": "[]", "{": "{}", "\"": "\"\"", "'": "''"]
  static func pair(for key: String, ascii: Bool, previous: String) -> String? {
    // Preserve contractions and possessives such as don't and user's.
    if key == "'", let c = previous.last, c.isASCII && (c.isLetter || c.isNumber) { return nil }
    return (ascii ? english : chinese)[key]
  }
  static func isEmptyPair(_ text: String, ascii: Bool) -> Bool {
    (ascii ? english : chinese).values.contains(text)
  }
  static func closing(for key: String, ascii: Bool) -> String? {
    let opening = [")": "(", "]": "[", "}": "{", ">": "<", "\"": "\"", "'": "'"][key]
    return opening.flatMap { (ascii ? english : chinese)[$0]?.last.map(String.init) }
  }
  // A single nonempty replacement lets the host undo the pair/wrap as one edit.
  // Empty marked text moves the caret in document-access clients without key synthesis.
  static func move(to location: Int, replace: (String, NSRange) -> Void, locate: (NSRange) -> Void) {
    locate(NSRange(location: location, length: 0))
    replace("", NSRange(location: NSNotFound, length: 0))
  }
  static func wrap(_ pair: String, text: String, range: NSRange, replace: (String, NSRange) -> Void, locate: (NSRange) -> Void) {
    guard let first = pair.first, let last = pair.last else { return }
    replace(String(first) + text + String(last), range)
    move(to: range.location + String(first).utf16.count + text.utf16.count, replace: replace, locate: locate)
  }
  static func insert(_ pair: String, at location: Int, replace: (String, NSRange) -> Void, locate: (NSRange) -> Void) {
    wrap(pair, text: "", range: NSRange(location: location, length: 0), replace: replace, locate: locate)
  }
}

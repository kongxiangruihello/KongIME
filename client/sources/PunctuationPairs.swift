import Foundation

enum PunctuationPairs {
  static let chinese = ["(": "（）", "[": "【】", "{": "｛｝", "<": "《》", "\"": "“”", "'": "‘’"]
  static let english = ["(": "()", "[": "[]", "{": "{}", "\"": "\"\"", "'": "''"]
  static func pair(for key: String, ascii: Bool, previous: String) -> String? {
    // Preserve contractions and possessives such as don't and user's.
    if key == "'", previous.last?.isLetter == true || previous.last?.isNumber == true { return nil }
    return (ascii ? english : chinese)[key]
  }
  static func isEmptyPair(_ text: String, ascii: Bool) -> Bool {
    (ascii ? english : chinese).values.contains(text)
  }
  // Commit the pair, then use an empty marked range to locate the insertion point.
  // Replacing text before the caret alone does not move the caret inside the pair.
  static func insert(_ pair: String, at location: Int, replace: (String, NSRange) -> Void, locate: (NSRange) -> Void) {
    replace(pair, NSRange(location: location, length: 0))
    locate(NSRange(location: location + 1, length: 0))
    replace("", NSRange(location: NSNotFound, length: 0))
  }
}

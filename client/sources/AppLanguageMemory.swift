import Foundation

/// Stores only an application identifier and a Chinese/English Boolean, never text.
final class AppLanguageMemory {
  static let shared = AppLanguageMemory(defaults: UserDefaults(suiteName: "local.kongime.language-memory")!)
  private let defaults: UserDefaults
  init(defaults: UserDefaults) { self.defaults = defaults }
  func remembered(_ app: String) -> Bool? {
    guard valid(app) else { return nil }
    return defaults.object(forKey: "ascii." + app) as? Bool
  }
  func record(_ app: String, ascii: Bool, enabled: Bool) {
    guard enabled, valid(app), remembered(app) != ascii else { return }
    defaults.set(ascii, forKey: "ascii." + app)
  }
  private func valid(_ app: String) -> Bool {
    app.range(of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,199}$", options: .regularExpression) != nil && !app.hasPrefix("UnknownApp")
  }
}

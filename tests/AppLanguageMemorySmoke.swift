import Foundation
@main struct AppLanguageMemorySmoke {
 static func main() {
  let name="local.kongime.memory-test."+UUID().uuidString
  let defaults=UserDefaults(suiteName:name)!
  defer { defaults.removePersistentDomain(forName:name) }
  let store=AppLanguageMemory(defaults:defaults)
  precondition(store.remembered("com.example.Writer")==nil)
  store.record("com.example.Writer",ascii:true,enabled:false)
  precondition(store.remembered("com.example.Writer")==nil)
  store.record("com.example.Writer",ascii:true,enabled:true)
  store.record("com.example.Chat",ascii:false,enabled:true)
  let reloaded=AppLanguageMemory(defaults:UserDefaults(suiteName:name)!)
  precondition(reloaded.remembered("com.example.Writer")==true)
  precondition(reloaded.remembered("com.example.Chat")==false)
  store.record("com.example.Writer",ascii:false,enabled:true)
  precondition(reloaded.remembered("com.example.Writer")==false)
  store.record("UnknownApp1",ascii:true,enabled:true)
  precondition(store.remembered("UnknownApp1")==nil)
  print("PASS: per-application isolation, opt-in, persistence, state changes, unknown app rejection")
 }
}

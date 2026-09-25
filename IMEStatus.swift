import AppKit
import Carbon
import Foundation
func string(_ source:TISInputSource,_ key:CFString)->String{
 guard let ptr=TISGetInputSourceProperty(source,key) else{return ""}
 return Unmanaged<CFString>.fromOpaque(ptr).takeUnretainedValue() as String
}
func bool(_ source:TISInputSource,_ key:CFString)->Bool{
 guard let ptr=TISGetInputSourceProperty(source,key) else{return false}
 return CFBooleanGetValue(Unmanaged<CFBoolean>.fromOpaque(ptr).takeUnretainedValue())
}
let list=TISCreateInputSourceList(nil,true).takeRetainedValue() as! [TISInputSource]
let matches=list.filter{string($0,kTISPropertyInputSourceID).hasPrefix("im.rime.inputmethod.Squirrel")}
let current=TISCopyCurrentKeyboardInputSource().takeRetainedValue()
var result:[String:Any]=["enabled":matches.contains{bool($0,kTISPropertyInputSourceIsEnabled)},"selected":string(current,kTISPropertyInputSourceID).hasPrefix("im.rime.inputmethod.Squirrel")]
let instances=NSRunningApplication.runningApplications(withBundleIdentifier:"im.rime.inputmethod.Squirrel")
var runtimes:[[String:Any]]=[]
let root=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Rime")
for instance in instances {
 let pid=instance.processIdentifier
 let path=root.appendingPathComponent("kongime-runtime-\(pid).json")
 var row:[String:Any]=["pid":pid,"version":NSNull()]
 if let data=try? Data(contentsOf:path),let value=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
    value["pid"] as? Int32 == pid, let time=value["time"] as? Double,
    (0...35).contains(Date().timeIntervalSince1970-time),let version=value["version"] as? String,
    version.range(of:"^[0-9]+\\.[0-9]+\\.[0-9]+$",options:.regularExpression) != nil {
   row["version"]=version
 }
 runtimes.append(row)
}
result["runtimes"]=runtimes
result["screen_count"]=NSScreen.screens.count
let data=try JSONSerialization.data(withJSONObject:result)
print(String(data:data,encoding:.utf8)!)

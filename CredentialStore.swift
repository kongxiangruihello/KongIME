import Foundation
import Security
// Secrets travel over stdin/stdout, never command-line arguments or diagnostic logs.
do {
 let raw=FileHandle.standardInput.readDataToEndOfFile()
 guard let input=try JSONSerialization.jsonObject(with:raw) as? [String:Any],let account=input["account"] as? String,let op=input["op"] as? String else {exit(2)}
 let query:[String:Any]=[kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:"local.kongime.cloud.session",kSecAttrAccount as String:account]
 var output:[String:Any]=["ok":true]
 if op=="get" {
  var q=query;q[kSecReturnData as String]=true;q[kSecMatchLimit as String]=kSecMatchLimitOne
  var result:CFTypeRef?;let status=SecItemCopyMatching(q as CFDictionary,&result)
  if status==errSecSuccess,let data=result as? Data {output["value"]=try JSONSerialization.jsonObject(with:data)}
  else if status != errSecItemNotFound {throw NSError(domain:NSOSStatusErrorDomain,code:Int(status))}
 } else if op=="set" {
  guard let value=input["value"] else {exit(2)}
  let data=try JSONSerialization.data(withJSONObject:value)
  var status=SecItemUpdate(query as CFDictionary,[kSecValueData as String:data] as CFDictionary)
  if status==errSecItemNotFound {var q=query;q[kSecValueData as String]=data;q[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly;status=SecItemAdd(q as CFDictionary,nil)}
  if status != errSecSuccess {throw NSError(domain:NSOSStatusErrorDomain,code:Int(status))}
 } else if op=="delete" {
  let status=SecItemDelete(query as CFDictionary);if status != errSecSuccess && status != errSecItemNotFound {throw NSError(domain:NSOSStatusErrorDomain,code:Int(status))}
 } else {exit(2)}
 FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject:output))
} catch {FileHandle.standardError.write(Data("无法访问登录钥匙串，请重新授权或稍后重试。".utf8));exit(1)}

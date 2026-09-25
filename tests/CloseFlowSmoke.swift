import Foundation
import JavaScriptCore
@main struct CloseFlowSmoke {
 static func main() throws {
  let context=JSContext()!;var failed=false
  context.exceptionHandler={_,e in failed=true;print(e?.toString() ?? "JavaScript error")}
  context.evaluateScript(try String(contentsOfFile:CommandLine.arguments[1],encoding:.utf8))
  context.evaluateScript("""
  var finished=false;
  (async()=>{
    function check(ok){if(!ok)throw Error('close flow assertion');}
    check(await settleSettingsClose(async()=>{},()=>false,async()=>{throw Error('unexpected prompt')},async()=>{})===true);
    let dirty=true,saves=0;
    check(await settleSettingsClose(async()=>{},()=>dirty,async()=>false,async()=>{saves++;dirty=false})===false);check(saves===0&&dirty);
    check(await settleSettingsClose(async()=>{},()=>dirty,async()=>true,async()=>{saves++;dirty=false})===true);check(saves===1&&!dirty);
    let rejected=false;
    try{await settleSettingsClose(async()=>{},()=>true,async()=>true,async()=>{throw Error('disk full')})}catch(e){rejected=true}check(rejected);
    dirty=true;saves=0;
    check(await settleSettingsClose(async()=>{},()=>dirty,async()=>true,async()=>{saves++;if(saves===2)dirty=false}));check(saves===2);
    dirty=true;saves=0;
    check(!await settlePhraseDraft(()=>dirty,async()=> 'cancel',async()=>{saves++;return true},()=>{dirty=false}));check(dirty&&saves===0);
    check(await settlePhraseDraft(()=>dirty,async()=> 'discard',async()=>false,()=>{dirty=false}));check(!dirty);
    dirty=true;
    check(!await settlePhraseDraft(()=>dirty,async()=> 'save',async()=>false,()=>{dirty=false}));check(dirty);
    check(!await settlePhraseDraft(()=>dirty,async()=> 'save',async()=>true,()=>{}));check(dirty);
    check(await settlePhraseDraft(()=>dirty,async()=> 'save',async()=>{dirty=false;return true},()=>{}));
    const config={settings:{abbreviation:true},fuzzy:['z_zh','in_ing']};
    const phrases=[{code:'rq',text:'{W}',dynamic:true},{code:'yx',text:'mail',enabled:false}];
    let list=buildInputChecklist(config,phrases);
    check(list.some(x=>x.id==='abbr')&&list.some(x=>x.id==='mixed')&&list.some(x=>x.id==='fuzzy-z_zh'));
    check(list.some(x=>x.id==='phrase-rq')&&!list.some(x=>x.id==='phrase-yx'));
    config.settings.abbreviation=false;config.fuzzy=[];list=buildInputChecklist(config,phrases);
    check(list.some(x=>x.id==='abbr-off')&&!list.some(x=>x.id==='abbr')&&!list.some(x=>x.id.startsWith('fuzzy-')));
    finished=true;
  })().catch(e=>{throw e});
  """)
  precondition(!failed && context.objectForKeyedSubscript("finished").toBool(),"close flow failed")
  print("PASS: settings/phrase close, cancel, discard, save, failed save, edits during save, generated input checklist")
 }
}

// Shared by native close requests and the in-page close button.
async function settleSettingsClose(waitPending, isDirty, confirmSave, save) {
  await waitPending();
  if (!isDirty()) return true;
  if (!await confirmSave()) return false;
  while (isDirty()) await save();
  return true;
}

async function settlePhraseDraft(isDirty, choose, save, discard) {
  if (!isDirty()) return true;
  const action = await choose();
  if (action === 'discard') { discard(); return true; }
  if (action === 'save') return (await save()) === true && !isDirty();
  return false;
}

function buildInputChecklist(config, phrases) {
  const rows = [{id:'full',title:'全拼',code:'nihao',expected:'候选中应有“你好”'}];
  if(config.settings.abbreviation){
    rows.push({id:'abbr',title:'简拼',code:'nh',expected:'候选中应有“你好”，必要时展开或翻页'},
      {id:'mixed',title:'混合拼音',code:"ni'h",expected:'候选中应有“你好”'});
  } else rows.push({id:'abbr-off',title:'简拼已关闭',code:'nh',expected:'不应通过简拼产生“你好”；同名自定义短语仍可出现'});
  const examples={z_zh:['zan','zhan','站'],c_ch:['can','chan','产'],s_sh:['san','shan','山'],n_l:['nai','lai','来'],f_h:['fei','hei','黑'],an_ang:['san','sang','桑'],en_eng:['sen','seng','僧'],in_ing:['jin','jing','京']};
  for(const key of config.fuzzy){const e=examples[key];if(e)rows.push({id:'fuzzy-'+key,title:e[0]+' ↔ '+e[1],code:e[0],expected:'候选中可找到“'+e[2]+'”，必要时展开或翻页'});}
  for(const row of phrases.filter(x=>x.enabled!==false))rows.push({id:'phrase-'+row.code,title:'短语 '+row.code,code:row.code,expected:(row.dynamic?'应按本机当前时间生成：':'应出现：')+row.text});
  return rows;
}

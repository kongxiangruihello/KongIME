-- Reorder only the first 200 candidates of the exact current input.
local M = {}
function M.func(input, env)
  local code=env.engine.context.input
  local rules={};local count=0;local blocked={}
  local f=io.open(rime_api.get_user_data_dir()..'/kongime_quick.tsv','r')
  if f then
    for line in f:lines() do
      if line:sub(1,2)=="H\t" then break end
      local key,word,mode=line:match('^P\t([^\t]+)\t([^\t]+)\t([^\t]+)$')
      if mode=='block' then blocked[word]=true
      elseif key==code then rules[word]=mode;count=count+1 end
    end
    f:close()
  end
  if count==0 then for cand in input:iter() do if not blocked[cand.text] then yield(cand) end end;return end
  local first,normal,last={},{},{}
  local function flush()
    for _,list in ipairs({first,normal,last}) do for _,cand in ipairs(list) do yield(cand) end end
  end
  local n=0
  for cand in input:iter() do
    n=n+1
    if n<=200 then
      local mode=rules[cand.text]
      -- An explicit unpin skips the stable pin candidate; ordinary translation remains.
      if not blocked[cand.text] and not(mode=='unpin' and cand.quality>=100000) then
        local target=mode=='pin' and first or ((mode=='lower') and last or normal)
        table.insert(target,cand)
      end
    else
      if n==201 then flush() end
      if not blocked[cand.text] then yield(cand) end
    end
  end
  if n<=200 then flush() end
end
return M

-- Expand a validated, literal template at query time; never evaluate user code.
local M = {}
function M.init(env)
  env.templates = {}
  local file = io.open(rime_api.get_user_data_dir()..'/kongime_templates.tsv', 'r')
  if file then
    for line in file:lines() do
      local code, value, offset, label = line:match('^([a-z]+)\t([^\t]+)\t(-?%d+)\t([^\t]+)$')
      if code and value then env.templates[code] = {text=value, offset=tonumber(offset), label=label} end
    end
    file:close()
  end
end
function M.func(input, seg, env)
  if seg.start ~= 0 or input ~= env.engine.context.input then return end
  local template = env.templates[input]
  if not template then return end
  local now = os.date('*t')
  local date = os.date('*t',os.time{year=now.year,month=now.month,day=now.day+template.offset,hour=12})
  local function pad(n) return string.format('%02d', n) end
  local values = {W=({'星期日','星期一','星期二','星期三','星期四','星期五','星期六'})[date.wday],YYYY=string.format('%04d',date.year), MM=pad(date.month), M=tostring(date.month), DD=pad(date.day), D=tostring(date.day), HH=pad(now.hour), mm=pad(now.min), ss=pad(now.sec)}
  local result = template.text:gsub('{([A-Za-z]+)}',function(key) return values[key] or '{'..key..'}' end)
  local candidate = Candidate('kongime_template', seg.start, seg._end, result, template.label)
  candidate.quality = 90000
  yield(candidate)
end
return M

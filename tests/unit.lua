-- Run from the checkout: nvim --headless -u NONE -i NONE -l tests/unit.lua
local root = assert(debug.getinfo(1, "S").source:gsub("^@", ""):match("^(.*/)")) .. "../"
local common = dofile(root .. "copy-mode-common.lua")
local count = 0
local function equal(actual, expected)
  assert(vim.deep_equal(actual, expected), "expected " .. vim.inspect(expected) .. ", got " .. vim.inspect(actual))
  count = count + 1
end
local esc = string.char(27)

equal(common.title("π - terminal", "shell"), "(copy-mode) π - terminal")
equal(common.title("program", "My pane"), "(copy-mode) My pane")
equal(common.title("", "shell"), "(copy-mode) shell")
equal(common.title("a\n\7b" .. esc, "shell"), "(copy-mode) ab")
equal(common.title("(copy-mode) title", "shell"), "(copy-mode) title")
local long_title = common.title(string.rep("🎉", 200), "shell")
assert(#long_title <= 128 and vim.str_utfindex(long_title) > 0)
equal(long_title:sub(1, 12), "(copy-mode) ")

local styled = esc .. "[1;3;4;38;2;255;100;10mÅäö 🎉" .. esc .. "[0m\r\nnext\n"
equal(common.sanitize_vt(styled), styled:gsub("\r\n", "\n"))
equal(common.sanitize_vt("safe" .. esc .. "]52;c;payload\7" .. esc .. "]0;title" .. esc .. "\\"
    .. esc .. "]8;;https://example.com" .. esc .. "\\link" .. esc .. "]8;;" .. esc .. "\\"
    .. esc .. "Ppayload" .. esc .. "\\" .. esc .. "_Gimage" .. esc .. "\\end"), "safelinkend")
equal(common.sanitize_vt("before" .. esc .. "[?1049h" .. esc .. "[2J" .. esc .. "[H" .. esc .. "[6n\7\8\0after\tend"), "beforeafter\tend")
equal(common.sanitize_vt("\194\1553mitalic\194\1550m\194\15752;c;evil\194\156plain" .. esc .. "]unterminated"), esc .. "[3mitalic" .. esc .. "[0mplain")
equal(common.sanitize_vt(esc .. "(Btext" .. esc .. "[?3m" .. esc), "text")
equal(common.sanitize_vt("Åäö 🎉 日本語\194\133\n"), "Åäö 🎉 日本語\n")
local large = string.rep("Åäö large text\n", 100000)
equal(common.sanitize_vt(large), large)

local view = { windows = {{ window_id = "w", layers = {{ layout = {
  split = { before = { block_id = "a", rect = { 0, 0, 0.4, 1 } },
            after = { block_id = "b", rect = { 0.4, 0, 0.6, 1 } } },
}}}}} }
equal(common.pane_bounds(view, "w", "b"), { 0.4, 0, 0.6, 1 })
view.windows[1].zoomed_block_id = "b"
equal(common.pane_bounds(view, "w", "b"), { 0, 0, 1, 1 })

-- Exercise the actual Rex action with mocked API calls. Files are real/private;
-- format/blob_read pagination, error cleanup and direct Neovim launch are tested.
local function action_test(fail_layer, fail_capture, settings)
  settings = settings or {}
  local directory, action, request
  local bindings = {}
  local parts = { "first Åäö\r\n", "second 🎉\r\n", "last" }
  local total = #table.concat(parts)
  local offset = 0
  local deleted = false
  _G.rex = {
    action = function(definition) action = definition.run end,
    bind = function(key, target) bindings[#bindings + 1] = { key, target } end,
    json = { encode = vim.json.encode },
    layout = { block = function(options) return { block = options } end },
    exec = function(argv)
      if argv[1] == "which" then
        return { ok = true, stdout = (argv[2]:find("/") and argv[2] or "/test/bin/" .. argv[2]) .. "\n" }
      elseif argv[1] == "mktemp" then
        directory = assert(vim.uv.fs_mkdtemp(vim.fn.stdpath("cache") .. "/rex-copy-mode-XXXXXXXX"))
        return { ok = true, stdout = directory .. "\n" }
      elseif argv[1] == "chmod" then
        assert(vim.uv.fs_chmod(argv[3], 384))
        assert(vim.uv.fs_chmod(argv[4], 384))
        return { ok = true }
      elseif argv[1] == "rmdir" then
        deleted = vim.uv.fs_rmdir(argv[2]) ~= nil
        return { ok = deleted }
      end
      error("Unexpected subprocess: " .. vim.inspect(argv))
    end,
    block = { call = function(creator, method, params)
      equal(creator, "com.superlogical.terminal")
      equal(params.session_id, "session:test")
      equal(params.block_id, "block:test")
      if method == "title" then return { title = "Native test" } end
      if method == "format" then
        if fail_capture then return nil, "fixture capture failure" end
        offset = #parts[1]
        return { content = parts[1], id = 91, total = total } -- older format reply without eof
      end
      equal(method, "blob_read")
      equal(params.args.id, 91)
      equal(params.args.offset, offset) -- byte offsets, not Unicode character counts
      local part = offset == #parts[1] and parts[2] or parts[3]
      offset = offset + #part
      return { id = 91, data = part, total = total, eof = offset == total }
    end },
    session = {
      describe_block = function() return { block = { creator_name = "com.superlogical.terminal", window_id = "w", label = "shell" } } end,
      view = function() return { windows = {{ window_id = "w", layers = {{ layout = { block_id = "block:test", rect = { 0, 0, 1, 1 } } }} }} } end,
      new_layer = function(options)
        request = options
        equal(vim.fn.readfile(directory .. "/capture.vt", "b"), { "first Åäö\r", "second 🎉\r", "last", "" })
        equal(vim.uv.fs_stat(directory).mode % 512, 448) -- 0700
        equal(vim.uv.fs_stat(directory .. "/capture.vt").mode % 512, 384) -- 0600
        local command = options.layout.block.options.command
        equal(command[1], settings.nvim or "/test/bin/nvim")
        local metadata = vim.json.decode(table.concat(vim.fn.readfile(directory .. "/meta.json"), "\n"))
        equal(metadata.rex_cli, settings.rex or "/test/bin/rex")
        equal(metadata.copy_key, settings.copy_key == nil and "<CR>" or settings.copy_key)
        equal(metadata.toast_seconds, settings.toast_seconds or 1.2)
        equal(vim.uv.fs_stat(directory .. "/meta.json").mode % 512, 384)
        assert(not table.concat(command, " "):find("python", 1, true))
        if fail_layer then return nil, "fixture layer failure" end
        return { layer_id = "layer:test", block_ids = { "block:viewer" } }
      end,
    },
  }
  dofile(root .. "copy-mode.lua").setup(settings)
  if settings.key == false then
    equal(#bindings, 0)
  else
    equal(bindings, {{ settings.key or "ctrl+a>enter", "copy_mode" }})
  end
  local ok, result = pcall(action, { session_id = "session:test", block_id = "block:test", origin = "cli" }, {})
  if fail_layer or fail_capture then
    equal(ok, false)
    equal(deleted, true)
    equal(vim.uv.fs_stat(directory), nil)
  else
    equal(ok, true)
    equal(result.layer_id, "layer:test")
    equal(request.layout.block.label, "(copy-mode) Native test")
  end
  if directory then vim.fn.delete(directory, "rf") end
end

action_test(false, false)
action_test(true, false)
action_test(false, true)
action_test(false, false, { key = "ctrl+b>enter", copy_key = "<C-y>", toast_seconds = 2,
  nvim = "/custom path/nvim", rex = "/custom path/rex" })
action_test(false, false, { key = false, copy_key = false, toast_seconds = 0 })
local module = dofile(root .. "copy-mode.lua")
for _, invalid in ipairs({ { bogus = true }, { key = "" }, { copy_key = 3 }, { nvim = "" },
    { rex = false }, { toast_seconds = -1 }, { toast_seconds = 0/0 }, { toast_seconds = math.huge } }) do
  equal(pcall(module.setup, invalid), false)
end
rex.exec = function() return nil, "fixture executable missing" end
equal(pcall(module.setup), false)
-- A broken startup must exit instead of waiting at an error prompt, and its
-- already-installed VimLeavePre hook must still remove the private snapshot.
local broken = assert(vim.uv.fs_mkdtemp(vim.fn.stdpath("cache") .. "/rex-copy-mode-XXXXXXXX"))
vim.fn.writefile({ "{}" }, broken .. "/meta.json")
vim.fn.writefile({ "startup fixture" }, broken .. "/capture.vt")
local failed = vim.system({
  vim.v.progpath, "--headless", "-u", "NONE", "-i", "NONE", "-n",
  "--cmd", "lua vim.g.rex_copy_mode_directory = " .. string.format("%q", broken),
  "-c", "lua dofile(" .. string.format("%q", root .. "copy-mode-view.lua") .. ")",
}, { timeout = 5000 }):wait()
equal(failed.code, 1)
equal(vim.uv.fs_stat(broken), nil)
print("PASS: " .. count .. " native Lua assertions (filtering, Unicode/title, geometry, pagination, private files, action/startup failure cleanup, direct Neovim launch)")

-- Disposable-session test entry point; does not change the running config.
local root = assert(debug.getinfo(1, "S").source:gsub("^@", ""):match("^(.*/)")) .. "../"
dofile(root .. "copy-mode.lua").setup()

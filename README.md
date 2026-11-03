# Rex copy-mode

Keyboard-only, styled scrollback for Rex, using a disposable Neovim overlay. Works independently of Pi, Claude Code, Codex, or the program running in your terminal.

- **Ctrl+A, then Enter** opens the focused pane's scrollback.
- Navigate/search with Vim keys; select with `v`, `V`, or `Ctrl+V`.
- **Enter in visual mode** copies the selection to the system clipboard and returns to the source pane.
- `y` copies without closing; `:q` cancels.
- A small **Copied to clipboard** notice appears at the bottom after copying and exiting.

Colors, bold, italics and underline are preserved. The overlay matches the source pane, including nested splits, floating panes and zoom. Source applications keep running untouched. Neovim runs without user config, plugins, history or swap files.

## Requirements

Currently tested on **macOS**, Rex Beta **0.1.0 (1758)** / server **0.0.1793645657-gd018d2**, API revision 10, and **Neovim 0.12.2**. Other versions/platforms are not yet verified.

Requires Rex's Lua actions, floating-layer and terminal capture APIs; Neovim's `vim.system`, `vim.uv` and `nvim_open_term` APIs; and standard `which`, `mktemp`, `chmod`, `rmdir`, and `sleep` utilities. Clipboard copying uses Neovim's clipboard provider (normally `pbcopy` on macOS).

**No Python runtime dependency.** Python 3 is only used by optional integration tests.

## Installation

An AI assistant can follow [AGENTS.md](AGENTS.md). Manual installation:

1. Check your existing Rex config and keymap. Back up files before changing them; the default shortcut may already be bound.
2. From this checkout, copy **all three runtime files** into your Rex configuration directory:

   ```sh
   mkdir -p "$HOME/.config/rex"
   cp copy-mode.lua copy-mode-common.lua copy-mode-view.lua "$HOME/.config/rex/"
   ```

   Inspect existing destination files before overwriting them. The default config location above may differ on your setup.

3. Add this to your existing `init.lua`—do not replace the rest of the file:

   ```lua
   require("copy-mode").setup()
   ```

4. Validate, then reload:

   ```sh
   rex config check
   rex config reload
   ```

The files find one another relative to their own location; no username, Homebrew prefix, or configuration directory is hardcoded. If keeping them elsewhere, keep all three together and use an **absolute path**:

```lua
dofile("/absolute/path/to/rex-copy-mode/copy-mode.lua").setup()
```

Call `setup` once per config load. It registers the `copy_mode` action, also available from the command palette or `rex do copy_mode`.

## Configuration

All options are optional. These are the defaults:

```lua
require("copy-mode").setup({
  key = "ctrl+a>enter", -- Rex shortcut; false disables automatic binding
  copy_key = "<CR>",   -- Neovim visual-mode copy-and-exit key; false disables it
  nvim = "nvim",       -- executable name or absolute path
  rex = "rex",         -- executable name or absolute path
  toast_seconds = 1.2, -- 0 disables the confirmation notice
})
```

For example, choose another Rex prefix with `key = "ctrl+b>enter"`, or copy-and-exit with `copy_key = "<C-y>"`.

Executable names are resolved **once during setup** using Rex's command environment, then passed as absolute paths to the terminal launcher. Rex's launcher and app-side config loader can have a narrower PATH than your interactive shell. **A CLI config check can pass while an app-side reload fails**, so check both results. If lookup fails, configure explicit paths for both executables: `nvim` might be `/opt/homebrew/bin/nvim`, while `rex` may be inside the installed Rex Server app bundle. Locate your actual paths rather than copying someone else's. This adds no executable lookup to the live opening path.

The confirmation is a non-focused, short-lived floating pane using only its title line, not a native Rex toast. It is suppressed if you switched away before closing copy-mode. Ordinary `:q` does not trigger it.

## Limitations and safety

- Full-screen/alternate-screen applications generally expose **only their current screen**, not their entire conversation/history. Use regular terminal output where available.
- This is a snapshot, not a live-updating view. Pane geometry is sampled on opening, not continuously tracked while resizing.
- Rex stores roughly 64 MiB of terminal history; older output may already be gone. Capture is bounded to 128 MiB and the viewer to 100,000 scrollback lines.
- Only printable text, tabs/newlines and SGR styling are replayed. OSC/DCS, title/clipboard commands, cursor controls, and device queries in captured output are stripped.
- Captures are private temporary directories (`0700`, files `0600`) and are removed on normal exit and handled startup failure. Forced kills/power loss can leave private `rex-copy-mode-*` directories in the system temp directory. Captures can contain sensitive terminal output; do not commit them or share them in bug reports.
- Focus/zoom restoration is best effort and avoids stealing focus if you switched panes/tabs. Remote-host and multi-client configurations have not been verified.
- The extension does not install or update software, modify the source application's input, or change your Neovim configuration.

## Tests

From the checkout:

```sh
nvim --headless -u NONE -i NONE -l tests/unit.lua
python3 tests/integration.py --stress
python3 tests/geometry.py
python3 tests/copy_enter.py
```

The integration tests require a running local Rex server. They create and close their own disposable sessions without selecting them in the app, reloading your config, or overwriting your clipboard. Clipboard tests use a fake provider. Run them sequentially; snapshot checks assume no other test or copy-mode capture starts concurrently.

After installation, `python3 tests/integration.py --live` also checks the configured server action. That test expects the default behavior. Tests use standard-library Python only, with no test framework or package installation.

## Uninstall

Remove the `require("copy-mode").setup(...)` or `dofile(...).setup(...)` call and any manual `copy_mode` keybindings. Validate and reload the config, then remove only the three installed module files/symlinks. Preserve unrelated files and changes.

## License

[MIT](LICENSE). Copyright © 2026 Johan Isacsson.

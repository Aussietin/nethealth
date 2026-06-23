# nethealth

A personal network health diagnostic tool for the terminal. Run one-shot checks, get a live monitoring TUI, test your download speed, and generate reports — no browser, no server, no setup friction.

```
nethealth tui 1.1.1.1 google.com cloudflare.com
```

---

## Install

### Linux Mint (or any Linux with pipx)

```bash
pipx install git+https://github.com/Aussietin/nethealth
```

Done. `nethealth` is now on your PATH globally.

**Shell completion:**

```bash
# bash — add to ~/.bashrc
eval "$(_NETHEALTH_COMPLETE=bash_source nethealth)"

# zsh — add to ~/.zshrc
eval "$(env _NETHEALTH_COMPLETE=zsh_source nethealth)"
```

### WSL2 / Ubuntu (dev machine)

```bash
git clone https://github.com/Aussietin/nethealth
cd nethealth
python3 -m venv .venv && .venv/bin/pip install -e .
```

Then add to `~/.zshrc`:

```bash
# nethealth CLI
export PATH="/home/austin/dev/projects/nethealth/.venv/bin:$PATH"

# shell completion
eval "$(env _NETHEALTH_COMPLETE=zsh_source nethealth)"
```

**Windows Terminal desktop shortcut** — right-click the desktop → New Shortcut, target:

```
wt.exe wsl -e bash -c "source ~/.zshrc; nethealth tui; exec zsh"
```

### Requirements

- Python 3.9+
- `ping` utility on PATH (standard on all Linux/WSL)
- `iw` for WiFi info: `sudo apt install iw` (optional)

---

## Commands

### TUI — live monitor

```bash
nethealth tui                              # defaults: google.com + 1.1.1.1
nethealth tui 8.8.8.8 cloudflare.com      # custom targets
```

Keybindings: `r` refresh · `t` add target · `q` quit

Live status table (DNS / Ping / HTTP / Port), ping sparklines with latency history and packet loss %, scrolling log panel.

### Full check suite

```bash
nethealth check google.com
nethealth check google.com --json          # raw JSON
nethealth check google.com --save json     # append to ~/.nethealth/history.json
nethealth check google.com --save csv      # append to ~/.nethealth/history.csv
nethealth check google.com --skip-traceroute
```

### Individual checks

```bash
nethealth dns 1.1.1.1
nethealth ping 1.1.1.1
nethealth http google.com
nethealth port google.com --ports 80,443,8080
nethealth traceroute google.com --max-hops 20
```

### Speed test

```bash
nethealth speed                # 10 MB download from Cloudflare
nethealth speed --size 25      # larger sample for more accurate result
nethealth speed --json
```

### WiFi info

```bash
nethealth wifi                 # SSID, signal dBm, band, TX rate
```

Requires `iw` (`sudo apt install iw`). Reports gracefully in WSL2 where the host WiFi adapter is not exposed.

### Long-running ping monitor

```bash
nethealth monitor ping --targets 1.1.1.1,google.com --interval 1 --duration 300
```

Logs per-target to `nethealth-logs/`. Ctrl-C for a clean summary.

### Report

```bash
nethealth report               # summary of all saved history
nethealth report --target google.com
nethealth report --last 50     # most recent 50 runs only
nethealth report --json
```

Reads from `~/.nethealth/history.json`. Populate it with `nethealth check --save json`.

### Packet sniffer

```bash
sudo nethealth sniffer --interface any --count 8
```

Captures raw Ethernet frames, parses IPv4/TCP/UDP/ICMP headers. Requires root.

---

## Project structure

```
nethealth/
├── nethealth/
│   ├── checks/         # dns, ping, http, port, traceroute, speed, wifi, ping_monitor, packet_sniffer
│   ├── cli.py          # Click entry point
│   ├── tui.py          # Textual TUI
│   ├── output.py       # shared Rich formatting
│   └── report.py       # history aggregation
└── pyproject.toml
```

---

## Extending

Adding a new check:

1. Create `nethealth/checks/mycheck.py` — return a dict with at least `{"name": "…", "status": "ok"|"fail"}`
2. Import and call it in `cli.py`
3. Optionally wire it into the TUI status table in `tui.py`

---

## License

MIT
# nethealth demo — record with: vhs demo.tape
Output demo.gif
Set Shell "zsh"
Set FontSize 14
Set Width 1100
Set Height 600
Set Theme "One Half Dark"
Set Framerate 30
Set PlaybackSpeed 1.0

# --- quick checks ---
Type "nethealth check google.com --skip-traceroute"
Enter
Sleep 4s

Type "nethealth ssl github.com"
Enter
Sleep 2s

Type "nethealth speed"
Enter
Sleep 12s

Type "nethealth wifi"
Enter
Sleep 1.5s

# --- TUI ---
Type "nethealth tui google.com 1.1.1.1 cloudflare.com"
Enter
Sleep 6s

# switch to Log tab
Type "2"
Sleep 2s

# switch to Report tab
Type "3"
Sleep 2s

# back to Monitor
Type "1"
Sleep 2s

# add a target live
Type "t"
Sleep 1s
Type "8.8.8.8"
Enter
Sleep 4s

Type "q"
Sleep 1s

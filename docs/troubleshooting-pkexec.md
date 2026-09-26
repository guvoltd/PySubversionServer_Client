# "No password prompt appears" for privileged actions (Debian 13 and others)

SVN Server Admin uses `pkexec` for anything that needs root (creating a
repository under a root-owned path, importing a dump file, adding a
firewall rule, installing the systemd unit, etc.). `pkexec` itself never
draws a password dialog — it hands that job to whatever **PolicyKit
authentication agent** is registered in your desktop session. If no agent
is running, `pkexec` has nothing to show the prompt through and just fails
immediately, with **no visible dialog of any kind** — not even an error, if
you're not looking at the app's own output window.

This is a very common situation on Debian 13 (Trixie), particularly on
minimal installs, Xfce, LXQt, or any desktop that doesn't pull in a
GNOME/KDE session by default — the agent packages usually aren't installed
automatically.

## Check whether an agent is running

```bash
ps aux | grep -iE 'polkit-gnome|polkit-kde|lxqt-policykit|lxpolkit|mate-polkit'
```

If that prints nothing (besides your `grep`), you don't have an agent
running — that's the cause.

## Install one for your desktop

| Desktop | Package |
|---|---|
| GNOME | `policykit-1-gnome` |
| KDE Plasma | `polkit-kde-agent-1` |
| Xfce | `lxpolkit` (there's no Xfce-specific package; this is what Xfce installs commonly use) |
| LXQt | `lxqt-policykit` |
| MATE | `mate-polkit` |
| Anything else / window managers (i3, sway, ...) | `lxpolkit` or `lxqt-policykit` both work fine standalone |

```bash
sudo apt install lxpolkit   # example: pick the row matching your desktop
```

## Make sure it actually starts with your session

Installing the package is usually enough — most of these register an
autostart `.desktop` entry under `/etc/xdg/autostart/` that your session
picks up on next login. **Log out and back in** (or reboot) after
installing.

If it still isn't running after that, start it manually to confirm it
fixes things, then look into why your session isn't running its autostart
entries:

```bash
lxpolkit &   # or whichever agent you installed above; check `dpkg -L <package>` for its exact binary path
```

## Verify

Re-run the action in SVN Server Admin. You should now see a graphical
authentication window pop up before the app's own output dialog proceeds.

## If you're packaging/distributing this app yourself

`svn_server/debian/control` declares `policykit-1` as a hard dependency
(needed for `pkexec` to exist at all) and lists the common desktop agents
above as `Recommends` alternatives, so a plain `sudo apt install
./svn-server-admin_*.deb` pulls one in by default. If you installed with
`apt --no-install-recommends`, or via the portable AppImage/pip-wheel path
(see `docs/installing-from-wheel.md`), that automatic pull-in doesn't
happen and you'll need to install an agent yourself as above.

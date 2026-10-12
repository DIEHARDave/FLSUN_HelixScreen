# FLSUN_HelixScreen

Runs [HelixScreen](https://github.com/prestonbrown/helixscreen) on the **FLSun T1 Pro**'s touchscreen in place of FLSun's stock screen, and keeps it up to date from Mainsail's and Fluidd's update manager.

It installs HelixScreen's official `flsun-t1` release. Install it on its own, or through [FLSUN_Updater](https://github.com/DIEHARDave/FLSUN_Updater) by setting `flsun_helixscreen: yes` in `flsun_plugins.cfg`.

## Install

SSH into the printer as `pi` (the default password is `1`), then:

```sh
sudo ntpdate -u -b time.google.com
curl -fsSL --cacert /etc/ssl/certs/ca-certificates.crt https://raw.githubusercontent.com/DIEHARDave/FLSUN_HelixScreen/main/prepare.sh | bash
cd ~
git clone https://github.com/DIEHARDave/FLSUN_HelixScreen.git
~/FLSUN_HelixScreen/install.sh
```

The first two commands set the clock and repair certificates and git so that `git clone` works. Skip them if another FLSun plugin is already installed.

The installer downloads the newest HelixScreen release for the T1 Pro and switches the screen over. If HelixScreen is already installed, it keeps the installed version unless the pinned release is newer.

To install a package you built yourself (`make flsun-t1-docker && make release-flsun-t1` in HelixScreen), copy it to the printer and run:

```sh
~/FLSUN_HelixScreen/install.sh --local ~/helixscreen-flsun-t1-v1.1.0-beta.7.tar.gz
```

## Updates

When HelixScreen publishes a release that includes a T1 Pro package, **FLSUN_HelixScreen** shows an update in the update manager (**Machine** page in Mainsail, **Settings → Software Updates** in Fluidd). The update's commit message names the HelixScreen version. Installing it downloads that release, keeps your settings, and restarts the screen. If a print is running, the printer waits until it finishes.

Choose the release channel in **flsun_helixscreen.cfg**:

```ini
[helixscreen]
channel: stable   # or beta
```

Saving the file applies it. Until a stable HelixScreen release supports the T1 Pro, `stable` follows `beta`. Changing channels never downgrades.

HelixScreen's own **Moonraker update entry** (`[update_manager helixscreen]`) must not be used on the T1 Pro. FLSun's older Moonraker can't pick the right release file, so an update from it deletes HelixScreen and then fails. HelixScreen's installer already leaves it out on this Moonraker.

## What it changes

| File | Change |
| --- | --- |
| `/home/pi/helixscreen` | HelixScreen, owned by root. Updates keep `config/settings.json`, `config/helixscreen.env` and your other files in `config/`, the same way HelixScreen's own installer does. The previous version is kept in `/home/pi/helixscreen.old`. |
| `/home/pi/qt/out_linux/startboot.sh` | Starts HelixScreen at boot. FLSun's script is kept as `startboot.sh.flsun`, and it still starts the stock screen if HelixScreen is missing. The script is put back at every boot if a FLSun firmware update replaced it. |
| `flsun_helixscreen.service` | Installs the pinned release at boot, when `flsun_helixscreen.cfg` is saved (`flsun_helixscreen.path`), and after an update. |
| `~/printer_data/config/flsun_helixscreen.conf` | Update manager entry |
| `~/printer_data/config/flsun_helixscreen.cfg` | Settings |
| `~/printer_data/config/moonraker.conf` | Adds `[include flsun_helixscreen.conf]` (a backup is saved first) |
| `~/printer_data/moonraker.asvc` | Adds `flsun_helixscreen`, so the update manager can run the service after an update |
| Clock, certificates, git | The same system fixes as the other FLSun plugins, with the same files |

`~/FLSUN_HelixScreen/flsun_helixscreen.py status` shows the installed version, the channel, and the pinned releases.

## How updates reach printers

A [scheduled workflow](.github/workflows/track-releases.yml) checks HelixScreen's releases every six hours. When a newer one includes `helixscreen-flsun-t1-<version>.tar.gz`, the workflow writes its version to `versions/stable` or `versions/beta` and commits. Moonraker sees the commit as an update. After updating, it restarts `flsun_helixscreen.service`, which downloads and installs that version.

GitHub pauses scheduled workflows in repos with no activity for 60 days. If updates stop arriving, re-enable the workflow on the repo's **Actions** tab.

## Uninstall

```sh
~/FLSUN_HelixScreen/uninstall.sh
rm -rf ~/FLSUN_HelixScreen
```

The uninstaller puts FLSun's stock screen back and deletes HelixScreen. HelixScreen's settings are kept in `~/helixscreen-config.bak`. Through FLSUN_Updater, set `flsun_helixscreen: no` instead.

## License

GPL-3.0, the same as HelixScreen. See [LICENSE](LICENSE).

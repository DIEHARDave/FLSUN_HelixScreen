# FLSUN_HelixScreen (retired)

**This project is no longer maintained.** To run [HelixScreen](https://github.com/prestonbrown/helixscreen) on the FLSun T1 Pro, use the `helixscreen` plugin in [FLSUN_Updater](https://github.com/DIEHARDave/FLSUN_Updater) instead.

FLSUN_HelixScreen waited for HelixScreen to publish a T1 Pro package (`helixscreen-flsun-t1`). There won't be one: HelixScreen's developer doesn't want a separate build for each board. FLSUN_Updater instead installs HelixScreen's official build for the Elegoo Centauri Carbon, which runs on the T1 Pro unchanged, and sets it up for the T1 Pro's screen. Its README explains how: [HelixScreen on the T1 Pro uses the Centauri Carbon build](https://github.com/DIEHARDave/FLSUN_Updater#helixscreen-on-the-t1-pro-uses-the-centauri-carbon-build).

## Switching to FLSUN_Updater

If FLSUN_HelixScreen is installed, SSH into the printer as `pi` (the default password is `1`) and remove it first:

```sh
~/FLSUN_HelixScreen/uninstall.sh
rm -rf ~/FLSUN_HelixScreen
```

The uninstaller removes HelixScreen and puts FLSun's stock screen back. It keeps HelixScreen's settings in `~/helixscreen-config.bak`.

Then [install FLSUN_Updater](https://github.com/DIEHARDave/FLSUN_Updater#install) if you don't have it, and set `helixscreen: yes` in `flsun_plugins.cfg`. HelixScreen is installed within a few seconds and is already set up for the T1 Pro's touchscreen. From then on, its updates appear in the update manager as **helixscreen**.

## License

GPL-3.0, the same as HelixScreen. See [LICENSE](LICENSE).

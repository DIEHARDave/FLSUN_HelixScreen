#!/usr/bin/env python3
"""FLSUN_HelixScreen: runs HelixScreen on the FLSun T1 Pro's touchscreen.

    flsun_helixscreen.py apply          Install or upgrade to the release
                                        pinned in versions/, and make sure
                                        the screen starts HelixScreen at
                                        boot. What the flsun_helixscreen
                                        service runs.
    flsun_helixscreen.py install FILE   Install a helixscreen-flsun-t1
                                        package from a local file.
    flsun_helixscreen.py remove         Put FLSun's stock screen back and
                                        delete HelixScreen.
    flsun_helixscreen.py status         Show the installed and pinned
                                        versions.

All but status need root. Standard library only: the T1 Pro has Python 3.7
and no pip.
"""

import argparse
import configparser
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

REPO_DIR = os.path.dirname(os.path.realpath(__file__))
UPSTREAM = "prestonbrown/helixscreen"
PLATFORM = "flsun-t1"
HOME = "/home/pi"
HELIX_DIR = os.path.join(HOME, "helixscreen")
HELIX_NEW = HELIX_DIR + ".new"
HELIX_OLD = HELIX_DIR + ".old"
HELIX_STATE = os.path.join(HOME, "helixscreen-state")
QT_DIR = os.path.join(HOME, "qt", "out_linux")
STARTBOOT = os.path.join(QT_DIR, "startboot.sh")
STARTBOOT_FLSUN = STARTBOOT + ".flsun"
HOOK = os.path.join(REPO_DIR, "system", "startboot.sh")
SETTINGS = os.path.join(HOME, "printer_data", "config", "flsun_helixscreen.cfg")
DOWNLOAD = os.path.join(HOME, "helixscreen-download.tar.gz")
SCREEN_UNIT = "flsun-screen"
LOCK = "/run/flsun_helixscreen.lock"
MOONRAKER = "http://127.0.0.1:7125"

# Mirrors upstream's installer (scripts/lib/installer/release.sh): these two
# always come from the old install; anything else in the old config/ that the
# new package doesn't ship is carried over, minus these.
KEEP_ALWAYS = ("settings.json", "helixscreen.env")
NEVER_KEEP = {
    "crash.txt", "crash_report.txt", ".crash_restart_count",
    ".helix-fresh-install", "printer_database.json", "printing_tips.json",
    "default_layout.json", "helix_macros.cfg", "presets",
    "print_start_profiles", "sounds", "platform",
}


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def require_root():
    if os.geteuid() != 0:
        sys.exit("needs root: sudo %s" % " ".join(sys.argv))


# ------------------------------------------------------------------ versions

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")


def version_key(tag):
    """Sort key for vX.Y.Z[-pre.N]; a release sorts above its prereleases."""
    m = VERSION_RE.match(tag or "")
    if not m:
        return None
    pre = m.group(4)
    if pre is None:
        pre_key = (1,)
    else:
        pre_key = (0,) + tuple(
            (0, int(p), "") if p.isdigit() else (1, 0, p)
            for p in pre.split("."))
    return tuple(int(g) for g in m.group(1, 2, 3)) + (pre_key,)


def newer(a, b):
    """True if version a is newer than b (b may be None)."""
    ka = version_key(a)
    if ka is None:
        return False
    kb = version_key(b)
    return kb is None or ka > kb


def pinned(name):
    try:
        with open(os.path.join(REPO_DIR, "versions", name)) as f:
            tag = f.read().strip()
    except FileNotFoundError:
        return None
    return tag if version_key(tag) else None


def channel():
    parser = configparser.ConfigParser()
    try:
        parser.read(SETTINGS)
        value = parser.get("helixscreen", "channel", fallback="stable")
    except configparser.Error as e:
        log("Can't read %s (%s); using the stable channel" % (SETTINGS, e))
        return "stable"
    value = value.strip().lower()
    if value not in ("stable", "beta"):
        log("Unknown channel '%s' in %s; using stable" % (value, SETTINGS))
        return "stable"
    return value


def target_version():
    stable, beta = pinned("stable"), pinned("beta")
    if channel() == "beta":
        return beta if newer(beta, stable) else stable
    if stable is None and beta is not None:
        log("No stable HelixScreen release supports the T1 Pro yet; "
            "following beta")
        return beta
    return stable


def installed_version(root=HELIX_DIR):
    try:
        with open(os.path.join(root, "release_info.json")) as f:
            return json.load(f).get("version")
    except (FileNotFoundError, ValueError):
        return None


# ------------------------------------------------------------------ printing

def print_state():
    try:
        url = MOONRAKER + "/printer/objects/query?print_stats=state"
        with urllib.request.urlopen(url, timeout=5) as resp:
            res = json.loads(resp.read().decode())
        return res["result"]["status"]["print_stats"]["state"]
    except (OSError, ValueError, KeyError):
        return None


def wait_until_idle():
    """Restarting the screen mid-print is harmless to the print, but the
    screen would vanish while someone may be using it."""
    waiting = False
    while print_state() in ("printing", "paused"):
        if not waiting:
            log("A print is running; waiting for it to finish")
            waiting = True
        time.sleep(60)


# ---------------------------------------------------------------- the screen

def process_args(pid):
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as f:
            return [a.decode(errors="replace")
                    for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def screen_pids():
    """HelixScreen's processes (launcher, watchdog, splash, screen) and
    FLSun's stock TUI. Matched by program path, never by a loose pattern."""
    helix_bin = HELIX_DIR + "/bin/"
    pids = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        args = process_args(pid)
        if not args:
            continue
        prog = args[1] if (os.path.basename(args[0]) == "sh"
                           and len(args) > 1) else args[0]
        if prog.startswith(helix_bin) or prog == os.path.join(QT_DIR, "TUI"):
            pids.append(int(pid))
    return pids


def stop_screen():
    subprocess.call(["systemctl", "stop", SCREEN_UNIT + ".service"],
                    stderr=subprocess.DEVNULL)
    subprocess.call(["systemctl", "reset-failed", SCREEN_UNIT + ".service"],
                    stderr=subprocess.DEVNULL)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = screen_pids()
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        time.sleep(3)


def start_screen():
    """Starts the screen the way rc.local does at boot. A transient unit
    keeps it alive after this script exits; RemainAfterExit keeps FLSun's
    TUI, which its start script backgrounds, from being killed."""
    log("Starting the screen")
    subprocess.call([
        "systemd-run", "--unit=" + SCREEN_UNIT, "-p", "RemainAfterExit=yes",
        "--description=Touchscreen (restarted by FLSUN_HelixScreen)",
        STARTBOOT], stdout=subprocess.DEVNULL)


def restart_screen():
    stop_screen()
    start_screen()


def is_helix_hook(path):
    try:
        with open(path) as f:
            return "helix-launcher" in f.read()
    except OSError:
        return False


def install_hook():
    """Makes FLSun's boot script start HelixScreen. Returns True if it
    changed. FLSun firmware updates can put the stock script back."""
    if not os.path.isdir(QT_DIR):
        log("WARNING: %s not found; HelixScreen won't start at boot" % QT_DIR)
        return False
    with open(HOOK) as f:
        hook = f.read()
    try:
        with open(STARTBOOT) as f:
            if f.read() == hook:
                return False
    except FileNotFoundError:
        pass
    if os.path.exists(STARTBOOT) and not is_helix_hook(STARTBOOT):
        # The stock script, possibly a newer one from a firmware update.
        log("Keeping FLSun's screen start script as " + STARTBOOT_FLSUN)
        shutil.copy2(STARTBOOT, STARTBOOT_FLSUN)
    if not os.path.exists(STARTBOOT_FLSUN):
        log("WARNING: FLSun's start script is missing; if HelixScreen is "
            "removed the screen will stay blank")
    log("Setting the screen to start HelixScreen at boot")
    tmp = STARTBOOT + ".tmp"
    with open(tmp, "w") as f:
        f.write(hook)
    os.chmod(tmp, 0o755)
    os.replace(tmp, STARTBOOT)
    return True


def remove_hook():
    if not os.path.exists(STARTBOOT_FLSUN):
        log("WARNING: %s is missing; can't restore the stock screen"
            % STARTBOOT_FLSUN)
        return False
    log("Setting the screen to start FLSun's stock screen at boot")
    shutil.copy2(STARTBOOT_FLSUN, STARTBOOT)
    return True


# ------------------------------------------------------------- installation

def run(cmd):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True)
    if res.returncode != 0:
        raise RuntimeError("%s failed: %s" % (cmd[0], res.stdout.strip()))


def check_package(path):
    """Raises unless path is a HelixScreen package for this printer."""
    try:
        with tarfile.open(path) as tar:
            names = set(tar.getnames())
    except (tarfile.TarError, OSError) as e:
        raise RuntimeError("%s is not a readable package: %s" % (path, e))
    for need in ("helixscreen/bin/helix-launcher.sh",
                 "helixscreen/bin/helix-screen",
                 "helixscreen/release_info.json"):
        if need not in names:
            raise RuntimeError("%s is not a HelixScreen package (no %s)"
                               % (path, need))


def copy_item(src, dst):
    if os.path.isdir(src) and not os.path.islink(src):
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst, follow_symlinks=False)


def keep_user_config(old_cfg, new_cfg):
    if not os.path.isdir(old_cfg):
        return
    for name in KEEP_ALWAYS:
        src = os.path.join(old_cfg, name)
        if os.path.lexists(src):
            dst = os.path.join(new_cfg, name)
            if os.path.lexists(dst):
                os.remove(dst)
            copy_item(src, dst)
    for name in os.listdir(old_cfg):
        if (name in KEEP_ALWAYS or name in NEVER_KEEP
                or re.match(r"crash_.*\.txt$", name)):
            continue
        src, dst = os.path.join(old_cfg, name), os.path.join(new_cfg, name)
        if not os.path.lexists(dst):
            copy_item(src, dst)
        elif os.path.isdir(src) and os.path.isdir(dst):
            # Merge user additions into directories the package also ships.
            for sub in os.listdir(src):
                if name == "themes" and sub == "defaults":
                    continue
                if not os.path.lexists(os.path.join(dst, sub)):
                    copy_item(os.path.join(src, sub), os.path.join(dst, sub))


def install_package(path):
    """Installs a helixscreen-flsun-t1 tarball, keeping the user's settings,
    and restarts the screen."""
    check_package(path)
    shutil.rmtree(HELIX_NEW, ignore_errors=True)
    os.makedirs(HELIX_NEW)
    staging = HELIX_NEW + "/extract"
    os.makedirs(staging)
    run(["tar", "xzf", path, "--no-same-owner", "-C", staging])
    os.rename(os.path.join(staging, "helixscreen"), HELIX_NEW + "/helixscreen")
    shutil.rmtree(staging)
    new_root = HELIX_NEW + "/helixscreen"
    version = installed_version(new_root) or "unknown version"
    log("Installing HelixScreen %s" % version)
    keep_user_config(os.path.join(HELIX_DIR, "config"),
                     os.path.join(new_root, "config"))
    # The launcher refuses config/helixscreen.env unless the install is
    # root-owned and not group- or world-writable.
    run(["chown", "-R", "root:root", new_root])
    run(["chmod", "-R", "go-w", new_root])

    wait_until_idle()
    stop_screen()
    shutil.rmtree(HELIX_OLD, ignore_errors=True)
    if os.path.exists(HELIX_DIR):
        os.rename(HELIX_DIR, HELIX_OLD)
    os.rename(new_root, HELIX_DIR)
    shutil.rmtree(HELIX_NEW, ignore_errors=True)
    install_hook()
    start_screen()
    log("HelixScreen %s installed; the previous version is in %s"
        % (version, HELIX_OLD) if os.path.exists(HELIX_OLD) else
        "HelixScreen %s installed" % version)


def download(tag):
    asset = "helixscreen-%s-%s.tar.gz" % (PLATFORM, tag)
    url = "https://github.com/%s/releases/download/%s/%s" % (UPSTREAM, tag,
                                                             asset)
    log("Downloading " + url)
    if os.path.exists(DOWNLOAD):
        os.remove(DOWNLOAD)
    run(["curl", "-fsSL", "--retry", "3", "-o", DOWNLOAD, url])
    return DOWNLOAD


# ----------------------------------------------------------------- commands

def take_lock():
    lock = open(LOCK, "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock


def cmd_apply(_args):
    require_root()
    _lock = take_lock()
    target = target_version()
    current = installed_version()
    if target and newer(target, current):
        path = download(target)
        try:
            got = None
            with tarfile.open(path) as tar:
                member = tar.extractfile("helixscreen/release_info.json")
                got = json.loads(member.read().decode()).get("version")
            if got != target:
                raise RuntimeError("the %s package says it is %s"
                                   % (target, got))
            install_package(path)
        finally:
            if os.path.exists(path):
                os.remove(path)
        return
    if current is None:
        if os.path.isdir(HELIX_DIR):
            log("%s has no release_info.json; leaving it as it is"
                % HELIX_DIR)
        else:
            log("No HelixScreen release for the T1 Pro has been published "
                "yet. Install a package you built with: "
                "~/FLSUN_HelixScreen/install.sh --local FILE")
            return
    else:
        log("HelixScreen %s is installed%s" % (
            current, "" if target is None else
            " (the %s channel is at %s)" % (channel(), target)))
    if install_hook():
        restart_screen()


def cmd_install(args):
    require_root()
    _lock = take_lock()
    install_package(os.path.abspath(args.file))


def cmd_remove(_args):
    require_root()
    _lock = take_lock()
    restored = remove_hook()
    stop_screen()
    if restored:
        start_screen()
    for path in (HELIX_NEW, HELIX_OLD):
        shutil.rmtree(path, ignore_errors=True)
    if os.path.isdir(HELIX_DIR):
        backup = os.path.join(HOME, "helixscreen-config.bak")
        shutil.rmtree(backup, ignore_errors=True)
        if os.path.isdir(os.path.join(HELIX_DIR, "config")):
            shutil.copytree(os.path.join(HELIX_DIR, "config"), backup,
                            symlinks=True)
            log("HelixScreen's settings are kept in " + backup)
        shutil.rmtree(HELIX_DIR)
    shutil.rmtree(HELIX_STATE, ignore_errors=True)
    log("HelixScreen removed")


def cmd_status(_args):
    print("installed: %s" % (installed_version() or "-"))
    print("channel:   %s" % channel())
    print("stable:    %s" % (pinned("stable") or "-"))
    print("beta:      %s" % (pinned("beta") or "-"))
    print("at boot:   %s" % ("HelixScreen" if is_helix_hook(STARTBOOT)
                             else "FLSun's stock screen"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("apply").set_defaults(func=cmd_apply)
    p = sub.add_parser("install")
    p.add_argument("file")
    p.set_defaults(func=cmd_install)
    sub.add_parser("remove").set_defaults(func=cmd_remove)
    sub.add_parser("status").set_defaults(func=cmd_status)
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        sys.exit(2)
    try:
        args.func(args)
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)


if __name__ == "__main__":
    main()

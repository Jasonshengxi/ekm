#!/usr/bin/python3
import argparse
import importlib.util
import tomllib
from dataclasses import dataclass
from os import getcwd, getenv, listdir, mkdir, path
from pprint import pprint
from subprocess import run as system
from sys import stderr
from typing import Any, Optional

from ekm import BuildConfig


def eprint(*args, **kwargs):
    print(*args, **kwargs, file=stderr)


BUILD_TOML = "ekm.toml"
BUILD_PY = "ekm.py"
home_env_var = getenv("HOME")
if home_env_var is None:
    eprint("$HOME environment variable not defined.")
    exit(0)
DEFAULT_TOML = path.join(home_env_var, ".local", "share", "ekm", BUILD_TOML)


@dataclass
class CompileConfig:
    cc: str
    out: str
    cflags: list[str]
    ldflags: list[str]


def unnone(cfg: Optional[BuildConfig]) -> BuildConfig:
    return cfg if cfg is not None else BuildConfig()


JOIN_ATTRS = ["cflags", "ldflags"]


def merge_attr[T](attr: str, base: T, cfg: T) -> T:
    if base is None:
        return cfg
    if cfg is None:
        return base

    if attr in JOIN_ATTRS:
        assert isinstance(base, list)
        assert isinstance(cfg, list)
        return base + cfg
    else:
        return cfg


def merge_config_attr(
    result: BuildConfig, attr: str, base: BuildConfig, cfg: BuildConfig
):
    result.__dict__[attr] = merge_attr(attr, base.__dict__[attr], cfg.__dict__[attr])


def merge_config(base: BuildConfig, cfg: BuildConfig) -> BuildConfig:
    result = BuildConfig()
    for attr in BuildConfig.__match_args__:
        merge_config_attr(result, attr, base, cfg)
    return result


def merge_config_opt(
    base: Optional[BuildConfig], cfg: Optional[BuildConfig]
) -> BuildConfig:
    return merge_config(unnone(base), unnone(cfg))


def make_flags(proj_name: str, config: BuildConfig) -> CompileConfig:
    cflags = config.cflags if (config.cflags is not None) else []
    # cflags += ["-fsanitize-trap=all"]

    ldflags = config.ldflags if (config.ldflags is not None) else []
    cc = config.cc if (config.cc is not None) else "gcc"
    out = config.out if (config.out is not None) else proj_name

    if config.opt_level is not None:
        cflags += [f"-O{config.opt_level}"]
    if config.warn is not None and config.warn:
        warns: set[str] = set()
        for warn in config.warn:
            if warn == "all":
                warns |= {"-Wall"}
            elif warn == "extra":
                warns |= {"-Wextra"}
            elif warn == "full":
                warns |= {"-Wall", "-Wextra"}
            elif warn == "error":
                warns |= {"-Werror"}
            else:
                warns |= {f"-W{warn}"}
        cflags += sorted(list(warns))
    if config.debug is not None:
        if isinstance(config.debug, int):
            cflags += [f"-g{config.debug}"]
            if config.debug >= 2:
                cflags += ["-fno-omit-frame-pointer"]
        elif isinstance(config.debug, str):
            cflags += [f"-g{config.debug}"]
        elif isinstance(config.debug, bool):
            if config.debug:
                cflags += [f"-g"]
        else:
            eprint(config.debug)
            assert False
    if config.sanitize is not None and config.sanitize:
        san_flags = [f"-fsanitize={",".join(config.sanitize)}"]
        cflags += san_flags
        ldflags += san_flags
    if config.lto is not None and config.lto:
        cflags += ["-flto"]
        ldflags += ["-flto"]

    return CompileConfig(cflags=cflags, ldflags=ldflags, cc=cc, out=out)


def parse_config(toml: dict[str, Any]) -> BuildConfig:
    config = BuildConfig()
    for attr in ["warn", "sanitize", "cflags", "ldflags"]:
        if attr in toml:
            if isinstance(toml[attr], str):
                config.__dict__[attr] = [toml[attr]]
            else:
                config.__dict__[attr] = toml[attr]
    for attr in ["cc", "lto", "run", "out"]:
        if attr in toml:
            config.__dict__[attr] = toml[attr]

    if "inherits" in toml:
        inherits = toml["inherits"]
        if isinstance(inherits, str):
            config.inherits = {"all": inherits}
        else:
            config.inherits = inherits

    if "debug" in toml:
        config.debug = int(toml["debug"])
    if "opt-level" in toml:
        config.opt_level = toml["opt-level"]

    return config


def apply_inherits(configs: dict[str, BuildConfig]):
    can_inherits = {prof: config.inherits is None for prof, config in configs.items()}

    not_done = True
    while not_done:
        not_done = False
        for prof in configs:
            profile = configs[prof]
            if profile.inherits is not None and profile.inherits:
                can_inherit = all(
                    can_inherits[p] for p in profile.inherits.values() if p
                )

                if can_inherit:
                    # eprint(f"doing inheritance for {prof}")
                    # pprint(configs[prof], stream=stderr)

                    result = merge_config(BuildConfig(), configs[prof])
                    for attr, parent in profile.inherits.items():
                        if attr != "all" and parent:
                            # eprint(f"merging {attr}")
                            parent_prof = configs[parent]
                            merge_config_attr(result, attr, parent_prof, configs[prof])
                    if "all" in profile.inherits.keys():
                        done = set(profile.inherits.keys()) - {"all"}
                        cfg_args: set[str] = set(BuildConfig.__match_args__)
                        redo = sorted(list(cfg_args - done))

                        parent_prof = configs[profile.inherits["all"]]
                        for attr in redo:
                            # eprint(f"merging {attr} as part of *")
                            merge_config_attr(result, attr, parent_prof, configs[prof])

                    # pprint(result, stream=stderr)
                    configs[prof] = result
                    can_inherits[prof] = True
                else:
                    not_done = True


def parse_configs(
    profiles: dict[str, dict[str, Any]],
    base: dict[str, BuildConfig] = {},
    apply_inherit=True,
) -> dict[str, BuildConfig]:
    configs: dict[str, BuildConfig] = dict()
    for prof, cfg in profiles.items():
        config = parse_config(cfg)
        configs[prof] = config

    inherited_profs = {
        k for k, v in configs.items() if v.inherits is not None
    }
    all_profs = (set(profiles.keys()) | set(base.keys())) - {"all"}
    layered_profs = all_profs - inherited_profs

    config_all = None
    if "all" in configs:
        config_all = parse_config(profiles["all"])
        assert config_all.inherits is None

    final_configs: dict[str, BuildConfig] = {}
    for prof in layered_profs:
        assert prof != "all"
        config = configs[prof] if prof in configs else None
        config_base = base[prof] if prof in base else None
        merged = merge_config_opt(merge_config_opt(config_base, config_all), config)
        if merged is not None:
            final_configs[prof] = merged

    for prof in inherited_profs:
        assert prof != "all"
        final_configs[prof] = configs[prof]

    if apply_inherit:
        apply_inherits(final_configs)

    return {k: v for k, v in final_configs.items() if v is not None}


def emit_ninja(profile: tuple[str, CompileConfig], files: list[str]) -> str:
    prof, config = profile
    build_dir = f"target/{prof}"

    ninja = f"builddir = {build_dir}\n"
    ninja += "rule compile\n"
    ninja += f"  command = {config.cc} -MMD -MF $out.d {" ".join(config.cflags)} -c $in -o $out\n"
    ninja += f"  description = COMPILE $out\n"
    ninja += f"  depfile = $out.d\n"
    ninja += f"  deps = gcc\n"
    ninja += f"  restat = 1\n"
    ninja += "rule link\n"
    ninja += f"  command = {config.cc} {" ".join(config.ldflags)} $in -o $out\n"
    ninja += f"  description = LINK $out\n"
    ninja += "\n"
    objs = []
    for file in files:
        obj = f"$builddir/{file}.o"
        ninja += f"build {obj}: compile src/{file}.c\n"
        objs.append(obj)
    ninja += f"build $builddir/{config.out}: link {" ".join(objs)}\n"
    ninja += f"default $builddir/{config.out}\n"
    return ninja


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="build a C project badly.")
    subparsers = parser.add_subparsers(dest="subcommand")

    common = argparse.ArgumentParser(add_help=True)
    common.add_argument("profile", nargs="?", default="dev")
    common.add_argument("--dry-run", action="store_true", default=False)
    common.add_argument("--verbose", action="store_true", default=False)
    # common.add_argument("--show-profs-base", action="store_true", default=False)
    # common.add_argument("--show-profs", action="store_true", default=False)
    common.add_argument("--args", nargs="*", default=[])

    subparsers.add_parser("run", parents=[common], add_help=False)
    subparsers.add_parser("build", parents=[common], add_help=False)

    sub_clean = subparsers.add_parser("clean")
    sub_clean.add_argument("profile", nargs="?", default="all")

    return parser


def get_from_toml() -> dict[str, BuildConfig]:
    with open(DEFAULT_TOML, "rb") as file:
        default_toml = tomllib.load(file)

    base_profiles = parse_configs(default_toml["profile"], apply_inherit=False)

    with open(BUILD_TOML, "rb") as file:
        try:
            toml = tomllib.load(file)
        except tomllib.TOMLDecodeError as e:
            print(f"Could not parse {BUILD_TOML}:")
            print(e)
            raise e

    if "profile" in toml:
        profiles = parse_configs(toml["profile"], base_profiles, apply_inherit=True)
    else:
        profiles = base_profiles

    return profiles


def get_from_py() -> dict[str, BuildConfig]:
    raise Exception("Unimplemented")


def main():
    args = parser().parse_args()

    if args.subcommand == "clean":
        if args.profile == "all":
            system(["rm", "-r", "target"])
        else:
            system(["rm", "-r", f"target/{args.profile}"])
        return

    if args.subcommand is None:
        eprint("no subcommand specified")
        return 1

    if path.exists(BUILD_PY):
        profiles = get_from_py()
    elif path.exists(BUILD_TOML):
        profiles = get_from_toml()
    else:
        eprint("build.ekm not found.")
        return 1

    project_name = getcwd().rsplit("/", maxsplit=1)[-1]
    project_files = [
        file[:-2]
        for file in listdir("src")
        if file.endswith(".c") and not file.endswith("_old.c")
    ]

    run = args.subcommand == "run"
    build = True

    profile = profiles[args.profile]
    flags = make_flags(project_name, profile)
    ninja = emit_ninja((args.profile, flags), project_files)
    if args.dry_run:
        print(ninja)
        return

    if not path.exists("target"):
        mkdir("target")
    if not path.exists(f"target/{args.profile}"):
        mkdir(f"target/{args.profile}")

    ninja_file = f"target/{args.profile}/build.ninja"
    with open(ninja_file, "w") as file:
        file.write(ninja)

    if build:
        extra = []
        if args.verbose:
            extra = ["-v"]
        proc = system(["ninja"] + extra + ["-f", ninja_file])
        print()

        if proc.returncode == 0 and run:
            bin = f"target/{args.profile}/{project_name}"
            if profile.run is not None:
                if isinstance(profile.run, str):
                    run = [
                        "fish",
                        "-c",
                        profile.run.format(bin=bin, args=" ".join(args.args)),
                    ]
                else:
                    run = [
                        arg.format(bin=bin, args=" ".join(args.args))
                        for arg in profile.run
                    ]
            else:
                run = [bin] + args.args

            proc = system(run)
            return proc.returncode


if __name__ == "__main__":
    exit(main())

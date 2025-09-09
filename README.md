## Summary

`ekm` is a simple build tool for C. The name is simply an anagram of `make` but without the `a`.

## Requirements

Requires `python` to execute. The exact version is unknown, but it's tested on `3.13.7`.

Requires `ninja` for the build backend. Using the default configuration, `gcc` is used as the c compiler. 
`ekm` doesn't respect any environment variables except for the `$HOME` variable.

## Installation

To install ekm, 3 files must be moved:
- place `ekm_bin.py` in `$PATH`. 
- place `ekm.py` in `$PYTHON_PATH`.
- place `ekm.toml` at `~/.local/share/ekm/ekm.toml`

Alternatively, use symlinks, so that any updates are automatically reflected.

## Usage

`ekm` expects an `ekm.toml` file in the current working directory. The file can be left empty to use the
default configuration, which uses `gcc`. For the syntax, reference the default configuration, `ekm.toml`.

Important Note: `ekm` uses a very simple method to search for source files: all top-level files under the
src/ directory from the cwd, which end with `.c`, and doesn't end with `_old.c`. 


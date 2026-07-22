# inspect-antigravity

`inspect-antigravity` packages inspect_swe's Antigravity CLI agent as a standalone
[Inspect AI](https://inspect.aisi.org.uk/) agent plugin.

## Install

```bash
uv add inspect-antigravity
```

Inspect discovers the `antigravity_cli` agent when `inspect-antigravity` is installed:
the package registers its `inspect_antigravity` entry point in the `inspect_ai` group.

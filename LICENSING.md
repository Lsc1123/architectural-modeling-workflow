# Licenses

| Path/content | License |
|---|---|
| Python MCP service, geometry algorithms, SketchUp adapter, skill, scripts, tests and documentation | MIT |
| `adapters/blender/`, `examples/fixtures/*_texture.py` (imports `bpy`) | GPL-3.0-or-later |
| Original example models and fixtures, including the owner's Plan E contribution | CC0-1.0 |
| Third-party assets | Their original license; listed individually in the case manifest |

The wheel includes both MIT code and the separate GPL Blender adapter, so its package metadata declares `MIT AND GPL-3.0-or-later`. The service launches Blender as a separate process. Blender, SketchUp and their SDKs/applications are not redistributed. Their own licenses still apply.

CC0 applies only to rights the contributor holds. Reference images, books, fonts, product names and third-party source assets are not relicensed by this repository. The Plan E example distinguishes original adapted geometry from its CC0 plant/texture sources. Raw chats, private temporary attachments and research-book PDFs are excluded.

License texts are in `LICENSE` and `LICENSES/`. The Blender adapter source is shipped alongside every binary package. For contributions, preserve per-file SPDX headers and record asset provenance; see `CONTRIBUTING.md`.

References: [Blender licensing](https://www.blender.org/about/license/), [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

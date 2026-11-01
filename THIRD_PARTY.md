# Third-party notices and provenance

Applications are not bundled. SketchUp's proprietary application license and Blender's GPL apply to their respective installations. The GPL Blender runner is distributed in source under `adapters/blender/`; it runs separately from the MIT MCP service. GPL text comes from the official Blender distribution.

Python packages are resolved with hashes in `requirements-lock.txt`. MCP is the official Python SDK (MIT), NumPy is BSD-3-Clause, Shapely is BSD-3-Clause, trimesh is MIT, manifold3d is Apache-2.0. Their dependency wheels retain their own notices; installation does not relicense them. The lock includes development dependencies separately from the installable project's required dependency list.

Plan E's original building and adapted furniture geometry are CC0 by the owner's explicit release instruction. Adapted furniture is not an authorized manufacturer replica. External plant/texture sources retain CC0 and their author attribution:

| Source | Author | License |
|---|---|---|
| Poly Haven `potted_plant_01`, `potted_plant_02` | Rico Cilliers | CC0 |
| Poly Haven `potted_plant_04` | James Ray Cock | CC0 |
| Poly Haven `fern_02` | Rob Tuytel, Rico Cilliers | CC0 |
| Poly Haven `wood_table_001` | Dimitrios Savva, Rico Cilliers | CC0 |
| Poly Haven `oak_veneer_01` | Jenelle | CC0 |
| ambientCG `Plaster001` (catalogued alternative) | ambientCG | CC0 |

The retained source catalogue is [asset-provenance.json](examples/plan-e/asset-provenance.json). A catalogued candidate does not imply it occurs in every final model. The release's actual material index supplies the final inventory. No reference books, web photographs, branded product CAD or raw chat logs are redistributed.

The new regression geometry, pavilion task and table fixture are original CC0 contributions. Earlier owner-authored project scripts informed the regression cases; their local paths and hashes are retained in [history-lessons.json](docs/history-lessons.json). Project-specific dimensions are not copied as universal defaults. New generic algorithms use the dependencies above and preserve their licenses.

Primary sources: [Poly Haven license](https://polyhaven.com/license), [ambientCG license](https://docs.ambientcg.com/license/), [Blender licensing](https://www.blender.org/about/license/), [CC0 legal text](https://creativecommons.org/publicdomain/zero/1.0/legalcode.en).

The actual ten embedded `LR_*` floor/traffic textures are original procedural images (NumPy/Pillow grain/noise) made for this project, not Poly Haven photographs. Their source file hashes and generator provenance are in [finish-provenance.json](examples/plan-e/finish-provenance.json). Historical architectural references informed the palette; no source PDF or reference image is included. Each final variant's material index lists the actual embedded set.

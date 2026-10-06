# Third-Party Notices

This repository publishes the original **Semantic Graybox** control, orchestration, Blender UI, and review code.

The repository-level MIT License applies to the original Semantic Graybox code published here. It does **not** relicense third-party software, models, model weights, runtimes, or separately installed dependencies.

## Roblox Cube / Cube3D

Semantic Graybox currently includes an adapter that can invoke Roblox Cube3D as an **external dependency** through its command-line interface.

Upstream project:

- https://github.com/Roblox/cube

Cube3D source code, CubePart source code, model weights, checkpoints, virtual environments, and upstream artifacts are **not distributed in this repository**.

Users who install or use Cube3D/CubePart must review and comply with the applicable upstream license terms for the specific artifacts/version they use.

The presence of an adapter or documentation reference does not imply that Roblox Cube/Cube3D/CubePart is licensed under MIT.

## Blender

Semantic Graybox integrates with Blender through the Blender Python API (`bpy`). Blender itself is not distributed with this repository and remains subject to its own license terms.

## General dependency rule

Any third-party package installed separately by the user remains subject to that package's own license. This notice does not replace or modify upstream license terms.

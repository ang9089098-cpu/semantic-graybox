"""Disposable scene for visual UI review; never opens/saves source .blend files."""
import os
import sys
import tempfile
from pathlib import Path
import bpy
import bmesh
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import blender_ui
from blender_ui import workflow
from generation.generator_adapters.base import GenerationResult
from generation.generator_adapters.cube3d_adapter import Cube3DAdapter
from unittest.mock import patch

for default_obj in list(bpy.data.objects):
    bpy.data.objects.remove(default_obj, do_unlink=True)
blender_ui.register()
coll = bpy.data.collections.new('Desk')
bpy.context.scene.collection.children.link(coll)
for name, size, pos in [('Top',(2,1,.1),(0,0,1)),('Leg.001',(.08,.08,.7),(-.9,-.4,.5)),('Leg.002',(.08,.08,.7),(.9,-.4,.5)),('Leg.003',(.08,.08,.7),(-.9,.4,.5)),('Leg.004',(.08,.08,.7),(.9,.4,.5))]:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.scale, obj.location = size, pos
    coll.objects.link(obj)
bpy.context.view_layer.update()
p = bpy.context.scene.semantic_graybox
p.target_collection = coll
p.style_prompt = 'carved walnut, restrained rococo'
bpy.ops.semantic_graybox.analyze()
# Fixture generation only for initial result display. Buttons use the real pipeline.
objfile = Path(tempfile.gettempdir()) / 'semantic_graybox_manual_fixture.obj'
objfile.write_text('v 0 0 0\nv .1 0 0\nv 0 .1 .7\nf 1 2 3\n')
with patch.object(Cube3DAdapter, 'generate', lambda a,r: GenerationResult(True,r.master_id,output_path=str(objfile))):
    bpy.ops.semantic_graybox.generate()
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        area.spaces.active.show_region_ui = True
        area.spaces.active.region_3d.view_distance = 5
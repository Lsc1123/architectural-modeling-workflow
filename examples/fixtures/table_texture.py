# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
m=bpy.data.materials['Warm top'];n=m.node_tree.nodes.new('ShaderNodeTexImage')
i=bpy.data.images.new('Original_checker_CC0',width=8,height=8)
pixels=[]
for y in range(8):
 for x in range(8):
  c=(.6,.28,.10,1) if (x//2+y//2)%2 else (.85,.65,.35,1)
  pixels.extend(c)
i.pixels=pixels;i.pack();n.image=i
m.node_tree.links.new(n.outputs['Color'],m.node_tree.nodes['Principled BSDF'].inputs['Base Color'])

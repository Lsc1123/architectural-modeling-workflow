"""Opt-in API examples and actual MCP image verification in an isolated SU workspace."""
import argparse
import asyncio
import base64
import re
from pathlib import Path
from _harness import Harness
from amw.io import atomic, sha
from amw import checks


async def run(root, label):
    directory = 'api-reference/' + label
    references = Path(__file__).resolve().parents[1] / 'skills/architectural-modeling-workflow/references/api'
    def example(name):
        return re.search(r'```ruby\n(.*?)```', (references/name).read_text(), re.S)[1]
    async with Harness(root, directory, 'api-' + label) as h:
        state = await h.call('sketchup_state')
        if state['modified']:
            raise RuntimeError('Preserve unsaved native work before testing')
        await h.blank(directory + '/model.skp')
        code = example('entities.md') + "\nraise 'Hole volume' unless (g.volume * 0.0254**3 - 3.0).abs < 1e-8\n"
        code += """
parent = Sketchup.active_model.entities.add_group
parent.name = 'API parent'
child = parent.entities.add_group
face = child.entities.add_face([[0,0,0],[1.m,0,0],[1.m,1.m,0],[0,1.m,0]])
face.reverse! if face.normal.z < 0
face.pushpull(1.m)
parent.transform!(Geom::Transformation.translation([5.m,0,0]))
child.transform!(Geom::Transformation.translation([0,3.m,0]))
"""
        code += example('transforms.md') + "\nraise 'Nested transform' unless metres.zip([6,3,0]).all? { |a,b| (a-b).abs < 1e-8 }\n"
        code += "face = child.entities.grep(Sketchup::Face).first\n" + example('materials.md')
        code += example('views.md') + "\nraise 'Visible path' unless visible\nparent.hidden = true\nraise 'Ancestor visibility' if m.drawing_element_visible?(path)\nparent.hidden = false\n"
        await h.script('examples', code, new_roots=True)
        await h.write('sketchup_save', 'save', path=directory + '/model.skp')
        saved = await h.snapshot('saved')
        await h.write('sketchup_reopen', 'reopen')
        reread = await h.snapshot('reopened')
        assert checks.scope_diff(saved, reread, [])['status'] == 'passed'
        capture_path = directory + '/mcp-image.png'
        reply = await h.client.call_tool('sketchup_capture',dict(path=capture_path,width=800,height=600,zoom_extents=True))
        assert not reply.is_error and reply.structured_content['status']=='completed'
        image = next(c for c in reply.content if c.type=='image')
        assert image.mime_type=='image/png'
        assert base64.b64decode(image.data)==(h.root/capture_path).read_bytes()
        atomic(h.root/directory/'validation.json',dict(status='passed',version=state['version'],
            examples=['entities','transforms','materials','views'],
            transactions='Native save and actual reopen; rollback and undo covered separately by validate_recovery',
            model_sha256=sha(h.root/directory/'model.skp'),image_sha256=sha(h.root/capture_path),
            screenshot=dict(mcp_image_matches_file=True,width=800,height=600),
            limits='Isolated examples, not arbitrary script correctness or building compliance'))
    print('API examples and MCP image passed:',label)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);parser.add_argument('--round',required=True)
    args=parser.parse_args();asyncio.run(run(Path(args.workspace).resolve(),args.round))

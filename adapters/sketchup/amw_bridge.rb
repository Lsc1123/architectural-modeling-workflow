# SPDX-License-Identifier: MIT
require 'sketchup.rb'
require 'json'
require 'digest'
require 'fileutils'
require 'securerandom'

module AMW
  module Bridge
    M = 0.0254
    class Observer < Sketchup::ModelObserver
      def onTransactionCommit(model); Bridge.touch(model); end
      def onTransactionUndo(model); Bridge.touch(model); end
      def onTransactionRedo(model); Bridge.touch(model); end
      def onPostSaveModel(model); Bridge.saved(model); end
    end
    class ApplicationObserver < Sketchup::AppObserver
      def onNewModel(model); Bridge.document_opened(model, 'new'); end
      def onOpenModel(model); Bridge.document_opened(model, 'open'); end
    end
    @documents = {}
    @busy = false
    @bridge_code_sha = Digest::SHA256.file(__FILE__).hexdigest

    def self.atomic(path, data)
      FileUtils.mkdir_p(File.dirname(path))
      temp = path + '.tmp-' + SecureRandom.hex(4)
      File.write(temp, JSON.pretty_generate(data))
      File.rename(temp, path)
    ensure
      File.delete(temp) if temp && File.exist?(temp)
    end

    def self.local(relative)
      raise 'Connect a project first' unless @root
      target = File.expand_path(relative, @root)
      raise 'Output path escapes workspace' unless target.start_with?(@root + File::SEPARATOR)
      # Refuse existing symlink parents which could redirect a workspace write.
      parent = target
      until parent == @root
        raise 'Symlink path is not an output target' if File.symlink?(parent)
        parent = File.dirname(parent)
      end
      target
    end

    def self.metadata(model)
      @documents[model.object_id] ||= begin
        observer = Observer.new
        model.add_observer(observer)
        {id: SecureRandom.hex(12), revision: 0, observer: observer, model_reference: model,
         loaded_sha: File.file?(model.path) ? Digest::SHA256.file(model.path).hexdigest : nil}
      end
    end

    def self.touch(model)
      metadata(model)[:revision] += 1
    end

    def self.saved(model)
      meta = metadata(model)
      meta[:loaded_sha] = File.file?(model.path) ? Digest::SHA256.file(model.path).hexdigest : nil
      meta[:revision] += 1
    end

    def self.camera_info(c)
      {eye: c.eye.to_a.map { |v| v*M }, target: c.target.to_a.map { |v| v*M },
        up: c.up.to_a, perspective: c.perspective?, fov: c.perspective? ? c.fov : nil,
        height_m: c.perspective? ? nil : c.height*M}
    end

    def self.without_transition(model)
      options = model.options['PageOptions']; previous = options['ShowTransition']
      begin
        options['ShowTransition'] = false
        yield
      ensure
        options['ShowTransition'] = previous
      end
    end

    def self.state
      model = Sketchup.active_model
      meta = metadata(model)
      disk_sha = nil
      if File.file?(model.path)
        stat = File.stat(model.path)
        key = [model.path, stat.size, stat.mtime.to_f, stat.ino]
        if meta[:stat_key] != key
          meta[:disk_sha] = Digest::SHA256.file(model.path).hexdigest
          meta[:stat_key] = key
        end
        disk_sha = meta[:disk_sha]
      end
      {heartbeat_unix: Time.now.to_f, application: 'SketchUp', version: Sketchup.version,
       bridge_version: '0.1.1', bridge_sha256: @bridge_code_sha,
       pid: Process.pid, document_id: meta[:id], path: model.path, title: model.title,
       modified: model.modified?, disk_sha256: disk_sha,
       external_disk_change: disk_sha != meta[:loaded_sha],
       revision: "#{meta[:id]}:#{meta[:revision]}:#{disk_sha || 'unsaved'}",
       active_scene: model.pages.selected_page&.name,
       active_edit_path: (model.active_path || []).map { |e| e.persistent_id.to_s },
       active_tool: model.tools.active_tool_name,
       current_view_camera: camera_info(model.active_view.camera),
       render_mode: model.rendering_options['RenderMode'], textures_displayed: model.rendering_options['Texture'],
       units: 'm', native_units: 'inch'}
    end

    def self.connect(root)
      raise 'Wait for the current native operation before changing workspace' if @busy
      @root = File.expand_path(root)
      raise 'Choose an existing project folder' unless File.directory?(@root)
      @runtime = local('.amw/runtime/sketchup')
      previous = JSON.parse(File.read(File.join(@runtime, 'session.json'))) rescue nil
      if previous && previous['pid'] != Process.pid && Time.now.to_f - previous.fetch('heartbeat_unix', 0) < 5
        raise 'Another SketchUp process is connected to this workspace'
      end
      FileUtils.mkdir_p(File.join(@runtime, 'queue'))
      Dir[File.join(@runtime, 'operations', '*', 'status.json')].each do |path|
        row = JSON.parse(File.read(path)) rescue {}
        result = File.join(File.dirname(path), 'result.json')
        if row['status'] == 'running' && !File.exist?(result)
          atomic(result, {status: 'unknown', operation_id: File.basename(File.dirname(path)), recovery: 'Native process ended without a final receipt; inspect the same operation and preserved document before any retry'})
        end
      end
      UI.stop_timer(@timer) if @timer
      @timer = UI.start_timer(0.25, true) { tick }
      atomic(File.join(@runtime, 'session.json'), state)
      @root
    end

    def self.disconnect
      UI.stop_timer(@timer) if @timer
      @timer = nil
      atomic(File.join(@runtime, 'session.json'), state.merge(heartbeat_unix: 0)) if @runtime
    end

    def self.tick
      return if @busy
      atomic(File.join(@runtime, 'session.json'), state)
      file = Dir[File.join(@runtime, 'queue', '*.json')].sort.first
      return unless file
      request = JSON.parse(File.read(file))
      id = request.fetch('id')
      raise 'Invalid operation ID' unless id.match?(/\A[A-Za-z0-9_-]{1,100}\z/)
      base = File.join(@runtime, 'operations', id)
      FileUtils.mkdir_p(base)
      if File.exist?(File.join(base, 'result.json'))
        File.delete(file)
        return
      end
      if File.exist?(File.join(base, 'cancel.json'))
        atomic(File.join(base, 'result.json'), {status: 'canceled', operation_id: id})
        File.delete(file)
        return
      end
      # A persisted running receipt is deliberately not replayed after a crash.
      old = JSON.parse(File.read(File.join(base, 'status.json'))) rescue {}
      if old['status'] == 'running'
        atomic(File.join(base, 'result.json'), {status: 'unknown', operation_id: id,
          recovery: 'Inspect the document and operation snapshot; do not resend blindly'})
        File.delete(file)
        return
      end
      @busy = true
      atomic(File.join(base, 'status.json'), {status: 'running', request_sha256: request['request_sha256']})
      File.delete(file)
      begin
        result = dispatch(request)
        unless result == :deferred
          atomic(File.join(base, 'result.json'), {status: 'completed', operation_id: id,
            request_sha256: request['request_sha256'], result: result, state: state})
        end
      rescue Exception => error
        @pending = nil
        atomic(File.join(base, 'result.json'), {status: 'failed', operation_id: id,
          error: error.message, backtrace: error.backtrace.first(10), state: state})
      ensure
        @busy = false unless @pending
      end
    rescue Exception => error
      warn "AMW bridge: #{error.message}"
      @busy = false
    end

    def self.document_opened(model, kind)
      return unless @pending && @pending[:event_kind] == kind
      @pending[:opened_model] = model
    end

    def self.defer_document(request, path, event_kind)
      @pending = {request: request, path: path, event_kind: event_kind,
        old_model: Sketchup.active_model, require_event: request['operation'] != 'open', deadline: Time.now.to_f + 120}
      UI.start_timer(0.1, false) { finish_document }
    end

    def self.finish_document
      pending = @pending
      return unless pending
      request = pending[:request]
      result_path = File.join(@runtime, 'operations', request['id'], 'result.json')
      begin
        model = pending[:require_event] ? pending[:opened_model] : Sketchup.active_model
        if model && Sketchup.active_model == model && (!pending[:require_event] || model != pending[:old_model]) && (pending[:event_kind] == 'new' || model.path == pending[:path])
          if pending[:event_kind] == 'new'
            raise 'New document was edited before its initial save; preserved it' if model.modified?
            raise 'Output appeared while opening new document' if File.exist?(pending[:path])
            FileUtils.mkdir_p(File.dirname(pending[:path]))
            raise 'Initial native save failed' unless model.save(pending[:path])
          end
          raise 'Opened document path differs from requested target' unless model.path == pending[:path]
          if pending[:require_event]
            metadata(model)[:loaded_sha] = Digest::SHA256.file(model.path).hexdigest
          end
          atomic(result_path, {status: 'completed', operation_id: request['id'],
            request_sha256: request['request_sha256'], state: state,
            result: {path: model.path.delete_prefix(@root + '/'), native_document_event: pending[:require_event] ? pending[:event_kind] : 'target_active',
              new_document_id: metadata(model)[:id], verification: pending[:require_event] ? 'Observed a new native document event; compare subsequent geometry' : 'Requested target is actually active; this may activate an existing window and is not a file reread'}})
          @pending = nil; @busy = false
        elsif Time.now.to_f > pending[:deadline]
          atomic(result_path, {status: 'unknown', operation_id: request['id'],
            recovery: 'No matching native document-open event/current target. Inspect the document and this same operation; never repeat blindly'})
          @pending = nil; @busy = false
        else
          atomic(File.join(@runtime, 'session.json'), state) if Sketchup.active_model
          UI.start_timer(0.1, false) { finish_document }
        end
      rescue Exception => error
        atomic(result_path, {status: 'failed', operation_id: request['id'], error: error.message})
        @pending = nil; @busy = false
      end
    end

    def self.require_revision(request)
      current = state
      raise 'Document revision conflict: reread current window and preserve user edits' unless request['expected_revision'] == current[:revision]
      raise 'Disk changed outside this document; resolve it before writing' if current[:external_disk_change]
    end

    def self.material_name(material)
      material&.name
    end

    def self.material_info(material)
      return nil unless material
      return @material_export_cache[material] if @material_export_cache && @material_export_cache.key?(material)
      c = material.color
      row = {name: material.name, color: [c.red, c.green, c.blue], opacity: material.alpha}
      if material.texture
        t = material.texture
        row[:texture] = {filename: File.basename(t.filename), width_m: t.width * M, height_m: t.height * M}
        rep = t.image_rep
        row[:texture][:pixel_sha256] = Digest::SHA256.hexdigest(rep.data) if rep.respond_to?(:data)
      end
      @material_export_cache[material] = row if @material_export_cache
      row
    end

    def self.export_geometry
      model = Sketchup.active_model
      @material_export_cache = {}
      s = state
      objects = []; sections = []; instances = []
      material_rows = model.materials.map do |m|
        c = m.color
        row = {id: m.name, color: [c.red / 255.0, c.green / 255.0, c.blue / 255.0], opacity: m.alpha}
        row[:texture] = {filename: File.basename(m.texture.filename), width_m: m.texture.width * M,
                         height_m: m.texture.height * M} if m.texture
        row
      end
      writer = Sketchup.create_texture_writer
      walk = nil
      walk = lambda do |entities, transform, chain, names, active, inherited, owner|
        entities.grep(Sketchup::SectionPlane).each do |p|
          a, b, c, d = p.get_plane
          length2 = a*a + b*b + c*c
          point = Geom::Point3d.new(-d*a/length2, -d*b/length2, -d*c/length2).transform(transform).to_a.map { |v| v*M }
          inv = transform.inverse.to_a
          n = [inv[0]*a+inv[1]*b+inv[2]*c, inv[4]*a+inv[5]*b+inv[6]*c, inv[8]*a+inv[9]*b+inv[10]*c]
          length = Math.sqrt(n.sum { |v| v*v }); n.map! { |v| v/length }
          sections << {id: (chain + [p.persistent_id.to_s]).join('/'), name: p.name,
            symbol: p.symbol, active: p.active?, plane_world_m: n + [-n.zip(point).sum { |x,y| x*y }]}
        end
        faces = entities.grep(Sketchup::Face)
        unless faces.empty?
          points = []; indices = {}; triangles = []; loops = []
          index = lambda do |point|
            p = point.transform(transform).to_a.map { |v| v * M }
            indices[p] ||= begin points << p; points.length - 1 end
          end
          mirrored = transform.xaxis.cross(transform.yaxis).dot(transform.zaxis) < 0
          faces.each do |face|
            front = face.material || inherited
            back = face.back_material || inherited
            row = {outer: face.outer_loop.vertices.map { |v| index.call(v.position) },
                   holes: face.loops.reject(&:outer?).map { |l| l.vertices.map { |v| index.call(v.position) } },
                   persistent_id: face.persistent_id.to_s,
                   front_material: material_name(front), back_material: material_name(back),
                   resolved_front_material: material_info(front), resolved_back_material: material_info(back)}
            row[:hidden] = face.hidden?
            row[:tag] = face.layer.name
            if (front && front.texture) || (back && back.texture)
              helper = face.get_UVHelper(true, true, writer)
              row[:uv_front] = face.outer_loop.vertices.map { |v| q = helper.get_front_UVQ(v.position); [q.x / q.z, q.y / q.z] }
              row[:uv_back] = face.outer_loop.vertices.map { |v| q = helper.get_back_UVQ(v.position); [q.x / q.z, q.y / q.z] }
              row[:uv_front_holes] = face.loops.reject(&:outer?).map { |l| l.vertices.map { |v| q = helper.get_front_UVQ(v.position); [q.x / q.z, q.y / q.z] } }
              row[:uv_back_holes] = face.loops.reject(&:outer?).map { |l| l.vertices.map { |v| q = helper.get_back_UVQ(v.position); [q.x / q.z, q.y / q.z] } }
            end
            loops << row
            fm = face.mesh(0)
            fm.polygons.each do |poly|
              ids = poly.map { |i| index.call(fm.point_at(i.abs)) }
              (1...(ids.length - 1)).each do |i|
                tri = [ids[0], ids[i], ids[i + 1]]
                triangles << (mirrored ? tri.reverse : tri)
              end
            end
          end
          matrix = transform.to_a
          [12, 13, 14].each { |i| matrix[i] *= M }
          objects << {id: chain.join('/'), name: names.last || 'Loose model faces', path: names,
            locator: {document_id: s[:document_id], persistent_id_path: chain},
            semantic_id: owner.respond_to?(:get_attribute) ? owner.get_attribute('AMW', 'semantic_id') : nil,
            kind: owner.respond_to?(:get_attribute) ? owner.get_attribute('AMW', 'kind', 'unspecified') : 'surface',
            expect_solid: owner.respond_to?(:get_attribute) ? owner.get_attribute('AMW', 'expect_solid') : false,
            asset_id: owner.respond_to?(:get_attribute) ? owner.get_attribute('AMW', 'asset_id') : nil,
            instance_material: owner ? material_info(owner.material) : nil,
            tag: owner ? owner.layer.name : nil, hidden: owner ? owner.hidden? : false,
            active: active, vertices: points, triangles: triangles, faces: loops, world_transform: matrix}
        end
        entities.each do |e|
          next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
          child = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
          id = (chain + [e.persistent_id.to_s]).join('/')
          matrix = (transform * e.transformation).to_a
          [12, 13, 14].each { |i| matrix[i] *= M }
          instances << {id: id, name: e.name.empty? ? e.definition.name : e.name,
            locator: {document_id: s[:document_id], persistent_id_path: chain + [e.persistent_id.to_s]},
            semantic_id: e.get_attribute('AMW', 'semantic_id'), definition: e.definition.name,
            asset_id: e.get_attribute('AMW', 'asset_id'), source_sha256: e.get_attribute('AMW', 'source_sha256'),
            native_type: e.typename, locked: e.locked?, hidden: e.hidden?, tag: e.layer.name,
            active: active && !e.hidden? && e.layer.visible?, instance_material: material_info(e.material),
            world_transform: matrix, own_faces: child.grep(Sketchup::Face).length,
            child_instances: child.to_a.count { |x| x.is_a?(Sketchup::Group) || x.is_a?(Sketchup::ComponentInstance) }}
          walk.call(child, transform * e.transformation, chain + [e.persistent_id.to_s],
                    names + [e.name.empty? ? e.definition.name : e.name],
                    active && !e.hidden? && e.layer.visible?, e.material || inherited, e)
        end
      end
      walk.call(model.entities, Geom::Transformation.new, ['root'], [], true, nil, nil)
      scenes = model.pages.map do |p|
        c = p.camera
        {name: p.name, camera: camera_info(c),
         hidden_persistent_ids: (p.hidden_entities || []).select { |e| !p.get_drawingelement_visibility(e) }.map { |e| e.persistent_id.to_s },
         layer_visibility_overrides: (p.layers || []).map(&:name),
         stores_hidden_layers: p.use_hidden_layers?, stores_camera: p.use_camera?,
         stores_hidden_objects: p.use_hidden_objects?, stores_section_planes: p.use_section_planes?}
          .merge(active_section_persistent_ids: (p.active_section_planes || []).map { |e| e.persistent_id.to_s },
                 layer_defaults: model.layers.map { |l| {name: l.name, page_behavior: l.page_behavior} },
                 hidden_layer_folders: (p.layer_folders || []).map(&:name))
      end
      source_path = model.path.start_with?(@root + '/') ? model.path.delete_prefix(@root + '/') : model.path
      {schema_version: 1, units: 'm', coordinate_space: 'world',
       source: {path: source_path, sha256: s[:disk_sha256], saved: !s[:modified] && !s[:external_disk_change] && !model.path.empty?},
       document: s.merge(path: source_path), objects: objects, instances: instances, materials: material_rows, scenes: scenes,
       sections: sections}
    ensure
      @material_export_cache = nil
    end

    def self.find(id)
      ids = id.split('/')
      raise 'Expected a root-based instance path' unless ids.shift == 'root'
      entities = Sketchup.active_model.entities
      parent_transform = Geom::Transformation.new
      entity = nil
      ids.each_with_index do |pid, i|
        entity = entities.find { |e| e.respond_to?(:persistent_id) && e.persistent_id.to_s == pid }
        raise "Object disappeared: #{id}" unless entity
        if i < ids.length - 1
          raise 'Shared component editing requires an explicit unique instance first' if entity.is_a?(Sketchup::ComponentInstance) && entity.definition.instances.length > 1
          parent_transform *= entity.transformation
          entities = entity.is_a?(Sketchup::Group) ? entity.entities : entity.definition.entities
        end
      end
      raise 'Object is locked' if entity && entity.respond_to?(:locked?) && entity.locked?
      [entity, entities, parent_transform]
    end

    def self.fill(group, data, parent_transform = Geom::Transformation.new)
      raise 'Mesh must contain triangles' if data.fetch('triangles').empty?
      mesh = Geom::PolygonMesh.new
      inverse = parent_transform.inverse
      data.fetch('vertices').each { |p| mesh.add_point(Geom::Point3d.new(p.map { |v| v / M }).transform(inverse)) }
      data.fetch('triangles').each { |tri| mesh.add_polygon(tri.map { |i| i + 1 }) }
      group.entities.add_faces_from_mesh(mesh, 0)
      group.entities.grep(Sketchup::Edge).each do |edge|
        next unless edge.valid? && edge.faces.length == 2
        a, b = edge.faces
        next unless a.normal.samedirection?(b.normal) && a.material == b.material && a.back_material == b.back_material
        edge.erase! if (a.plane[3] - b.plane[3]).abs < 1e-7
      end
      raise 'Native result is not a manifold editable solid' unless group.manifold?
      group.set_attribute('AMW', 'expect_solid', true)
    end

    def self.edit(request)
      require_revision(request)
      model = Sketchup.active_model
      args = request.fetch('arguments')
      scope = args.fetch('scope_ids', [])
      before = export_geometry
      backup = local('.amw/backups/' + request['id'] + '.skp')
      FileUtils.mkdir_p(File.dirname(backup))
      raise 'Could not preserve the live document' unless model.save_copy(backup)
      opened = false
      begin
        model.start_operation('AMW ' + args.fetch('label', 'model edit'), true)
        opened = true
        created = []
        args.fetch('operations').each do |op|
          case op.fetch('type')
          when 'create_mesh'
            raise 'Semantic ID already exists; preserve instance identity or use a new ID' if op['semantic_id'] && before.fetch(:instances, []).any? { |o| o[:semantic_id] == op['semantic_id'] }
            g = model.entities.add_group
            g.name = op.fetch('name')
            g.set_attribute('AMW', 'semantic_id', op.fetch('semantic_id', SecureRandom.uuid))
            g.set_attribute('AMW', 'kind', op.fetch('kind', 'solid'))
            fill(g, op.fetch('geometry'))
            created << 'root/' + g.persistent_id.to_s
          when 'replace_mesh'
            e, _, parent = find(op.fetch('id'))
            raise 'Replacement requires a leaf group, not a shared component or assembly' unless e.is_a?(Sketchup::Group) && e.entities.grep(Sketchup::Group).empty? && e.entities.grep(Sketchup::ComponentInstance).empty?
            raise 'Typed replacement would discard face-specific material/UV; use a scoped preserving native script' if e.entities.grep(Sketchup::Face).any? { |f| f.material || f.back_material }
            world = parent * e.transformation
            e.entities.clear!
            fill(e, op.fetch('geometry'), world)
          when 'transform'
            e, _, parent = find(op.fetch('id'))
            matrix = op.fetch('matrix').dup
            [12, 13, 14].each { |i| matrix[i] /= M }
            delta = Geom::Transformation.new(matrix)
            e.transformation = parent.inverse * delta * parent * e.transformation
          when 'delete'
            e, _, _ = find(op.fetch('id')); e.erase!
          when 'group'
            found = op.fetch('ids').map { |id| find(id) }
            raise 'Typed grouping currently needs root-level sibling instances' unless found.all? { |_, parent, _| parent == model.entities }
            g = model.entities.add_group(found.map(&:first))
            g.name = op.fetch('name'); g.set_attribute('AMW', 'semantic_id', SecureRandom.uuid)
            created << 'root/' + g.persistent_id.to_s
          when 'material'
            e, _, _ = find(op.fetch('id'))
            existing = model.materials[op.fetch('name')]
            mat = existing || model.materials.add(op.fetch('name'))
            # Reusing a material must not recolor unrelated instances.
            if existing && ((op['color'] && mat.color.to_a[0, 3] != op['color']) || (op.key?('opacity') && (mat.alpha - op['opacity']).abs > 1e-6))
              mat = model.materials.add(op.fetch('name') + '_' + request['id'][-8, 8])
            end
            mat.color = op['color'] if op['color']
            mat.alpha = op['opacity'] if op.key?('opacity')
            e.material = mat
          when 'probe_pushpull'
            e, _, _ = find(op.fetch('id'))
            raise 'Probe needs a group or unique component' unless e.is_a?(Sketchup::Group) || (e.is_a?(Sketchup::ComponentInstance) && e.definition.instances.length == 1)
            entities = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
            faces = entities.grep(Sketchup::Face)
            face = faces.select { |f| f.normal.z > 0.9 }.max_by { |f| f.vertices.map { |v| v.position.z }.max }
            raise 'No upward native face for push/pull probe' unless face
            model.selection.clear
            model.selection.add(e)
            face.pushpull(op.fetch('distance_m') / M)
          else
            raise 'Unknown typed edit: ' + op['type']
          end
        end
        if args['script']
          script = local(args['script'])
          raise 'Script content changed' unless Digest::SHA256.file(script).hexdigest == args.fetch('script_sha256')
          model.instance_eval(File.read(script), script)
        end
        after = export_geometry
        if args['allow_new_root_entities']
          before_roots = (before.fetch(:instances, []) + before[:sections]).select { |o| o[:id].count('/') == 1 }.map { |o| o[:id] }
          created |= (after[:instances] + after[:sections]).select { |o| o[:id].count('/') == 1 && !before_roots.include?(o[:id]) }.map { |o| o[:id] }
        end
        signatures = lambda do |g|
          grouped = (g[:objects] + g.fetch(:instances, []) + g[:sections]).group_by { |o| o[:id] }
          grouped.to_h { |id, rows| [id, Digest::SHA256.hexdigest(JSON.generate(rows))] }
        end
        a, b = signatures.call(before), signatures.call(after)
        permitted = scope + created
        changed = (a.keys | b.keys).select { |id| a[id] != b[id] }
        unexpected = changed.reject { |id| permitted.any? { |p| id == p || id.start_with?(p + '/') } }
        raise 'Scope violation; rolling back: ' + unexpected.join(', ') unless unexpected.empty?
        a_scenes = before[:scenes].to_h { |p| [p[:name], p] }; b_scenes = after[:scenes].to_h { |p| [p[:name], p] }
        changed_scenes = (a_scenes.keys | b_scenes.keys).select { |name| a_scenes[name] != b_scenes[name] }
        unexpected_scenes = changed_scenes.reject { |name| args.fetch('scene_names', []).include?(name) }
        raise 'Unexpected scene change; rolling back: ' + unexpected_scenes.join(', ') unless unexpected_scenes.empty?
        model.commit_operation
        opened = false
        touch(model)
        {created_ids: created, changed_ids: changed, changed_scenes: changed_scenes, backup: backup.delete_prefix(@root + '/'),
         saved: false, evidence: 'Live transaction only; save and reread before final verification'}
      rescue Exception
        model.abort_operation if opened
        raise
      end
    end

    def self.dispatch(request)
      model = Sketchup.active_model
      args = request.fetch('arguments', {})
      case request.fetch('operation')
      when 'status'; state
      when 'open'
        require_revision(request)
        raise 'Preserve unsaved changes before switching documents' if model.modified?
        path = local(args.fetch('path')); raise 'Workspace model missing' unless File.file?(path)
        defer_document(request, path, 'open')
        status = Sketchup.open_file(path, with_status: true)
        raise 'Open failed or skipped information' unless status == Sketchup::Model::LOAD_STATUS_SUCCESS
        :deferred
      when 'new'
        require_revision(request)
        raise 'Preserve unsaved changes before creating a document' if model.modified?
        path = local(args.fetch('path')); raise 'New model path already exists' if File.exist?(path)
        defer_document(request, path, 'new')
        Sketchup.file_new
        :deferred
      when 'query'
        g = export_geometry
        geometry = g[:objects].to_h { |o| [o[:id], o] }
        rows = g[:instances].map { |o| o.merge(vertices: geometry.fetch(o[:id], {}).fetch(:vertices, []).length, triangles: geometry.fetch(o[:id], {}).fetch(:triangles, []).length) }
        rows += g[:sections].map { |o| o.merge(native_type: 'SectionPlane', vertices: 0, triangles: 0) }
        rows << geometry['root'].merge(vertices: geometry['root'][:vertices].length, triangles: geometry['root'][:triangles].length) if geometry['root']
        rows = rows.select { |o| args['ids'].include?(o[:id]) } if args['ids']
        rows = rows.select { |o| o[:name].downcase.include?(args['name_contains'].downcase) } if args['name_contains']
        page = rows.drop(args.fetch('offset', 0)).take([args.fetch('limit', 50), 200].min)
        {total: rows.length, objects: page.map { |o| o.reject { |k, _| [:faces].include?(k) } }, state: state}
      when 'export'
        path = local(args.fetch('path')); data = export_geometry
        textures = path.sub(/\.json\z/i, '') + '_textures'
        model.materials.each do |material|
          next unless material.texture
          FileUtils.mkdir_p(textures)
          target = File.join(textures, Digest::SHA256.hexdigest(material.name)[0, 20] + '.png')
          raise 'Native texture export failed: ' + material.name unless material.texture.write(target, false)
          row = data[:materials].find { |m| m[:id] == material.name }
          row[:texture].merge!(path: target.delete_prefix(@root + '/'), sha256: Digest::SHA256.file(target).hexdigest,
            colorized: false, note: 'Native source pixels; material color and opacity remain separate')
        end
        atomic(path, data)
        {path: path.delete_prefix(@root + '/'), sha256: Digest::SHA256.file(path).hexdigest}
      when 'apply'; edit(request)
      when 'edit_context'
        require_revision(request)
        model.select_tool(nil)
        if args['id']
          ids = args['id'].split('/'); raise 'Expected root instance path' unless ids.shift == 'root'
          path = model.instance_path_from_pid_path(ids.join('.'))
          raise 'Open only a group/component editing path' unless path && path.to_a.all? { |e| e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance) }
          model.active_path = path.to_a
        else
          model.active_path = nil
        end
        touch(model)
        {active_edit_path: (model.active_path || []).map { |e| e.persistent_id.to_s }, verification: 'Editing context changed; save and reread after geometry edits'}
      when 'save'
        require_revision(request)
        raise 'Exit the native group/component edit context before final save; preserve current geometry using edit_context' if model.active_path
        path = local(args.fetch('path'))
        FileUtils.mkdir_p(File.dirname(path))
        raise 'Refusing to overwrite a different existing model' if File.exist?(path) && path != model.path
        raise 'Native save failed' unless model.save(path)
        saved(model)
        {path: path.delete_prefix(@root + '/'), sha256: Digest::SHA256.file(path).hexdigest,
         freeze_ready: !model.modified?,
         verification: 'Saved only; reopen then export and inspect the actual file'}
      when 'reopen'
        require_revision(request)
        raise 'Preserve unsaved edits before reopening' if model.modified?
        path = model.path
        raise 'Current model is not a saved workspace file' if path.empty? || !path.start_with?(@root + '/')
        defer_document(request, path, 'open')
        model.close
        # Let native document-close notifications finish before opening again.
        UI.start_timer(0.25, false) do
          begin
            status = Sketchup.open_file(path, with_status: true)
            raise 'Native reopen failed or skipped information' unless status == Sketchup::Model::LOAD_STATUS_SUCCESS
          rescue Exception => error
            atomic(File.join(@runtime, 'operations', request['id'], 'result.json'),
              {status: 'failed', operation_id: request['id'], error: error.message})
            @pending = nil; @busy = false
          end
        end
        :deferred
      when 'undo'
        require_revision(request); Sketchup.undo; touch(model); {undone: true, verification: 'Compare a subsequent snapshot'}
      when 'capture'
        path = local(args.fetch('path')); FileUtils.mkdir_p(File.dirname(path))
        model.active_view.zoom_extents if args['zoom_extents']
        model.active_view.refresh
        raise 'Capture failed' unless model.active_view.write_image(filename: path, width: args.fetch('width', 1600), height: args.fetch('height', 1000), antialias: true)
        {path: path.delete_prefix(@root + '/'), state: state}
      when 'scene'
        require_revision(request)
        model.start_operation('AMW scene', true)
        begin
        if args['select']
          p = model.pages.find { |x| x.name == args.fetch('select') }; raise 'Unknown scene' unless p
          without_transition(model) do
            model.pages.selected_page = p
            model.active_view.camera = p.camera if p.use_camera?
          end
        else
          c = args.fetch('camera')
          cam = Sketchup::Camera.new(c.fetch('eye').map { |v| v / M }, c.fetch('target').map { |v| v / M }, c.fetch('up'), c.fetch('perspective', false))
          cam.height = c.fetch('height_m') / M unless cam.perspective?
          cam.fov = c['fov'] if cam.perspective? && c['fov']
          p = model.pages.find { |x| x.name == args.fetch('name') } || model.pages.add(args.fetch('name'))
          without_transition(model) do
            model.active_view.camera = cam
            p.update
            model.pages.selected_page = p
            model.active_view.camera = cam
          end
        end
        model.commit_operation
        touch(model); {scene: p.name, camera: camera_info(model.active_view.camera)}
        rescue Exception
          model.abort_operation; raise
        end
      when 'import'
        require_revision(request)
        path = local(args.fetch('path')); raise 'Import file missing' unless File.file?(path)
        raise 'Import source changed since submission' if args['source_sha256'] && Digest::SHA256.file(path).hexdigest != args['source_sha256']
        backup = local('.amw/backups/' + request['id'] + '.skp')
        FileUtils.mkdir_p(File.dirname(backup)); raise 'Could not preserve live document' unless model.save_copy(backup)
        model.start_operation('AMW asset import', true)
        begin
          definition = model.definitions.import(path, show_summary: false, merge_coplanar_faces: true, validate_dae: true)
          raise 'SketchUp importer failed' unless definition && definition.entities.length > 0
          instance = model.entities.add_instance(definition, Geom::Transformation.new)
          instance.name = File.basename(path, File.extname(path))
          raise 'Semantic ID already exists' if args['semantic_id'] && export_geometry[:instances].any? { |o| o[:id] != 'root/' + instance.persistent_id.to_s && o[:semantic_id] == args['semantic_id'] }
          instance.set_attribute('AMW', 'semantic_id', args.fetch('semantic_id', SecureRandom.uuid))
          instance.set_attribute('AMW', 'asset_id', args['asset_id']) if args['asset_id']
          instance.set_attribute('AMW', 'kind', 'asset')
          instance.set_attribute('AMW', 'expect_solid', args['expect_solid']) if args.key?('expect_solid')
          instance.set_attribute('AMW', 'source_sha256', Digest::SHA256.file(path).hexdigest)
          model.commit_operation
          touch(model)
          {created_ids: ['root/' + instance.persistent_id.to_s], backup: backup.delete_prefix(@root + '/')}
        rescue Exception
          model.abort_operation; raise
        end
      else; raise 'Unknown native operation'
      end
    end

    Sketchup.remove_observer(@app_observer) if @app_observer
    @app_observer = ApplicationObserver.new
    Sketchup.add_observer(@app_observer)
    unless file_loaded?(__FILE__)
      menu = UI.menu('Extensions').add_submenu('AMW')
      menu.add_item('Connect project') { path = UI.select_directory(title: 'AMW project workspace'); connect(path) if path }
      menu.add_item('Disconnect') { disconnect }
      file_loaded(__FILE__)
    end
  end
end

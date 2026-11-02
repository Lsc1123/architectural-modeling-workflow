# SPDX-License-Identifier: MIT
require 'sketchup.rb'
require 'extensions.rb'
extension = SketchupExtension.new('Architectural Modeling Workflow', 'amw/amw_bridge')
extension.description = 'Revision-aware local MCP bridge for architectural modeling.'
extension.version = '0.1.1'
extension.creator = 'AMW contributors'
Sketchup.register_extension(extension, true)

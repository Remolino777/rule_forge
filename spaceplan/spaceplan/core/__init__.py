"""Shared core of spaceplan: imported by every module, imports no module.

core.lib_aux holds domain-free helpers (geometry, quantities, hashing, JSON I/O, ...);
core.lib holds the shared domain vocabulary (enums, rule DSL access, catalog loader,
schema validation, relation graph). Nothing in spaceplan.core may import outside spaceplan.core.
"""

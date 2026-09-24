# ADR 0005: Responsibility-based editor boundaries

- Status: Accepted
- Date: 2026-09-23
- Supersedes: the editor boundary policy in [ADR 0001](0001-feature-oriented-modularization.md)

## Context

The editor's access, port, service, state, and bundle conventions have become
mandatory routes even when a call only forwards to an existing collaborator.
Architecture tests required services to use access functions, reserved service
lookup for named resolver modules, and froze state-accessor inventories.
Consequently, thin forwarding wrappers could not be removed without triggering
boundary test violations, even when they provided no architectural value.

Similarly, the Qt migration inventory required introducing intermediate
protocols and composition paths to relocate code that directly interacts with a
Qt scene, while forbidding desktop consumers from importing Qt adapters. ADR 0001
recorded this tension without defining a destination boundary.

## Decision

1. Organize by responsibility. A feature need not maintain separate access, port,
   service, state, and bundle modules. Keep related workflows cohesive until a
   distinct responsibility or dependency boundary justifies separation.
2. Use direct collaborators within the desktop editor. Constructor injection of
   concrete objects is sufficient. Controllers and tools may access owned public
   state and Qt APIs directly. Use access helpers only when addressing concrete
   boundaries—such as resolving active documents, adapting representations, or
   restricting operations. Do not create wrapper layers solely for forwarding.
3. Maintain a single owner for each state and mutation rule. Direct access must
   not introduce duplicate state or bypass transaction, invalidation, history,
   or graphics-item lifecycle management. Resolve active documents and replaceable
   models at invocation time.
4. Preserve Qt-free document and chemistry rules in `domain`, Qt-free `core`,
   and existing headless import contracts. Desktop feature implementations may
   use Qt and concrete adapters directly. Retire the Qt migration inventory.
   Headless feature APIs must remain usable without GUI dependencies.
5. Preserve feature public APIs, acyclic eager imports, optional RDKit startup,
   document compatibility, and the shared rendering and recovery owners from
   ADRs 0002–0004. Features and adapters must not depend on editor widgets or
   application startup.
6. Test contracts rather than implementation structure. Architectural tests
   enforce domain isolation, single state ownership, and recovery guarantees,
   rather than fixed inventories of forwarding helpers. When refactoring
   responsibilities, update structural tests alongside implementation while
   preserving behavioral verification. New boundary tests must verify both
   compliant cases and violation rejections.

## Scope and consequences

This decision updates development guidelines and architectural tests. Production
refactoring, schema modifications, and annotation ownership migration remain
scoped to subsequent feature work. Existing helper modules remain functional until
their callers are migrated and behaviorally verified.

The initial slice simplifies the move interaction path via the existing controller
and transaction owner. Verification covers movement, cancellation, Undo/Redo,
recovery from failed edits, and document switching. Critical coordination
boundaries—such as `CanvasHistoryOperations` and `SceneRenderContext`—remain intact.

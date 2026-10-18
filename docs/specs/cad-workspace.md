# CAD workspace (branch `cad-workspace`)

Open `/static/cad.html` (or CAD tab → "Open the CAD workspace"). Reopen a design with `?bid=<project id>`.

## How it fits the existing app
A CAD design is an ordinary **edit project**. Every solid feature is one history step (`meshedit.OPS`, implemented in `app/core/cadops.py`), so undo / redo / goto, editing a step with replay of later steps, delete, exports, slicing and the plate editor are the existing machinery (`app/services/editproj.py`). The first feature creates the project (`POST /api/cad/new`); it is step 1 and stays editable.

Steps store their full inputs, e.g. an extrude stores its sketch (entities + constraints), plane, picked regions, distance, direction and mode. Editing a step re-solves its sketch and replays every later step (all-or-nothing).

## Editing your own files
- **Open ▾ → Import STL, OBJ or 3MF** (or drag a file onto the view) uses the existing upload gate (`POST /api/edit/new`: size cap, content sniffing, units). The uploaded file is kept byte-for-byte and is shown in History as **Import 01 (kept as-is)**; tapping it rolls back to the file.
- **Open ▾ → From my builds** opens editable projects directly and makes an editable copy of other builds (the original is unchanged). Showcase items: remix/download into your builds first (no direct Showcase picker yet).
- Editor: after any upload, **✏️ Open in CAD** opens the same project in the workspace; the parts builder hand-off links there too.
- Every tool works on the imported mesh: tap a face to select body + face, sketch on that face, extrude join/cut, boolean, fillet/chamfer (approx.), face offset (planar), move/rotate/scale/mirror/pattern/align. Meshes that are not closed solids get a clear message; **Fix mesh** (Y) runs the existing repair step.
- **Export ▾ → Save as a new version** copies the current state into a new project; **Open in Slicer & plate editor** opens it in the Slicer.
- **STEP is not supported**: no permissive STEP importer is installed (the usual ones depend on OpenCascade, LGPL with a large native build). Convert to STL/3MF first.

## Ops (history steps)
| op | what | notes |
|---|---|---|
| `sketch_extrude` | closed sketch regions → solid; up / down / both; new / join / cut / intersect; taper | exact (manifold3d) |
| `revolve` | profile about an in-plane axis, 0.1–360° | profile must stay on one side of the axis |
| `body_boolean` | union / subtract / intersect two bodies | exact |
| `round_edges` | fillet (ball) or chamfer (octahedron) of outside edges, all or picked | **approximate**: morphological opening; inside corners are not filleted; the ends of picked edges blend into neighbouring corners; faceted; seconds of compute |
| `hollow` (Shell tool) | closed hollow with wall thickness (existing op) | open-face shell not available |
| `face_offset` | move a flat face's connected coplanar region along its normal | works on prismatic faces; side faces stretch |
| `body_transform` | move / rotate / scale (uniform or per axis) / mirror (with copy) one body or all | |
| `pattern` | linear (step) or circular (centre, axis, angle) copies, fused | |
| `align` | body min/centre/max on an axis to a value or another body | |

**Bodies** are the connected solids of the project mesh (a hollow stays with its body), numbered by position (centre x, then y, then z). A step that names a body uses that number when it is replayed, so editing an earlier step can renumber bodies.

## Sketch engine (`app/core/sketch.py`)
Entities: line, arc, circle, ellipse, polygon (regular), spline (Catmull-Rom through points), poly (from Offset). Constraints: coincident, horizontal, vertical, parallel, perpendicular, equal, tangent, concentric, lock, midpoint; dimensions length, radius, distance, angle. Solver: least squares on residuals with a small pull toward the drawn values, then an unpulled polish. Reports a degrees-of-freedom estimate (Jacobian rank) and "conflict" when residuals stay above 1e-5. Regions: even-odd over all closed loops (a loop inside a loop is a hole); click-to-pick elementary faces.

## Workspace UI (`static/cad.*`)
Left rail (icon + label + shortcut, beginner tooltip), History (expand → edit params → Update replays; Edit sketch; Roll to here; Rename; Delete), Items (bodies with eye toggle + colour swatch, sketches, grid/axes), CSS view cube (tap a face), grid-size chip, snap toggle, Fit, Section view (clipping slider on X/Y/Z, cut faces not capped), Measure (two points, or an edge), Search (Ctrl/⌘+F command palette), Deselect (Esc), undo/redo (Ctrl/⌘+Z, Shift for redo; inside a sketch Ctrl+Z undoes sketch edits), hint bubble. Sketch mode: Line/Arc (A toggles arc, 3-point), Rectangle (Alt = from centre), Circle, Ellipse, Polygon (n sides), Spline, Offset, Trim, Delete; tap a dimension label to type it (becomes a locked dimension, solved on the server); constraint badges (tap to remove); Auto-constraint (H/V within 3°, coincident on snap) and Show-constraints toggles. Visualize: per-body colour + finish (display only, saved per project). Export: STL / 3MF download, "Open in Slicer & plate editor" (`/?edit=<id>#slicer`).

Touch / Pencil: pointer events; one finger or Pencil draws in sketch mode, two fingers pan/zoom; 44 px targets; narrow screens collapse the rail to icons and move History under the view.

## Not done yet (honest list)
- True B-rep: geometry is a triangle mesh. Fillets/chamfers are approximate; no variable fillets; no face/edge persistent naming (body and face references are by number / position).
- Shell with removed faces; face offset of curved faces; sweep / loft; sketch on a picked face of a later edited body re-uses the stored plane (it does not follow the face).
- Sketch: no drag-to-dimension between arbitrary points in the UI (the API supports `distance`), no symmetry constraint, no construction-geometry toggle in the UI (the API supports `construction`), spline control by through-points only.
- Section view does not cap the cut faces. Measure has no angle/radius readout.
- Title edits after the project exists are not saved (rename the build from Recent builds).

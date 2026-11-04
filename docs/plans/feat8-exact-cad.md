# FEAT8: exact fillets, chamfers and face pushes in CAD

Status: planning doc. The "approximate" notes stay until the result is exact.

## Why it is approximate today
ZEIM's CAD works on triangle meshes. A mesh fillet or chamfer can only approximate a round edge, and
moving a face on a mesh is not dimensionally exact. Exact results need a boundary-representation (B-rep)
kernel that stores true surfaces and edges.

## Options
| Option | Licence | Runs | Notes |
|---|---|---|---|
| opencascade.js (OpenCascade compiled to WebAssembly) | LGPL-2.1 (with OCCT exception) | Browser | Full fillet/chamfer/offset; download is large (tens of MB, can be split); LGPL needs the library kept replaceable and its notice shown |
| replicad (on top of opencascade.js) | MIT wrapper; OCCT LGPL underneath | Browser | Friendlier API; same size and licence notes |
| CadQuery / build123d on the server | Apache-2.0 wrappers; OCCT LGPL | Server (Python) | Small client; each edit is a server round trip; uses server CPU |
| Manifold | Apache-2.0 | Browser | Fast and robust booleans, but mesh-based: no exact fillets |

Cost: no licence fees. Cost is engineering time, a larger first load for CAD (or server CPU), and moving
the CAD history to a B-rep model so that edits stay exact.

## Recommendation
Prototype with replicad in a separate CAD mode behind a default-off flag: one box → exact fillet → STEP/STL
export, measured with a known dimension. Remove an "approximate" note only for the operation proven exact.

## Decision needed (Zach)
Accept the LGPL notice and the bigger CAD download, or prefer the server route.

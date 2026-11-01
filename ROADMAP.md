# Glamour Blueprint Agent — Roadmap

Current state: 2D floor plan + elevation drawings, interactive 3D view,
fabric texture preview, hardware catalog with auto-populated specs.

---

## Phase 3 — Natural Language Input (Claude API)
**Trigger:** First paid retainer / spending gate unlocked

Fabian describes the job in plain language:
> "Living room at Boudreau, 20 feet wide, 9-foot ceiling, soffit is 14 inches
> deep, we're doing Silent Gliss with 4 panels, 90-inch drop"

Claude parses this → auto-fills the entire blueprint form.
No manual measurement entry. Works as a chat interface or voice-to-text input.

**What it needs:** Anthropic API key + spending gate open.
**Edge it creates:** No competitor in the upholstery space has this.

---

## Phase 4 — Photorealistic Rendering (External Renderer)
**Trigger:** When clients start asking "can I see what it actually looks like?"

Options (in order of effort):
1. **Stable Diffusion / ComfyUI** — run locally on Windows desktop, no recurring cost.
   Feed the 3D scene as a base image + fabric swatch → AI upscales to photorealistic.
2. **Replicate API** — cloud-based, pay-per-render. ~$0.10/image.
3. **Veras (by Evolve Lab)** — purpose-built for interior design rendering,
   accepts SketchUp/3D exports. $99/mo but industry quality.

**Edge it creates:** No upholstery shop in the area is doing photorealistic
client renders. First one to do it wins the high-end residential contracts.

---

## Phase 5 — BIM + Clash Detection
**Trigger:** When commercial contracts (hotels, offices) become a target market

- Objects have properties: weight, material, installation sequence
- Clash detection: flags if curtain drop hits furniture, track weight exceeds
  bracket rating, motorized track is too far from power outlet
- Export to IFC format (standard BIM exchange — architects and GCs can import
  directly into Revit/AutoCAD without conversion)

**Edge it creates:** Allows Glamour to bid on commercial projects alongside
architects and GCs, not just as a sub. Changes the tier of client.

---

## Phase 6 — AR Preview (Client-Facing Mobile)
**Trigger:** When Glamour wants a mobile client experience

Client points their phone at the room → sees the curtains in place via
augmented reality before installation. Uses Apple ARKit (iOS) or ARCore (Android).

Requires: a simple mobile web app or iOS app build.
No competitor in the residential upholstery market has this.

---

## Phase 7 — Client Portal
**Trigger:** When client volume makes back-and-forth email inefficient

Unique shareable link per project → client sees:
- Their room in 3D with their fabric applied
- Installation timeline
- Work order + invoice
- Approval button (sign off on specs before fabrication starts)

Eliminates "I didn't know it would look like that" disputes.

---

## Notes
- Phases 1–2 are done (floor plan, elevation, 3D, fabric textures, hardware catalog)
- Each phase is independent — can be built in any order based on what clients ask for
- Natural language input (Phase 3) has the highest ROI per hour of build time

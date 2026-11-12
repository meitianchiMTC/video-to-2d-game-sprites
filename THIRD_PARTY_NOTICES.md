# Third-party attribution

This skill adapts ideas and algorithms from **gary149/h3-game-sprites**:

- Repository: https://github.com/gary149/h3-game-sprites
- Reviewed upstream revision: `d1295576a3debe364d7d8a6023cfc7a9835e6522`
- Code source: `skills/h3-game-sprites/scripts/sprite_cut.py`
- Workflow source: `skills/h3-game-sprites/SKILL.md`
- Upstream copyright: Copyright (c) 2026 Victor Mustar
- License: MIT (full notice below).

Adapted in `scripts/video_sprites.py`: cumulative-motion arc-length sampling,
closest-pose cycle search, and magenta/green channel-cap despill. Generation
constraints and reference-pose guidance are summarized with source links in
`references/generation-preflight.md`.

Local changes include exact distinct frame counts, premultiplied-alpha motion
features, actual timestamp timing and cycle-duration bounds, velocity scoring,
static-candidate rejection, explicit edge-only despill by default, and reporting
candidates separately from visual acceptance. The upstream code's hard-coded
24 FPS timing, tautological background-purity metric, and per-frame strip
alignment are not adopted. No H3 API client or dependency on `h3-video` is included.
These changes do not imply upstream endorsement or guarantee seamless loops.

## Upstream license

MIT License

Copyright (c) 2026 Victor Mustar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"use client";

import Inspector from "./Inspector";

/**
 * The right column: the one thing you picked, and nothing else.
 *
 * It used to be split, with 에이전트 구조 above and 상세 below. Both halves were
 * worse for it. The drawing got 460x334 with a header and a two-line legend in
 * it, which React Flow fitted at scale(0.3) -- nodes rendered smaller than their
 * own labels. And 상세 got the other 500px to hold a finding's judgement, its
 * evidence trail, its patch *and* its decision chain, which is the densest thing
 * on the surface and the one that most wanted the height.
 *
 * The structure is an overlay now, at a size the drawing can actually be read
 * at, so this column goes back to the rule the rest of the surface runs on:
 * the panel below is many, this is one. `Inspector` was always the whole of
 * that -- this file had no other job than to put a graph on top of it.
 */
export default Inspector;

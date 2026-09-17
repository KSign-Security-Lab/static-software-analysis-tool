"use client";

import { useEffect, useLayoutEffect } from "react";

export const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;

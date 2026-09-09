#!/usr/bin/env node
/**
 * Licence gate over the installed dependency tree.
 *
 * Reads `pnpm licenses list`, which reports what the lockfile resolved and the
 * store actually holds -- including platform-conditional optional
 * dependencies, which is the case that actually bites here: the LGPL libvips
 * binaries exist on linux-x64 and not on darwin-arm64, and a checker that
 * disagrees with the tree by platform is worse than none.
 *
 * There is no `extraneous` tier any more. Under npm, arborist reported a
 * package no manifest edge reaches as `dev: true`, so an undeclared one sailed
 * through the lenient tier and this had to force it back to production. pnpm
 * builds `node_modules` from the lockfile and prunes what is not in it, so the
 * listing cannot contain an undeclared package -- and anything hand-placed
 * there is invisible to this gate rather than mislabelled by it. What keeps the
 * lockfile honest is CI installing with `--frozen-lockfile`, which fails when
 * it and `package.json` disagree.
 *
 * No dependencies, on purpose. A licence gate that pulls in thirty transitive
 * packages has enlarged the thing it was meant to audit.
 *
 *   node scripts/licenses.mjs                  verify, exit 1 on failure
 *   node scripts/licenses.mjs --write-notices  regenerate THIRD-PARTY-NOTICES.md
 *   node scripts/licenses.mjs --check-notices  fail if that file is stale
 */

import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CONFIG = join(WEB, "licenses.config.json");
const NOTICES = join(WEB, "THIRD-PARTY-NOTICES.md");

/* -- SPDX -------------------------------------------------------------------
 *
 * Enough of the expression grammar to answer "may we use this, and under
 * which licence". `OR` picks the first allowed disjunct and records it --
 * `(MPL-2.0 OR Apache-2.0)` on dompurify is a real production dependency here,
 * and substring matching on that string gets the wrong answer. `AND` requires
 * all of them. `WITH` binds tighter than either and travels with its id.
 */

export function tokenize(expr) {
  return expr
    .replace(/([()])/g, " $1 ")
    .split(/\s+/)
    .filter(Boolean);
}

export function parseExpression(tokens) {
  let i = 0;

  const peek = () => tokens[i];
  const next = () => tokens[i++];

  function atom() {
    if (peek() === "(") {
      next();
      const inner = or();
      if (peek() !== ")") throw new Error("unbalanced parentheses");
      next();
      return inner;
    }
    const id = next();
    if (id === undefined) throw new Error("unexpected end of expression");
    if (/^(AND|OR|WITH)$/i.test(id)) throw new Error(`unexpected operator ${id}`);
    if (peek() && peek().toUpperCase() === "WITH") {
      next();
      const exception = next();
      if (!exception) throw new Error("WITH without an exception id");
      return { kind: "id", id: `${id} WITH ${exception}` };
    }
    return { kind: "id", id };
  }

  function and() {
    const parts = [atom()];
    while (peek() && peek().toUpperCase() === "AND") {
      next();
      parts.push(atom());
    }
    return parts.length === 1 ? parts[0] : { kind: "and", parts };
  }

  function or() {
    const parts = [and()];
    while (peek() && peek().toUpperCase() === "OR") {
      next();
      parts.push(and());
    }
    return parts.length === 1 ? parts[0] : { kind: "or", parts };
  }

  const tree = or();
  if (i !== tokens.length) throw new Error(`trailing tokens after expression: ${tokens.slice(i).join(" ")}`);
  return tree;
}

/** `{ ok, elected }` -- `elected` is the disjunct we are relying on. */
export function evaluate(node, allowed) {
  if (node.kind === "id") {
    // `GPL-2.0+` and the deprecated `-only`/`-or-later` pairs are distinct ids;
    // we compare literally rather than guessing at equivalences.
    return { ok: allowed(node.id), elected: node.id };
  }
  if (node.kind === "and") {
    const parts = node.parts.map((p) => evaluate(p, allowed));
    return { ok: parts.every((p) => p.ok), elected: parts.map((p) => p.elected).join(" AND ") };
  }
  for (const part of node.parts) {
    const result = evaluate(part, allowed);
    if (result.ok) return result;
  }
  return { ok: false, elected: null };
}

/**
 * A licence string the gate can reason about, or a reason it cannot.
 * Anything unreadable fails closed: it can only be cleared by an exception
 * entry, which forces someone to open the package and read the file.
 */
export function classify(license) {
  if (license === undefined || license === null || license === "") return { readable: false, why: "no licence declared" };
  const text = typeof license === "string" ? license : license.type;
  if (!text) return { readable: false, why: "no licence declared" };
  if (/^SEE LICEN[CS]E IN /i.test(text)) return { readable: false, why: text };
  if (/^(UNKNOWN|UNLICEN[CS]ED)$/i.test(text)) return { readable: false, why: text };
  return { readable: true, text };
}

/* -- the tree ---------------------------------------------------------------- */

function listing(...flags) {
  const raw = execFileSync("pnpm", ["licenses", "list", "--json", ...flags], {
    cwd: WEB,
    encoding: "utf8",
    maxBuffer: 256 << 20,
  });
  // Empty output rather than `{}` when a filter matches nothing.
  return raw.trim() ? JSON.parse(raw) : {};
}

/** `{ licence: [{ name, versions, paths }] }` into one row per `name@version`. */
export function flatten(groups) {
  const rows = [];
  for (const entries of Object.values(groups ?? {})) {
    for (const entry of entries) {
      // `versions` and `paths` are parallel; two versions of one package are
      // two rows, because they can be licensed differently.
      entry.versions.forEach((version, index) => {
        rows.push({
          id: `${entry.name}@${version}`,
          name: entry.name,
          version,
          license: entry.license,
          path: entry.paths?.[index] ?? entry.paths?.[0],
        });
      });
    }
  }
  return rows;
}

/**
 * One row per package, in the strictest tier that reaches it. First listing to
 * claim a package wins, so the order of the three is the tiering rule.
 *
 * A package reached both as a dev and as a production dependency is
 * production, or a copyleft dependency hides behind whichever listing happened
 * to be read first. Dev comes last for the reason the tier is looser at all --
 * a platform binary that only ever runs the build, vitest's bundler or
 * eslint's resolver, does not put its licence on our output. Only a dependency
 * a production edge reaches earns strict treatment.
 *
 * `dev` is therefore passed the *whole* tree rather than a dev-only listing:
 * whatever the first two did not claim is, by definition, reached by no
 * production edge, and nothing can fall out of the audit by not matching a
 * filter.
 *
 * @template {{id: string}} Row
 * @param {{production?: Row[], optional?: Row[], dev?: Row[]}} listings
 * @returns {(Row & {tier: "production" | "optional" | "dev"})[]}
 */
export function assign({ production = [], optional = [], dev = [] }) {
  const byId = new Map();
  for (const [tier, rows] of [
    ["production", production],
    ["optional", optional],
    ["dev", dev],
  ]) {
    for (const row of rows) {
      if (!byId.has(row.id)) byId.set(row.id, { ...row, tier });
    }
  }
  return [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
}

function collect() {
  // Three listings rather than one labelled tree, narrowest first. `--prod` is
  // `dependencies` *plus* `optionalDependencies`, so what it has over `--prod
  // --no-optional` is the optional set; there is no flag that asks for that
  // directly.
  //
  // The third is unfiltered on purpose. `--dev` is not the complement of
  // `--prod`: it leaves out the optional dependencies *of* dev dependencies,
  // which is where four native binaries live -- among them lightningcss's,
  // under MPL-2.0, which is not on the allowlist. Using `--dev` here dropped
  // all four out of the audit entirely rather than tiering them.
  const production = flatten(listing("--prod", "--no-optional"));
  const shipped = flatten(listing("--prod"));
  const everything = flatten(listing());

  return {
    // Ourselves, read rather than asked for: pnpm reports the workspace's
    // dependencies, not the importer, and this only needs the licence field.
    root: JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")),
    packages: assign({ production, optional: shipped, dev: everything }),
  };
}

/* -- verdicts ----------------------------------------------------------------- */

export function verify(config, packages, today) {
  const allow = new Set(config.allow);
  const deny = new Set(config.denyAlways);
  const exceptions = config.exceptions ?? {};
  const usedExceptions = new Set();

  const failures = [];
  const warnings = [];
  const rows = [];

  for (const pkg of packages) {
    const tier = pkg.tier;
    const exception = exceptions[pkg.id];
    const { readable, text, why } = classify(pkg.license);

    let verdict = null; // { status, elected }

    if (readable) {
      const tree = (() => {
        try {
          return parseExpression(tokenize(text));
        } catch (err) {
          return err;
        }
      })();

      if (tree instanceof Error) {
        failures.push(`${pkg.id} [${tier}] — unparseable SPDX expression ${JSON.stringify(text)}: ${tree.message}`);
        continue;
      }

      const denied = evaluate(tree, (id) => deny.has(id));
      // A deny-listed id anywhere is fatal in every tier, including dev.
      if (denied.ok) {
        failures.push(`${pkg.id} [${tier}] — ${text} is on the deny list`);
        continue;
      }

      if (tier === "dev") {
        verdict = { status: "dev", elected: text };
      } else {
        const permitted = evaluate(tree, (id) => allow.has(id));
        if (permitted.ok) {
          verdict = { status: "allowed", elected: permitted.elected };
        }
      }
    }

    if (!verdict) {
      if (exception) {
        usedExceptions.add(pkg.id);
        const declared = readable ? text : (why ?? "unreadable");
        if (exception.license && exception.license !== declared) {
          failures.push(
            `${pkg.id} [${tier}] — exception records ${JSON.stringify(exception.license)} but the package now declares ` +
              `${JSON.stringify(declared)}. Re-review.`,
          );
          continue;
        }
        if (!exception.reason || !exception.reason.trim()) {
          failures.push(`${pkg.id} [${tier}] — exception has no reason`);
          continue;
        }
        if (exception.expires && exception.expires < today) {
          failures.push(`${pkg.id} [${tier}] — exception expired on ${exception.expires}. Re-review.`);
          continue;
        }
        verdict = { status: "excepted", elected: declared };
      } else {
        const detail = readable ? text : why;
        failures.push(
          `${pkg.id} [${tier}] — ${detail} is not allowed and has no exception` +
            (readable ? "" : `\n      (read ${join(pkg.path ?? "", "LICENSE")} and record the reviewed SPDX id)`),
        );
        continue;
      }
    }

    rows.push({ ...pkg, tier, ...verdict });
  }

  for (const [id, exception] of Object.entries(exceptions)) {
    if (usedExceptions.has(id)) continue;
    // Platform binaries legitimately vanish on another OS or arch; anything
    // else that matches nothing is how an allowlist quietly goes permissive.
    const message = `exception for ${id} matches nothing installed`;
    if (exception.platformConditional) warnings.push(`${message} (platform-conditional; not an error here)`);
    else failures.push(`${message} — remove it or restore the dependency`);
  }

  return { rows, failures, warnings };
}

/* -- notices ------------------------------------------------------------------ */

const LICENCE_FILE = /^(LICEN[CS]E|COPYING|COPYRIGHT)(\..*)?$/i;
const NOTICE_FILE = /^NOTICE(\..*)?$/i;

function readTexts(dir, match) {
  if (!dir) return [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out = [];
  for (const entry of entries) {
    if (!entry.isFile() || !match.test(entry.name)) continue;
    try {
      out.push({ file: entry.name, text: readFileSync(join(dir, entry.name), "utf8").trimEnd() });
    } catch {
      /* unreadable; the caller records the absence */
    }
  }
  return out;
}

function renderNotices(rows) {
  // Production only: these are the packages whose code we redistribute, and
  // every permissive licence in the allowlist requires the notice travel with
  // it. Apache-2.0 s4(d) additionally requires any NOTICE file be propagated.
  const shipped = rows.filter((r) => r.tier === "production").sort((a, b) => a.id.localeCompare(b.id));

  const out = [
    "# Third-party notices",
    "",
    "Generated by `pnpm run licenses:notices` — do not edit by hand.",
    "",
    "The SSAT web UI redistributes the packages below. Where a licence offers a",
    "choice, the licence this project relies on is marked *elected*.",
    "",
    `${shipped.length} packages.`,
    "",
    "---",
    "",
  ];

  for (const row of shipped) {
    out.push(`## ${row.name}@${row.version}`, "");
    const declared = classify(row.license);
    out.push(`- Declared: \`${declared.readable ? declared.text : (declared.why ?? "none")}\``);
    if (row.elected && declared.readable && row.elected !== declared.text) out.push(`- Elected: \`${row.elected}\``);
    if (row.status === "excepted") out.push(`- Reviewed exception (see \`licenses.config.json\`)`);
    out.push("");

    const licences = readTexts(row.path, LICENCE_FILE);
    if (licences.length === 0) {
      out.push(
        "> This package ships no licence file. The canonical text for the declared",
        "> identifier applies; see https://spdx.org/licenses/ .",
        "",
      );
    }
    for (const { file, text } of licences) {
      out.push(`<details><summary>${file}</summary>`, "", "```", text, "```", "", "</details>", "");
    }
    for (const { file, text } of readTexts(row.path, NOTICE_FILE)) {
      out.push(`<details><summary>${file} (Apache-2.0 §4(d))</summary>`, "", "```", text, "```", "", "</details>", "");
    }
    out.push("---", "");
  }

  return out.join("\n");
}

/* -- report ------------------------------------------------------------------- */

function summarise(rows) {
  const tiers = { production: 0, dev: 0, optional: 0 };
  const licences = new Map();
  for (const row of rows) {
    tiers[row.tier] += 1;
    if (row.tier === "production") licences.set(row.elected, (licences.get(row.elected) ?? 0) + 1);
  }
  return { tiers, licences: [...licences.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])) };
}

function main() {
  const args = new Set(process.argv.slice(2));
  const config = JSON.parse(readFileSync(CONFIG, "utf8"));
  const today = new Date().toISOString().slice(0, 10);

  const { root, packages } = collect();
  const { rows, failures, warnings } = verify(config, packages, today);

  // A repo that demands an SPDX id from every dependency should declare one.
  // Any non-empty string counts, `UNLICENSED` included: for ourselves that is
  // a deliberate "not published, all rights reserved", not an unreadable grant
  // we are being asked to rely on.
  const declared = typeof root?.license === "string" ? root.license.trim() : "";
  if (!declared) failures.push(`this package declares no licence — set "license" in web/package.json`);

  const { tiers, licences } = summarise(rows);

  if (args.has("--write-notices")) {
    writeFileSync(NOTICES, renderNotices(rows));
    console.log(`wrote ${NOTICES}`);
  } else if (args.has("--check-notices")) {
    let current = "";
    try {
      current = readFileSync(NOTICES, "utf8");
    } catch {
      failures.push("THIRD-PARTY-NOTICES.md is missing — run `pnpm run licenses:notices`");
    }
    if (current && current !== renderNotices(rows)) {
      failures.push("THIRD-PARTY-NOTICES.md is out of date — run `pnpm run licenses:notices`");
    }
  }

  console.log(
    `licences: ${rows.length} packages — ` +
      `${tiers.production} production, ${tiers.dev} dev, ${tiers.optional} optional`,
  );
  console.log("production licences: " + licences.map(([id, n]) => `${id}×${n}`).join(", "));

  const excepted = rows.filter((r) => r.status === "excepted");
  if (excepted.length) {
    console.log("\nreviewed exceptions:");
    for (const row of excepted) console.log(`  ${row.id} — ${row.elected}`);
  }

  for (const warning of warnings) console.log(`\nwarning: ${warning}`);

  if (failures.length) {
    console.error(`\n${failures.length} licence problem(s):\n`);
    for (const failure of failures) console.error(`  ✗ ${failure}`);
    console.error("\nAllow it in web/licenses.config.json only with a written reason.");
    process.exit(1);
  }

  console.log("\nok — every dependency is permissively licensed or has a reviewed exception.");
}

// Importable for its tests; only walks the tree when run as a command.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();

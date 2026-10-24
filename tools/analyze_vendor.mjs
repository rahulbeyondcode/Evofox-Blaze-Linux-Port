// Run focused STATIC queries in one private REA MCP session. No agent
// registration, target execution, device access, or binary modification.
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [prefixArg, binaryArg, outputArg, snapshotArg, planArg] = process.argv.slice(2);
if (!prefixArg || !binaryArg || !outputArg) {
  console.error("Usage: node tools/analyze_vendor.mjs REA_NPM_PREFIX APPLICATION NEW_OUTPUT_DIR [SNAPSHOT|-] [PLAN_JSON]");
  process.exit(1);
}
const prefix = resolve(prefixArg);
const binary = resolve(binaryArg);
const output = resolve(outputArg);
const expected = "9eec736ee629ff9d0684f787a270afe86d064fdcf23e7eb11f921dc7844eee55";
const hash = async () => createHash("sha256").update(await readFile(binary)).digest("hex");
if (await hash() !== expected) throw new Error("Not the documented EvoFox application hash");
const plan = planArg ? JSON.parse(await readFile(resolve(planArg), "utf8")) : {
  procedures: ["0x413910", "0x413a10", "0x413ac0", "0x413b90"],
  xrefs: ["0x5d17bd", "0x5d17c3", "0x413ac0", "0x413910"],
};
const planKeys = ["procedures", "xrefs", "pseudocode", "instructions"];
if (plan === null || typeof plan !== "object" || Array.isArray(plan)
    || Object.keys(plan).some(key => !planKeys.includes(key))) {
  throw new Error("Analysis plan permits only procedures, xrefs, pseudocode and instructions arrays");
}
for (const key of planKeys) {
  if (!(key in plan) && ["pseudocode", "instructions"].includes(key)) continue;
  if (!Array.isArray(plan[key]) || plan[key].length > 32
      || plan[key].some(value => typeof value !== "string" || !/^0x[0-9a-f]{1,16}$/.test(value))
      || new Set(plan[key]).size !== plan[key].length) {
    throw new Error(`Plan ${key} must contain at most 32 unique lowercase hexadecimal addresses`);
  }
}

const sdk = resolve(prefix, "node_modules/@modelcontextprotocol/client/dist");
const { Client } = await import(pathToFileURL(resolve(sdk, "index.mjs")));
const { StdioClientTransport } = await import(pathToFileURL(resolve(sdk, "stdio.mjs")));
const packageRoot = resolve(prefix, "node_modules/rea-agents");
const pkg = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8"));
await mkdir(dirname(output), { recursive: true });
await mkdir(output); // Refuse to overwrite an earlier investigation.
const save = (name, value) => writeFile(resolve(output, name), JSON.stringify(value, null, 2) + "\n", { flag: "wx" });
await save("run.json", {
  application_sha256: expected,
  rea_version: pkg.version,
  node_version: process.version,
  started_at: new Date().toISOString(),
  provider: "ghidra",
  scope: "Static packet-builder and readback investigation; no target execution",
  plan,
});

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [resolve(packageRoot, "scripts/rea.mjs"), "mcp"],
  env: { ...process.env },
  stderr: "inherit",
});
const client = new Client({ name: "evofox-static-research", version: "0.1.0" });
let opened = false;
let exported = false;
let available;
async function call(name, args, filename) {
  if (!available.has(name)) throw new Error(`Installed REA does not advertise ${name}`);
  const result = await client.callTool({ name, arguments: args }, { timeout: 660000 });
  await save(filename, result);
  console.log(JSON.stringify({ tool: name, arguments: args, file: filename, error: result.isError === true }));
  if (result.isError) throw new Error(`REA query failed; inspect ${filename}`);
  return result;
}
try {
  await client.connect(transport);
  const catalog = await client.listTools();
  available = new Set(catalog.tools.map(tool => tool.name));
  const used = new Set(["open_binary", "analyze_function", "xrefs", "procedure_pseudo_code",
    "inspect_native_instruction", "export_evidence_bundle", "close_binary"]);
  await save("tool-inputs.json", catalog.tools.filter(tool => used.has(tool.name)).map(tool => ({ name: tool.name, inputSchema: tool.inputSchema })));
  await call("open_binary", {
    path: binary,
    provider_id: "ghidra",
    ...(snapshotArg && snapshotArg !== "-" ? { snapshot_path: resolve(snapshotArg) } : {}),
  }, "open.json");
  opened = true;
  for (const procedure of plan.procedures) {
    await call("analyze_function", { procedure }, `function-${procedure}.json`);
  }
  for (const address of plan.xrefs) {
    await call("xrefs", { address }, `xrefs-${address}.json`);
  }
  for (const procedure of plan.pseudocode ?? []) {
    await call("procedure_pseudo_code", { procedure }, `pseudocode-${procedure}.json`);
  }
  for (const address of plan.instructions ?? []) {
    await call("inspect_native_instruction", { address }, `instruction-${address}.json`);
  }
  await call("export_evidence_bundle", { path: resolve(output, "evidence.json") }, "export.json");
  exported = true;
} finally {
  try {
    if (opened) {
      try {
        if (!exported) {
          await call("export_evidence_bundle", { path: resolve(output, "partial-evidence.json") }, "partial-export.json");
        }
      } finally {
        await call("close_binary", { snapshot_path: resolve(output, "snapshot.json") }, "close.json");
      }
    }
  } finally {
    await client.close();
    if (await hash() !== expected) throw new Error("Application bytes changed during analysis");
  }
}

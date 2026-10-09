import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { InputData, JSONSchemaInput, quicktype } from "quicktype-core";

// Only profiles with a current server consumer are generated. Enrollment/sync
// remain schema contracts until their implementation needs DTOs.
const names = {
  health: ["health-response", "HealthResponse"],
  ready: ["ready-response", "ReadyResponse"],
  source: ["source-response", "SourceResponse"],
  telemetry: ["telemetry-event", "TelemetryEvent"],
};
const authNames = [
  "AuthMethods", "EmailChallengeRequest", "EmailChallenge", "EmailVerifyRequest",
  "Session", "SessionIssued", "GithubStart", "GithubExchangeRequest", "GithubPending", "GithubApprovalForm", "Error",
];
const [language, selected, output] = process.argv.slice(2);
if (!["rust", "dart"].includes(language) || !(Object.hasOwn(names, selected) || selected === "auth") || !output) {
  throw new Error("Usage: node scripts/generate-dtos.mjs rust|dart health|ready|source|auth|telemetry OUTPUT");
}
if (selected === "telemetry" && language !== "rust") {
  throw new Error("Telemetry currently has only a Rust consumer");
}
const path = selected === "auth"
  ? "contracts/v2/control-plane.schema.json"
  : selected === "telemetry" ? "contracts/v2/telemetry-event.schema.json"
  : `contracts/v1/${names[selected][0]}.schema.json`;
const source = readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const document = JSON.parse(source);
const emittedObjects = selected === "auth" ? authNames.map((name) => document.$defs[name]) : [document];
if (emittedObjects.some((object) => object.type !== "object" || object.additionalProperties !== false)) {
  throw new Error("This DTO profile requires reviewed closed object schemas");
}
const lock = readFileSync(new URL("../package-lock.json", import.meta.url));
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const input = new JSONSchemaInput(undefined);
if (selected === "auth") {
  for (const [index, name] of authNames.entries()) {
    await input.addSource({ name, uris: [`${document.$id}#/$defs/${name}`],
      ...(index === 0 ? { schema: source } : {}),
    });
  }
} else {
  await input.addSource({ name: names[selected][1], schema: source });
}
const inputData = new InputData();
inputData.addInput(input);
const provenance = [
  "Generated; do not edit. AGPL-3.0-only. NDDev OpenNetwork — https://nddev.ai",
  `Source: NDDev-OpenNetwork/nddev-device-sync-protocol/${path}`,
  `Schema SHA-256: ${sha256(source)}`,
  `Generator script SHA-256: ${sha256(readFileSync(new URL(import.meta.url)))}`,
  `Tool: quicktype-core 26.0.0; dependency lock SHA-256: ${sha256(lock)}`,
  "DTO generation is not schema, authorization or cryptographic validation.",
];
const result = await quicktype({
  lang: language,
  inputData,
  // Preserve the exact wire timestamp; domain/UI code chooses date-time parsing.
  inferDateTimes: false,
  leadingComments: language === "rust" ? undefined : provenance,
  rendererOptions: language === "rust"
    ? { visibility: "public", "leading-comments": "false", "derive-debug": "false", "derive-clone": "true", "skip-serializing-none": "true" }
    : { "required-props": "false", "final-props": "true", "coders-in-class": "true" },
});
// Every emitted object in these reviewed profiles has additionalProperties:false.
// quicktype emits shapes, not this Serde policy: keep the mechanical projection
// here, never as handwritten changes in a consumer's generated file.
const lines = result.lines.flatMap((line) => language === "rust" && line.startsWith("pub struct ")
  ? ["#[serde(deny_unknown_fields)]", line] : [line]);
if (language === "rust" && result.lines.filter((line) => line.startsWith("pub struct ")).length !== emittedObjects.length) {
  throw new Error("Unexpected generated object graph; review the closed-object profile");
}
const header = language === "rust" ? provenance.map((line) => `// ${line}`).join("\n") + "\n\n" : "";
writeFileSync(output, header + lines.join("\n") + "\n");

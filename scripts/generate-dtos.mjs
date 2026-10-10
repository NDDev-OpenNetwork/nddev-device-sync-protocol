import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { InputData, JSONSchemaInput, JSONSchemaStore, quicktype } from "quicktype-core";

// Generate only profiles with identified current consumers; sync remains a
// schema contract until its implementation needs DTOs.
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
const deviceNames = ["EnrollmentRequest", "EnrollmentChallenge", "EnrollmentProof", "Device", "DeviceList", "Error"];
const observabilityNames = ["Incident", "IncidentPage", "IncidentAction", "SilenceAction", "SourceHealth",
  "IngressReceipt", "SignalDelivery", "ObservabilityStatus", "ObservabilityError"];
const [language, selected, output] = process.argv.slice(2);
if (!["rust", "dart"].includes(language) || !(Object.hasOwn(names, selected) || ["auth", "devices", "observability"].includes(selected)) || !output) {
  throw new Error("Usage: node scripts/generate-dtos.mjs rust|dart health|ready|source|auth|devices|telemetry|observability OUTPUT");
}
if (["telemetry", "observability"].includes(selected) && language !== "rust") {
  throw new Error("Observability currently has only a Rust consumer");
}
const path = ["auth", "devices"].includes(selected)
  ? "contracts/v2/control-plane.schema.json"
  : selected === "observability" ? "contracts/v2/observability.schema.json"
  : selected === "telemetry" ? "contracts/v2/telemetry-event.schema.json"
  : `contracts/v1/${names[selected][0]}.schema.json`;
const source = readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const document = JSON.parse(source);
const selectedNames = selected === "auth" ? authNames : selected === "devices" ? deviceNames : selected === "observability" ? observabilityNames : undefined;
const emittedObjects = selectedNames ? selectedNames.map((name) => document.$defs[name]) : [document];
if (emittedObjects.some((object) => object.type !== "object" || object.additionalProperties !== false)) {
  throw new Error("This DTO profile requires reviewed closed object schemas");
}
const lock = readFileSync(new URL("../package-lock.json", import.meta.url));
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const sharedPath = "contracts/v2/control-plane.schema.json";
const sharedSource = readFileSync(new URL(`../${sharedPath}`, import.meta.url), "utf8");
const sharedSchema = JSON.parse(sharedSource);
class LocalStore extends JSONSchemaStore {
  async fetch(address) { return address === sharedSchema.$id ? sharedSchema : undefined; }
}
const input = new JSONSchemaInput(new LocalStore());
if (selectedNames) {
  for (const [index, name] of selectedNames.entries()) {
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
if (selected === "observability") provenance.push(`Shared schema SHA-256: ${sha256(sharedSource)}`);
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
const lines = [];
let currentObject;
let renamedField;
let needsRequiredNullable = false;
let nullableDartFactory = false;
for (const originalLine of result.lines) {
  let line = originalLine;
  if (language === "dart") {
    const factory = line.match(/^(\s*)factory (\w+)\.fromJson\(Map<String, dynamic> json\) => (.*)/);
    const object = factory && (selectedNames ? document.$defs[factory[2]] : document);
    const nullable = object?.required?.filter((name) => object.properties[name]?.anyOf?.some((kind) => kind.type === "null")) ?? [];
    if (factory && nullable.length) {
      lines.push(`${factory[1]}factory ${factory[2]}.fromJson(Map<String, dynamic> json) {`);
      for (const name of nullable) lines.push(`${factory[1]}  if (!json.containsKey(${JSON.stringify(name)})) throw FormatException('required field is missing');`);
      line = `${factory[1]}  return ${factory[3]}`;
      nullableDartFactory = true;
    } else if (nullableDartFactory && line.trim() === ");") {
      lines.push(line, "    }");
      nullableDartFactory = false;
      continue;
    }
  }
  if (language === "rust" && line.startsWith("pub struct ")) {
    const name = line.match(/^pub struct (\w+)/)[1];
    currentObject = selectedNames ? document.$defs[name] : document;
    lines.push("#[serde(deny_unknown_fields)]");
  }
  if (language === "rust") {
    const rename = line.match(/^\s*#\[serde\(rename = "([^"]+)"\)\]/);
    if (rename) renamedField = rename[1];
    const field = line.match(/^\s*pub (\w+): Option</);
    if (field) {
      const property = renamedField ?? field[1];
      if (currentObject?.required?.includes(property)) {
        // Serde Option normally accepts a missing key. Required JSON null is a
        // distinct contract: retain null on output and require key presence.
        if (lines.at(-1)?.includes('skip_serializing_if = "Option::is_none"')) lines.pop();
        lines.push('    #[serde(deserialize_with = "deserialize_required_nullable")]');
        needsRequiredNullable = true;
      }
    }
    if (/^\s*pub \w+:/.test(line)) renamedField = undefined;
  }
  lines.push(line);
}
if (needsRequiredNullable) lines.push(
  "",
  "fn deserialize_required_nullable<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>",
  "where D: serde::Deserializer<'de>, T: serde::Deserialize<'de> {",
  "    Option::<T>::deserialize(deserializer)",
  "}",
);
if (language === "rust" && result.lines.filter((line) => line.startsWith("pub struct ")).length !== emittedObjects.length) {
  throw new Error("Unexpected generated object graph; review the closed-object profile");
}
const header = language === "rust" ? provenance.map((line) => `// ${line}`).join("\n") + "\n\n" : "";
writeFileSync(output, header + lines.join("\n") + "\n");

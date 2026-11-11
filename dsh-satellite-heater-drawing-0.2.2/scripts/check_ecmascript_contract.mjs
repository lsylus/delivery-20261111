import fs from "node:fs";

const root = new URL("../", import.meta.url);
const schema = JSON.parse(
  fs.readFileSync(new URL("schemas/heater-row.schema.json", root), "utf8"),
);
const definitions = schema.$defs;
const positive = new RegExp(
  definitions.HeaterFields.properties.width_mm.pattern,
);
const scale = new RegExp(
  definitions.HeaterFields.properties.requested_scale.pattern,
);
const rowId = new RegExp(schema.properties.row_id.pattern);

const cases = [
  [positive, ["0.001", "1", "1.5", "200"], ["0", "-1", "1e2", "01", "1٢", "1\n"]],
  [scale, ["1:1", "1:1.5", "1:2"], ["1:0.5", "1:0", "1:-1", "1:NaN", "1:Inf", "1:2\n"]],
  [rowId, ["Sheet1:2", "Sheet1:9", "Sheet1:10", "Sheet1:100"], ["Sheet1:1", "Sheet1:true", "Sheet1:2\n"]],
];

const failures = [];
for (const [pattern, accepted, rejected] of cases) {
  for (const value of accepted) {
    if (!pattern.test(value)) failures.push({ value, expected: true });
  }
  for (const value of rejected) {
    if (pattern.test(value)) failures.push({ value, expected: false });
  }
}
console.log(JSON.stringify({ runtime: process.version, failures }));
if (failures.length) process.exit(1);

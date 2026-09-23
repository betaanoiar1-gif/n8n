const fs = require("fs");
const vm = require("vm");
function main() {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const previous = input.previous || {};
  const env = input.env || process.env;
  const execution = input.execution || { id: "python-" + Date.now(), mode: "manual" };
  const current = input.current || { json: {}, binary: undefined };
  function wrap(name) {
    const v = previous[name];
    return { first: () => v || { json: {}, binary: undefined }, item: v || { json: {}, binary: undefined }, all: () => v ? [v] : [] };
  }
  const $ = name => wrap(String(name));
  const $input = { first: () => current, item: current, all: () => [current], allData: () => [current].map(x => x.json) };
  const context = {
    $json: current.json || {}, $binary: current.binary, $env: env, $execution: execution, $input, $,
    console, JSON, Date, URL, Error, Buffer, Math, Number, String, Boolean, RegExp, Object, Array, Promise,
    parseInt, parseFloat, isNaN, isFinite, setTimeout, clearTimeout
  };
  vm.createContext(context);
  let result;
  if (input.mode === "code") result = new vm.Script(input.source).runInContext(context, { timeout: input.timeoutMs || 120000 });
  else result = new vm.Script("(" + input.source + ")").runInContext(context, { timeout: input.timeoutMs || 30000 });
  process.stdout.write(JSON.stringify(result === undefined ? null : result));
}
try { main(); } catch (e) {
  process.stderr.write(JSON.stringify({message: String(e?.message || e), stack: String(e?.stack || "")}));
  process.exit(1);
}

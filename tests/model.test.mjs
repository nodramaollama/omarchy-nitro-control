import assert from "node:assert/strict"
import { createRequire } from "node:module"

const require = createRequire(import.meta.url)
const Model = require("../NitroModel.js")

const state = Model.parseStatus(JSON.stringify({
  ok: true,
  backend: "ready",
  isNitro: true,
  sensorAvailable: true,
  controlAvailable: true,
  temperatures: { cpu: 61, gpu: 50 },
  fans: { cpu: { rpm: 2238 }, gpu: { rpm: 2654 } },
  mode: "automatic",
  profile: "balanced"
}))

assert.equal(state.temperatures.cpu, 61)
assert.equal(state.fans.gpu.rpm, 2654)
assert.equal(Model.temperature(61), "61°")
assert.match(Model.rpm(2238), /2.*238 RPM/)
assert.equal(Model.statusLine(state), "Automatic · balanced")
assert.equal(Model.clampManual(4), 20)
assert.equal(Model.clampManual(104), 100)
assert.equal(Model.profileTitle("balanced-performance"), "Balanced Performance")

const hostile = Model.parseStatus(JSON.stringify({
  ok: true,
  backend: "ready",
  vendor: "<b>Acer</b>\u0000",
  model: "<img src=x>",
  temperatures: { cpu: 9999 },
  fans: { cpu: { rpm: -1 } },
  profile: "<script>alert(1)</script>",
  profileChoices: Array.from({ length: 20 }, (_, index) => `<b>profile-${index}</b>`),
  error: "<b>unsafe</b>\nnext"
}))
assert.equal(hostile.vendor.includes("<"), false)
assert.equal(hostile.model.includes(">"), false)
assert.equal(hostile.temperatures.cpu, null)
assert.equal(hostile.fans.cpu.rpm, null)
assert.equal(hostile.profileChoices.length, 8)
assert.equal(hostile.error.includes("\n"), false)

const oversized = Model.parseStatus("x".repeat(Model.MAX_RESPONSE_CHARS + 1), state)
assert.equal(oversized.ok, false)
assert.match(oversized.error, /safety limit/)

const bad = Model.parseStatus("not json", state)
assert.equal(bad.ok, false)
assert.equal(bad.temperatures.cpu, 61)

console.log("NitroModel tests passed")

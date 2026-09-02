var MAX_RESPONSE_CHARS = 32768
var MAX_TEXT_CHARS = 256
var MAX_ERROR_CHARS = 512
var MAX_PROFILE_CHOICES = 8

function plainText(value, limit) {
  var source = String(value === null || value === undefined ? "" : value)
  var output = ""
  var maximum = Math.max(0, Number(limit) || MAX_TEXT_CHARS)
  for (var index = 0; index < source.length && output.length < maximum; index++) {
    var code = source.charCodeAt(index)
    var character = source.charAt(index)
    if (code < 32 || (code >= 127 && code <= 159)) character = " "
    // Dynamic values can flow through shell components whose internal Text
    // format is not controlled by this plugin. Remove markup delimiters.
    if (character === "<" || character === ">" || character === "&") continue
    output += character
  }
  return output.replace(/\s+/g, " ").trim()
}

function boundedNumber(value, minimum, maximum) {
  if (value === null || value === undefined || value === "") return null
  var number = Number(value)
  return isFinite(number) && number >= minimum && number <= maximum ? number : null
}

function emptyState() {
  return {
    ok: false,
    version: "",
    backend: "missing",
    vendor: "",
    model: "Acer Nitro",
    biosVersion: "",
    isNitro: false,
    sensorAvailable: false,
    controlAvailable: false,
    hwmonName: "",
    controlProvider: "",
    temperatures: { cpu: null, gpu: null, system: null },
    fans: {
      cpu: { rpm: null, percent: null },
      gpu: { rpm: null, percent: null }
    },
    mode: "unavailable",
    modeCode: null,
    profile: "",
    profileChoices: [],
    error: ""
  }
}

function invalidState(previous, message) {
  var fallback = previous || emptyState()
  return Object.assign({}, fallback, {
    ok: false,
    error: plainText(message || "Invalid backend response", MAX_ERROR_CHARS)
  })
}

function parseStatus(raw, previous) {
  var source = String(raw || "")
  if (source.length > MAX_RESPONSE_CHARS)
    return invalidState(previous, "Backend response exceeded safety limit")

  var parsed
  try {
    parsed = JSON.parse(source)
  } catch (error) {
    return invalidState(previous, "Invalid backend response")
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    return invalidState(previous, "Invalid backend response")

  var state = emptyState()
  var temperatures = parsed.temperatures && typeof parsed.temperatures === "object"
    ? parsed.temperatures : {}
  var fans = parsed.fans && typeof parsed.fans === "object" ? parsed.fans : {}
  var cpuFan = fans.cpu && typeof fans.cpu === "object" ? fans.cpu : {}
  var gpuFan = fans.gpu && typeof fans.gpu === "object" ? fans.gpu : {}
  var allowedModes = ["automatic", "maximum", "manual", "mixed", "unavailable"]
  var mode = plainText(parsed.mode, 32)
  var backend = plainText(parsed.backend, 32)

  state.ok = parsed.ok === true
  state.version = plainText(parsed.version, 64)
  state.backend = backend === "ready" ? "ready" : "missing"
  state.vendor = plainText(parsed.vendor, MAX_TEXT_CHARS)
  state.model = plainText(parsed.model, MAX_TEXT_CHARS) || "Acer Nitro"
  state.biosVersion = plainText(parsed.biosVersion, 128)
  state.isNitro = parsed.isNitro === true
  state.sensorAvailable = parsed.sensorAvailable === true
  state.controlAvailable = parsed.controlAvailable === true
  state.hwmonName = plainText(parsed.hwmonName, 64)
  state.controlProvider = plainText(parsed.controlProvider, 64)
  state.temperatures = {
    cpu: boundedNumber(temperatures.cpu, -50, 150),
    gpu: boundedNumber(temperatures.gpu, -50, 150),
    system: boundedNumber(temperatures.system, -50, 150)
  }
  state.fans = {
    cpu: {
      rpm: boundedNumber(cpuFan.rpm, 0, 100000),
      percent: boundedNumber(cpuFan.percent, 0, 100)
    },
    gpu: {
      rpm: boundedNumber(gpuFan.rpm, 0, 100000),
      percent: boundedNumber(gpuFan.percent, 0, 100)
    }
  }
  state.mode = allowedModes.indexOf(mode) >= 0 ? mode : "unavailable"
  state.modeCode = boundedNumber(parsed.modeCode, 0, 2)
  state.profile = plainText(parsed.profile, 64)
  state.error = plainText(parsed.error, MAX_ERROR_CHARS)

  var choices = Array.isArray(parsed.profileChoices) ? parsed.profileChoices : []
  for (var index = 0; index < choices.length && state.profileChoices.length < MAX_PROFILE_CHOICES; index++) {
    var choice = plainText(choices[index], 64)
    if (choice && state.profileChoices.indexOf(choice) === -1) state.profileChoices.push(choice)
  }
  return state
}

function temperature(value) {
  var number = boundedNumber(value, -50, 150)
  return number === null ? "—" : Math.round(number) + "°"
}

function rpm(value) {
  var number = boundedNumber(value, 0, 100000)
  return number === null ? "—" : Math.round(number).toLocaleString() + " RPM"
}

function percent(value) {
  var number = boundedNumber(value, 0, 100)
  return number === null ? "—" : Math.round(number) + "%"
}

function modeTitle(mode) {
  if (mode === "automatic") return "Automatic"
  if (mode === "maximum") return "Maximum"
  if (mode === "manual") return "Manual"
  if (mode === "mixed") return "Mixed"
  return "Unavailable"
}

function statusLine(state) {
  if (!state.isNitro && state.vendor) return "Unsupported hardware"
  if (!state.sensorAvailable) return "Kernel support required"
  if (state.backend !== "ready") return "Read-only · setup required"
  return modeTitle(state.mode) + " · " + (plainText(state.profile, 64) || "no profile")
}

function barText(state, showTemperature) {
  var icon = state.mode === "maximum" ? "󰈸" : "󰈐"
  if (!state.sensorAvailable) return icon + " !"
  return showTemperature ? icon + " " + temperature(state.temperatures.cpu) : icon
}

function clampManual(value) {
  var number = Math.round(Number(value))
  if (!isFinite(number)) return 40
  return Math.max(20, Math.min(100, number))
}

function profileTitle(profile) {
  return plainText(profile, 64).split("-").map(function(part) {
    return part ? part.charAt(0).toUpperCase() + part.slice(1) : ""
  }).join(" ")
}

function profileIcon(profile) {
  if (profile === "low-power") return "󰌪"
  if (profile === "quiet") return "󰝟"
  if (profile === "performance") return "󰓅"
  if (profile === "balanced-performance") return "󰾅"
  return "󰊚"
}

function profileShort(profile) {
  if (profile === "low-power") return "Saver"
  if (profile === "balanced-performance") return "Balanced+"
  return profileTitle(profile)
}

if (typeof module !== "undefined") {
  module.exports = {
    MAX_RESPONSE_CHARS: MAX_RESPONSE_CHARS,
    emptyState: emptyState,
    parseStatus: parseStatus,
    plainText: plainText,
    temperature: temperature,
    rpm: rpm,
    percent: percent,
    modeTitle: modeTitle,
    statusLine: statusLine,
    barText: barText,
    clampManual: clampManual,
    profileTitle: profileTitle,
    profileIcon: profileIcon,
    profileShort: profileShort
  }
}

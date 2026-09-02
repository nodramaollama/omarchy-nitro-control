import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "NitroModel.js" as Model

Panel {
  id: root
  moduleName: "nitro.control"
  ipcTarget: "nitro.control"
  manageIpc: false

  property var state: Model.emptyState()
  property bool statusReady: false
  property string localError: ""
  property int cpuManual: 40
  property int gpuManual: 40
  property string page: "controls"
  readonly property int maxProcessOutputChars: 32768

  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string clientPath: pluginDir + "/bin/nitroctl"
  readonly property string installPath: pluginDir + "/install"
  readonly property color contentForeground: root.bar ? root.bar.foreground : Color.foreground
  readonly property string contentFontFamily: root.bar ? root.bar.fontFamily : Style.font.family
  readonly property bool backendReady: state.backend === "ready"
  readonly property bool canControl: backendReady && state.isNitro && state.controlAvailable
  readonly property bool busy: actionProc.running
  readonly property bool showTemperature: setting("showTemperature", true) !== false
  readonly property bool syncFans: setting("syncFans", true) !== false
  readonly property string barAlignment: String(setting("alignment", "right"))

  function refresh() {
    if (statusProc.running) return
    statusProc.output = ""
    statusProc.outputOverflow = false
    statusProc.timedOut = false
    statusProc.command = state.mode === "manual"
      ? [clientPath, "status", "--heartbeat"]
      : [clientPath, "status"]
    statusProc.running = true
  }

  function consumeStatus(raw) {
    var next = Model.parseStatus(raw, state)
    state = next
    statusReady = true
    if (next.ok) localError = ""
    else if (next.error) localError = next.error
    if (next.mode === "manual") {
      if (!cpuFanControl.dragging && next.fans.cpu.percent !== null)
        cpuManual = Model.clampManual(next.fans.cpu.percent)
      if (!gpuFanControl.dragging && next.fans.gpu.percent !== null)
        gpuManual = Model.clampManual(next.fans.gpu.percent)
    }
  }

  function runAction(arguments) {
    if (actionProc.running) return
    localError = ""
    actionProc.output = ""
    actionProc.errorOutput = ""
    actionProc.outputOverflow = false
    actionProc.timedOut = false
    actionProc.command = [clientPath].concat(arguments)
    actionProc.running = true
  }

  function setAutomatic() { runAction(["automatic"]) }
  function setMaximum() { runAction(["maximum"]) }
  function setManual() { runAction(["manual", "--cpu", String(cpuManual), "--gpu", String(gpuManual)]) }
  function setProfile(profile) { runAction(["profile", profile]) }

  function setCpuManual(value, apply) {
    cpuManual = Model.clampManual(value)
    if (syncFans) gpuManual = cpuManual
    if (apply) setManual()
  }

  function setGpuManual(value, apply) {
    gpuManual = Model.clampManual(value)
    if (syncFans) cpuManual = gpuManual
    if (apply) setManual()
  }

  function openSetup() {
    Quickshell.execDetached([
      "xdg-terminal-exec",
      "--hold",
      "--title=Nitro Control setup",
      "--",
      installPath
    ])
  }

  function persistSettings(values) {
    var entry = { id: root.moduleName }
    var current = root.settings || {}
    for (var key in current)
      if (key !== "id") entry[key] = current[key]
    for (var name in values) entry[name] = values[name]
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function toggleTemperature() {
    persistSettings({ showTemperature: !root.showTemperature })
  }

  function toggleSyncFans() {
    if (!root.syncFans) root.gpuManual = root.cpuManual
    persistSettings({ syncFans: !root.syncFans })
  }

  function setAlignment(section) {
    if (["left", "center", "right"].indexOf(section) === -1) return
    persistSettings({ alignment: section })
    root.close()
    Quickshell.execDetached(["omarchy", "bar", "move", root.moduleName, "--section", section])
  }

  onOpenedChanged: if (opened) {
    page = "controls"
    refresh()
  }
  Component.onCompleted: refresh()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.page = "controls"; root.open() }
    function close(): void { root.close() }
    function show(): void { root.page = "controls"; root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function controls(): void { root.page = "controls"; root.open() }
    function settings(): void {
      root.open()
      Qt.callLater(function() { root.page = "settings" })
    }
  }

  Process {
    id: statusProc
    property string output: ""
    property bool outputOverflow: false
    property bool timedOut: false
    command: []
    clearEnvironment: true
    environment: ({ "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8" })
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        statusProc.outputOverflow = text.length > root.maxProcessOutputChars
        statusProc.output = statusProc.outputOverflow ? "" : text
      }
    }
    onStarted: statusDeadline.restart()
    onExited: function() {
      statusDeadline.stop()
      statusKillDeadline.stop()
      if (timedOut) {
        root.statusReady = true
        root.localError = "Status request timed out"
      } else if (outputOverflow) {
        root.statusReady = true
        root.localError = "Status response exceeded safety limit"
      } else {
        root.consumeStatus(output)
      }
    }
  }

  Process {
    id: actionProc
    property string output: ""
    property string errorOutput: ""
    property bool outputOverflow: false
    property bool timedOut: false
    command: []
    clearEnvironment: true
    environment: ({ "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8" })
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        actionProc.outputOverflow = text.length > root.maxProcessOutputChars
        actionProc.output = actionProc.outputOverflow ? "" : text
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: actionProc.errorOutput = Model.plainText(text, 512)
    }
    onStarted: actionDeadline.restart()
    onExited: function(exitCode) {
      actionDeadline.stop()
      actionKillDeadline.stop()
      if (timedOut) {
        root.localError = "Control action timed out"
        root.refresh()
        return
      }
      if (outputOverflow) {
        root.localError = "Control response exceeded safety limit"
        root.refresh()
        return
      }
      var next = Model.parseStatus(output, root.state)
      if (exitCode === 0 && next.ok) {
        root.consumeStatus(output)
      } else {
        root.localError = next.error || Model.plainText(errorOutput, 512) || "Control action failed"
        root.refresh()
      }
    }
  }

  Timer {
    id: statusDeadline
    interval: 3000
    repeat: false
    onTriggered: if (statusProc.running) {
      statusProc.timedOut = true
      statusProc.signal(15)
      statusKillDeadline.restart()
    }
  }
  Timer {
    id: statusKillDeadline
    interval: 750
    repeat: false
    onTriggered: if (statusProc.running) statusProc.signal(9)
  }
  Timer {
    id: actionDeadline
    interval: 5000
    repeat: false
    onTriggered: if (actionProc.running) {
      actionProc.timedOut = true
      actionProc.signal(15)
      actionKillDeadline.restart()
    }
  }
  Timer {
    id: actionKillDeadline
    interval: 750
    repeat: false
    onTriggered: if (actionProc.running) actionProc.signal(9)
  }

  Timer {
    interval: 4000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Model.barText(root.state, root.showTemperature)
    slotSize: root.showTemperature && !vertical ? Style.bar.iconSlot * 1.8 : Style.bar.iconSlot
    tooltipText: statusReady ? "Nitro Control · " + Model.statusLine(root.state) : "Nitro Control"
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton && root.canControl) root.setAutomatic()
      else if (mouseButton === Qt.MiddleButton) root.toggleTemperature()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(content.implicitHeight, Style.space(720))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: content
          width: parent.width
          spacing: Style.space(14)

          PanelHero {
            width: parent.width
            title: root.page === "settings" ? "Nitro Settings" : "Nitro Control"
            meta: root.page === "settings"
              ? (root.state.model || "Acer Nitro")
              : (root.statusReady ? Model.statusLine(root.state) : "Detecting Acer hardware")
            detail: root.page === "controls" && root.statusReady
              ? Model.temperature(root.state.temperatures.cpu)
              : ""
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            iconComponent: Component {
              Text {
                text: root.state.mode === "maximum" ? "󰈸" : "󰈐"
                textFormat: Text.PlainText
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.display
              }
            }
            trailingControl: Component {
              PanelActionButton {
                iconText: root.page === "settings" ? "󰁍" : ""
                tooltipText: root.page === "settings" ? "Back to controls" : "Settings"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                focusable: true
                onClicked: root.page = root.page === "settings" ? "controls" : "settings"
              }
            }
          }

          Column {
            visible: root.page === "controls"
            width: parent.width
            spacing: Style.space(14)

            Row {
              width: parent.width
              spacing: Style.space(8)

              SensorCard {
                width: (parent.width - parent.spacing) / 2
                title: "CPU"
                temperatureText: Model.temperature(root.state.temperatures.cpu)
                fanText: Model.rpm(root.state.fans.cpu.rpm)
              }

              SensorCard {
                width: (parent.width - parent.spacing) / 2
                title: "GPU"
                temperatureText: Model.temperature(root.state.temperatures.gpu)
                fanText: Model.rpm(root.state.fans.gpu.rpm)
              }
            }

            Column {
              visible: !root.backendReady
              width: parent.width
              spacing: Style.space(8)

              PanelSeparator { foreground: root.contentForeground }
              PanelSectionHeader {
                text: "SETUP"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
              }
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: root.state.controlAvailable
                  ? "Sensors are working. Install the safety backend to unlock controls."
                  : "Install verified kernel support and the safety backend. Unknown models remain read-only."
                textFormat: Text.PlainText
                color: root.contentForeground
                opacity: 0.72
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
              }
              Button {
                width: parent.width
                text: "Install system support"
                iconText: "󰒓"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                bordered: true
                focusable: true
                onClicked: root.openSetup()
              }
            }

            Column {
              visible: root.backendReady
              width: parent.width
              spacing: Style.space(10)

              PanelSeparator { foreground: root.contentForeground }
              PanelSectionHeader {
                text: "FAN MODE"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
              }

              Row {
                width: parent.width
                spacing: Style.space(6)
                property real cellWidth: (width - spacing * 2) / 3

                Button {
                  width: parent.cellWidth
                  text: "Automatic"
                  iconText: "󰁨"
                  active: root.state.mode === "automatic"
                  enabled: root.canControl && !root.busy
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  bordered: true
                  onClicked: root.setAutomatic()
                }
                Button {
                  width: parent.cellWidth
                  text: "Maximum"
                  iconText: "󰈸"
                  active: root.state.mode === "maximum"
                  enabled: root.canControl && !root.busy
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  bordered: true
                  onClicked: root.setMaximum()
                }
                Button {
                  width: parent.cellWidth
                  text: "Manual"
                  iconText: "󰓾"
                  active: root.state.mode === "manual"
                  enabled: root.canControl && !root.busy
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  bordered: true
                  onClicked: root.setManual()
                }
              }

              Column {
                visible: root.state.mode === "manual"
                width: parent.width
                spacing: Style.space(8)

                FanSlider {
                  id: cpuFanControl
                  label: root.syncFans ? "CPU & GPU" : "CPU"
                  value: root.cpuManual
                  onMoved: function(value) { root.setCpuManual(value, false) }
                  onReleased: function(value) { root.setCpuManual(value, true) }
                }

                FanSlider {
                  id: gpuFanControl
                  visible: !root.syncFans
                  label: "GPU"
                  value: root.gpuManual
                  onMoved: function(value) { root.setGpuManual(value, false) }
                  onReleased: function(value) { root.setGpuManual(value, true) }
                }

                Text {
                  width: parent.width
                  text: "Manual control returns to Automatic if this plugin stops responding."
                  textFormat: Text.PlainText
                  wrapMode: Text.WordWrap
                  color: root.contentForeground
                  opacity: 0.58
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                }
              }

              Column {
                visible: root.state.profileChoices.length > 0
                width: parent.width
                spacing: Style.space(8)

                PanelSeparator { foreground: root.contentForeground }
                PanelSectionHeader {
                  text: "PERFORMANCE PROFILE"
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                }
                Column {
                  id: profileRows
                  width: parent.width
                  spacing: Style.space(4)
                  property real cellWidth: (width - Style.space(8)) / 3

                  Row {
                    property int itemCount: Math.min(3, root.state.profileChoices.length)
                    width: profileRows.cellWidth * itemCount + spacing * Math.max(0, itemCount - 1)
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Style.space(4)
                    Repeater {
                      model: root.state.profileChoices.slice(0, 3)
                      ProfileButton {
                        required property var modelData
                        width: profileRows.cellWidth
                        profile: String(modelData)
                      }
                    }
                  }

                  Row {
                    visible: root.state.profileChoices.length > 3
                    property int itemCount: Math.max(0, root.state.profileChoices.length - 3)
                    width: profileRows.cellWidth * itemCount + spacing * Math.max(0, itemCount - 1)
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Style.space(4)
                    Repeater {
                      model: root.state.profileChoices.slice(3)
                      ProfileButton {
                        required property var modelData
                        width: profileRows.cellWidth
                        profile: String(modelData)
                      }
                    }
                  }
                }
              }
            }

            Text {
              visible: root.localError !== ""
              width: parent.width
              text: root.localError
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: root.bar ? root.bar.urgent : Color.urgent
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }

          Column {
            visible: root.page === "settings"
            width: parent.width
            spacing: Style.space(10)

            PanelSectionHeader {
              text: "BAR DISPLAY"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Toggle {
              width: parent.width
              label: "Show CPU temperature"
              description: "Keep the live temperature next to the fan icon."
              checked: root.showTemperature
              foreground: root.contentForeground
              accent: root.bar ? root.bar.urgent : Color.accent
              fontFamily: root.contentFontFamily
              onClicked: root.toggleTemperature()
            }

            PanelSectionHeader {
              text: "BAR POSITION"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Row {
              id: alignmentRow
              width: parent.width
              spacing: Style.space(6)
              Repeater {
                model: ["left", "center", "right"]
                Button {
                  required property string modelData
                  width: (alignmentRow.width - alignmentRow.spacing * 2) / 3
                  text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                  active: root.barAlignment === modelData
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  bordered: true
                  onClicked: root.setAlignment(modelData)
                }
              }
            }

            PanelSeparator { foreground: root.contentForeground }
            PanelSectionHeader {
              text: "MANUAL CONTROL"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Toggle {
              width: parent.width
              label: "Link CPU and GPU fans"
              description: "Use one slider and send the same speed to both fans."
              checked: root.syncFans
              foreground: root.contentForeground
              accent: root.bar ? root.bar.urgent : Color.accent
              fontFamily: root.contentFontFamily
              onClicked: root.toggleSyncFans()
            }

            Text {
              width: parent.width
              text: "The 20% safety floor and 12-second Automatic fallback are enforced by the system service and cannot be disabled here."
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: root.contentForeground
              opacity: 0.58
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
            }

            Button {
              text: "Back to controls"
              iconText: "󰁍"
              bordered: true
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
              onClicked: root.page = "controls"
            }
          }
        }
      }
    }
  }

  component SensorCard: BorderSurface {
    property string title: ""
    property string temperatureText: "—"
    property string fanText: "—"

    implicitHeight: sensorColumn.implicitHeight + Style.space(20)
    color: Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.06)
    borderSpec: Border.controlSpec("normal", root.contentForeground, Color.accent)
    radius: Style.cornerRadius

    Column {
      id: sensorColumn
      anchors.centerIn: parent
      spacing: Style.space(2)
      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: title
        textFormat: Text.PlainText
        color: Qt.darker(root.contentForeground, 1.4)
        font.family: root.contentFontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        font.letterSpacing: 1
      }
      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: temperatureText
        textFormat: Text.PlainText
        color: root.contentForeground
        font.family: root.contentFontFamily
        font.pixelSize: Style.font.title
        font.bold: true
      }
      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: fanText
        textFormat: Text.PlainText
        color: root.contentForeground
        opacity: 0.65
        font.family: root.contentFontFamily
        font.pixelSize: Style.font.bodySmall
      }
    }
  }

  component FanSlider: Column {
    required property string label
    required property int value
    property alias dragging: controlSlider.dragging
    signal moved(real value)
    signal released(real value)
    width: parent ? parent.width : implicitWidth
    spacing: Style.space(4)

    Row {
      width: parent.width
      Text {
        text: label
        textFormat: Text.PlainText
        color: root.contentForeground
        font.family: root.contentFontFamily
        font.pixelSize: Style.font.bodySmall
      }
      Item {
        width: Math.max(0, parent.width - parent.children[0].implicitWidth - parent.children[2].implicitWidth)
        height: 1
      }
      Text {
        text: value + "%"
        textFormat: Text.PlainText
        color: root.contentForeground
        font.family: root.contentFontFamily
        font.pixelSize: Style.font.bodySmall
        font.bold: true
      }
    }

    PanelSlider {
      id: controlSlider
      width: parent.width
      bar: root.bar
      minimum: 20
      maximum: 100
      step: 5
      integer: true
      tickCount: 9
      value: parent.value
      onMoved: function(next) { parent.moved(next) }
      onReleased: function(next) { parent.released(next) }
    }
  }

  component ProfileButton: Button {
    required property string profile
    text: Model.profileShort(profile)
    iconText: Model.profileIcon(profile)
    fontSize: Style.font.caption
    iconSize: Style.font.body
    active: root.state.profile === profile
    enabled: !root.busy
    foreground: root.contentForeground
    fontFamily: root.contentFontFamily
    horizontalPadding: Style.space(4)
    bordered: true
    tooltipText: Model.profileTitle(profile)
    onClicked: root.setProfile(profile)
  }
}

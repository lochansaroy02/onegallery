// One Gallery Memories: a Plasma widget showing pictures from One Gallery's library.
// It reads the feed One Gallery writes (backend/widget.py) and runs `onegallery --widget-feed`
// when that feed is missing or from an earlier day.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    // ~/.local/bin: where packaging/install-user.sh puts the launcher of a source checkout
    readonly property string app: 'PATH="$PATH:$HOME/.local/bin" onegallery'
    readonly property string feedFile: '"${XDG_CACHE_HOME:-$HOME/.cache}/onegallery/widget/feed.json"'
    readonly property int rebuildPause: 20 * 60 * 1000   // after a failed or recent rebuild

    property var feed: null
    property string feedText: ""
    property bool building: false
    property double lastBuild: 0
    property bool appMissing: false
    property int index: 0

    readonly property bool folderMode: Plasmoid.configuration.source === "folder"
    readonly property var folders: Plasmoid.configuration.folders || []
    // the folders the last forced rebuild asked for, so a missing folder is asked for once
    property string requestedFolders: ""

    readonly property var items: {
        if (!feed)
            return []
        if (folderMode)
            return interleave(folders.map(folder => (feed.folders || {})[folder] || []))
        const lists = feed.lists
        const order = {
            memories: ["memories", "favorites", "recent"],
            favorites: ["favorites", "recent"],
            recent: ["recent"],
        }[Plasmoid.configuration.source] || ["memories", "favorites", "recent"]
        for (const name of order) {
            if (lists[name] && lists[name].length)
                return lists[name]
        }
        return []
    }
    readonly property var current: items.length ? items[Math.min(index, items.length - 1)] : null
    readonly property bool foldersMissing: folderMode && folders.some(
        folder => !feed || !feed.folders || !(folder in feed.folders))

    onFoldersChanged: reload()
    onFolderModeChanged: reload()

    Plasmoid.backgroundHints: PlasmaCore.Types.DefaultBackground | PlasmaCore.Types.ConfigurableBackground
    toolTipMainText: current ? current.title : i18n("One Gallery Memories")
    toolTipSubText: current ? current.subtitle : ""
    switchWidth: Kirigami.Units.gridUnit * 8
    switchHeight: Kirigami.Units.gridUnit * 6

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Open One Gallery")
            icon.name: "onegallery"
            onTriggered: root.run(root.app)
        },
        PlasmaCore.Action {
            text: i18n("Refresh Pictures")
            icon.name: "view-refresh"
            onTriggered: root.rebuild(true)
        }
    ]

    // ---- shell commands -------------------------------------------------------------------
    P5Support.DataSource {
        id: shell
        engine: "executable"
        connectedSources: []
        property var callbacks: ({})
        property int serial: 0
        onNewData: (source, data) => {
            disconnectSource(source)
            const done = callbacks[source]
            delete callbacks[source]
            if (done)
                done(data["exit code"], data["stdout"] || "")
        }
    }

    function run(command, done) {
        // a unique trailing comment lets the same command run twice at once
        const source = command + " # " + (++shell.serial)
        shell.callbacks[source] = done || null
        shell.connectSource(source)
    }

    function quote(text) {
        return "'" + String(text).replace(/'/g, "'\\''") + "'"
    }

    // a picture from each folder in turn
    function interleave(lists) {
        const out = []
        const longest = Math.max(0, ...lists.map(list => list.length))
        for (let i = 0; i < longest; i++) {
            for (const list of lists) {
                if (i < list.length)
                    out.push(list[i])
            }
        }
        return out
    }

    function today() {
        return Qt.formatDate(new Date(), "yyyy-MM-dd")
    }

    // ---- feed -----------------------------------------------------------------------------
    function reload() {
        run("cat " + feedFile, (code, out) => {
            if (code === 0 && out !== feedText) {
                try {
                    const parsed = JSON.parse(out)
                    if (parsed.version === 1 && parsed.lists) {
                        const path = current ? current.path : ""
                        feedText = out
                        feed = parsed
                        const at = items.findIndex(item => item.path === path)
                        index = Math.max(0, at)
                    }
                } catch (e) {
                    console.warn("One Gallery Memories: unreadable feed:", e)
                }
            }
            if (foldersMissing && requestedFolders !== folders.join("\n"))
                rebuild(true)
            else if (!feed || feed.day !== today())
                rebuild(false)
        })
    }

    function rebuild(force) {
        if (building || (!force && Date.now() - lastBuild < rebuildPause))
            return
        building = true
        lastBuild = Date.now()
        let command = app + " --widget-feed"
        if (folderMode) {
            requestedFolders = folders.join("\n")
            command += folders.map(folder => " --folder " + quote(folder)).join("")
        }
        run(command, code => {
            building = false
            appMissing = code === 127
            if (code === 0)
                reload()
        })
    }

    function step(by) {
        if (items.length)
            index = (index + by + items.length) % items.length
    }

    function open(item) {
        run(app + " " + quote(item.path), code => {
            if (code === 127)   // One Gallery isn't installed: use the default viewer
                Qt.openUrlExternally("file://" + item.path.split("/").map(encodeURIComponent).join("/"))
        })
        root.expanded = false
    }

    Component.onCompleted: reload()

    Timer {   // picks up feeds written by the running app, and the next day
        interval: 2 * 60 * 1000
        running: true
        repeat: true
        onTriggered: root.reload()
    }

    Timer {
        id: slideshow
        interval: Math.max(3, Plasmoid.configuration.interval) * 1000
        running: root.items.length > 1 && !root.hovering
        repeat: true
        onTriggered: root.step(1)
    }
    property bool hovering: false

    // ---- representations ------------------------------------------------------------------
    compactRepresentation: MouseArea {
        Layout.minimumWidth: Kirigami.Units.iconSizes.small
        Layout.minimumHeight: Kirigami.Units.iconSizes.small
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        MemoryFrame {
            anchors.fill: parent
            anchors.margins: Math.round(Math.min(parent.width, parent.height) * 0.08)
            visible: root.current !== null
            items: root.items
            index: root.index
            interactive: false
            showCaption: false
            slowZoom: false
            radius: Kirigami.Units.cornerRadius
        }
        Kirigami.Icon {
            anchors.fill: parent
            visible: root.current === null
            source: "onegallery"
            fallback: "folder-pictures"
        }
    }

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 22
        Layout.preferredHeight: Kirigami.Units.gridUnit * 16
        Layout.minimumWidth: Kirigami.Units.gridUnit * 8
        Layout.minimumHeight: Kirigami.Units.gridUnit * 6

        Loader {
            anchors.fill: parent
            visible: root.current !== null
            sourceComponent: Plasmoid.configuration.transition === "mosaic" ? mosaicView : frameView
        }

        Component {
            id: frameView
            MemoryFrame {
                items: root.items
                index: root.index
                transition: Plasmoid.configuration.transition === "slide" ? "slide" : "fade"
                crop: Plasmoid.configuration.crop
                showCaption: Plasmoid.configuration.showCaption
                slowZoom: Plasmoid.configuration.slowZoom
                interval: slideshow.interval
                radius: Kirigami.Units.cornerRadius * 3
                fontPixelSize: Math.max(11, Math.min(16, Math.min(width, height) / 22))
                onActivated: item => root.open(item)
                onNext: root.step(1)
                onPrevious: root.step(-1)
                onHoveredChanged: root.hovering = hovered
            }
        }

        Component {
            id: mosaicView
            TileMosaic {
                items: root.items
                index: root.index
                showCaption: Plasmoid.configuration.showCaption
                radius: Kirigami.Units.cornerRadius * 3
                fontPixelSize: Math.max(11, Math.min(16, Math.min(width, height) / 22))
                onActivated: item => root.open(item)
                onNext: root.step(1)
                onPrevious: root.step(-1)
                onHoveredChanged: root.hovering = hovered
            }
        }

        QQC2.BusyIndicator {
            anchors.centerIn: parent
            visible: root.current === null && root.building
            running: visible
        }

        PlasmaExtras.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 2
            visible: root.current === null && !root.building
            iconName: root.appMissing ? "dialog-warning" : "folder-pictures"
            readonly property bool chooseFolder: root.folderMode && !root.folders.length
            text: root.appMissing ? i18n("One Gallery is not installed")
                  : chooseFolder ? i18n("No folder chosen")
                  : !root.feed ? i18n("Loading your pictures…")
                  : root.folderMode ? i18n("No pictures in these folders")
                  : i18n("No pictures yet")
            explanation: root.appMissing
                ? i18n("This widget shows pictures from One Gallery's library. Install One Gallery, then refresh the widget.")
                : root.folderMode
                ? i18n("Choose the folders whose pictures this widget shows in its settings.")
                : i18n("Add your photo folders in One Gallery, and your memories, favorites and latest pictures appear here.")
            helpfulAction: QQC2.Action {
                icon.name: root.appMissing ? "view-refresh" : root.folderMode ? "configure" : "onegallery"
                text: root.appMissing ? i18n("Refresh")
                      : root.folderMode ? i18n("Choose Folders…") : i18n("Open One Gallery")
                onTriggered: root.appMissing ? root.rebuild(true)
                             : root.folderMode ? Plasmoid.internalAction("configure").trigger()
                             : root.run(root.app)
            }
        }
    }
}

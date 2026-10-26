import QtQuick
import QtQuick.Controls
import ".."

// Pick the sub-folders of a watched folder that Gallery should skip.
// Unticked = excluded (with everything inside). Applied with gallery.setExcludes().
Popup {
    id: dlg
    property string root: ""
    property string current: ""
    property var excludes: []          // working copy, applied on "Apply"
    property var original: []
    property var entries: []
    property bool loading: false

    function openFor(rootPath, existing) {
        root = rootPath
        original = existing.slice()
        excludes = existing.slice()
        go(rootPath)
        open()
    }
    function go(path) {
        current = path
        loading = true
        entries = []
        gallery.requestSubfolders(path, root)
    }
    function within(path, folder) { return path === folder || path.startsWith(folder + "/") }
    function excludedBy(path) {
        for (var i = 0; i < excludes.length; ++i)
            if (within(path, excludes[i])) return excludes[i]
        return ""
    }
    function toggle(path) {
        var by = excludedBy(path)
        if (by === path) {
            excludes = excludes.filter(e => e !== path)            // include again
        } else if (by === "") {
            excludes = excludes.filter(e => !within(e, path)).concat([path])
        }
    }
    function relative(path) { return path === root ? "" : path.slice(root.length + 1) }
    function crumbs() {
        var parts = [{ name: root.replace(/^.*\//, "") || root, path: root }]
        var rel = relative(current)
        if (rel === "") return parts
        var acc = root
        rel.split("/").forEach(function(p) { acc += "/" + p; parts.push({ name: p, path: acc }) })
        return parts
    }
    readonly property bool changed: JSON.stringify(excludes.slice().sort()) !== JSON.stringify(original.slice().sort())

    Connections {
        target: gallery
        function onSubfoldersLoaded(folder, items) {
            if (folder === dlg.current) { dlg.entries = items; dlg.loading = false }
        }
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(620, parent ? parent.width - 48 : 620)
    height: Math.min(640, parent ? parent.height - 48 : 640)
    modal: true
    focus: true
    padding: Theme.s5
    Overlay.modal: Rectangle { color: Theme.scrim }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durNormal }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.durNormal; easing.type: Theme.easing }
    }
    background: Rectangle { radius: Theme.radiusL; color: Theme.surface }

    contentItem: Item {
        Column {
            id: head
            width: parent.width
            spacing: Theme.s2
            Text {
                text: qsTr("Exclude sub-folders")
                color: Theme.text
                font.pixelSize: Theme.fontTitle
                font.weight: Font.Bold
            }
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: qsTr("Untick the folders One Gallery should skip, including everything inside them. Their pictures leave the gallery; the files stay on disk.")
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall + 1
            }
            // path trail: click to go back up
            Flow {
                width: parent.width
                spacing: 2
                topPadding: Theme.s2
                Repeater {
                    model: dlg.crumbs()
                    delegate: Row {
                        required property var modelData
                        required property int index
                        spacing: 2
                        Icon {
                            visible: index > 0
                            name: "chevronRight"
                            size: 14
                            color: Theme.textSecondary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Rectangle {
                            width: crumbText.implicitWidth + 16
                            height: 28
                            radius: 14
                            color: crumbMouse.containsMouse ? Theme.hover : "transparent"
                            Text {
                                id: crumbText
                                anchors.centerIn: parent
                                text: modelData.name
                                color: modelData.path === dlg.current ? Theme.text : Theme.accent
                                font.pixelSize: Theme.fontSmall + 1
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                id: crumbMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (modelData.path !== dlg.current) dlg.go(modelData.path)
                            }
                        }
                    }
                }
            }
        }

        ListView {
            id: list
            anchors.top: head.bottom
            anchors.topMargin: Theme.s2
            anchors.bottom: summary.top
            anchors.bottomMargin: Theme.s2
            width: parent.width
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: dlg.entries
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var modelData
                readonly property string by: dlg.excludedBy(modelData.path)
                readonly property bool excluded: by !== ""
                readonly property bool inherited: excluded && by !== modelData.path
                width: list.width
                height: 54
                radius: Theme.radiusS
                color: rowMouse.containsMouse ? Theme.hover : "transparent"

                Rectangle {
                    id: box
                    x: Theme.s3
                    anchors.verticalCenter: parent.verticalCenter
                    width: 22
                    height: 22
                    radius: 6
                    color: parent.excluded ? "transparent" : Theme.accent
                    border.width: parent.excluded ? 2 : 0
                    border.color: Theme.textSecondary
                    opacity: parent.inherited ? 0.4 : 1
                    Icon { anchors.centerIn: parent; visible: !parent.parent.excluded; name: "check"; size: 15; strokeWidth: 3; color: Theme.accentText }
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -10
                        enabled: !parent.parent.inherited
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dlg.toggle(modelData.path)
                    }
                }
                Icon {
                    id: folderIcon
                    anchors.left: box.right
                    anchors.leftMargin: Theme.s3
                    anchors.verticalCenter: parent.verticalCenter
                    name: parent.excluded ? "folderMinus" : "folder"
                    size: 22
                    color: parent.excluded ? Theme.textSecondary : Theme.accent
                }
                Column {
                    anchors.left: folderIcon.right
                    anchors.leftMargin: Theme.s3
                    anchors.right: chevron.left
                    anchors.rightMargin: Theme.s2
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        width: parent.width
                        text: modelData.name
                        elide: Text.ElideMiddle
                        color: parent.parent.excluded ? Theme.textSecondary : Theme.text
                        font.pixelSize: Theme.fontBody
                        font.strikeout: parent.parent.excluded && !parent.parent.inherited
                    }
                    Text {
                        text: parent.parent.inherited ? qsTr("Excluded with %1").arg(parent.parent.by.replace(/^.*\//, ""))
                            : parent.parent.excluded ? qsTr("Excluded")
                            : modelData.count === 0 ? qsTr("No pictures in the gallery")
                            : modelData.count === 1 ? qsTr("1 picture") : qsTr("%1 pictures").arg(modelData.count.toLocaleString(Qt.locale(), "f", 0))
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSmall
                    }
                }
                Icon {
                    id: chevron
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.s3
                    anchors.verticalCenter: parent.verticalCenter
                    visible: modelData.hasChildren
                    name: "chevronRight"
                    size: 18
                    color: Theme.textSecondary
                }
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    anchors.leftMargin: box.x + box.width + 10
                    hoverEnabled: true
                    cursorShape: modelData.hasChildren ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: modelData.hasChildren ? dlg.go(modelData.path) : (parent.inherited ? null : dlg.toggle(modelData.path))
                }
            }
            Text {
                anchors.centerIn: parent
                visible: !dlg.loading && dlg.entries.length === 0
                text: qsTr("No sub-folders here")
                color: Theme.textSecondary
                font.pixelSize: Theme.fontBody
            }
            BusyIndicator { anchors.centerIn: parent; running: dlg.loading; visible: running }
        }

        Column {
            id: summary
            anchors.bottom: buttons.top
            anchors.bottomMargin: Theme.s3
            width: parent.width
            spacing: Theme.s2
            visible: dlg.excludes.length > 0
            Text {
                text: dlg.excludes.length === 1 ? qsTr("1 folder excluded") : qsTr("%1 folders excluded").arg(dlg.excludes.length)
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall
                font.weight: Font.DemiBold
            }
            Flow {
                width: parent.width
                spacing: Theme.s2
                Repeater {
                    model: dlg.excludes
                    delegate: Rectangle {
                        required property string modelData
                        width: chipRow.implicitWidth + 20
                        height: 30
                        radius: 15
                        color: Theme.surfaceHigh
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 4
                            Text {
                                text: dlg.relative(modelData)
                                color: Theme.text
                                font.pixelSize: Theme.fontSmall
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Icon {
                                name: "close"
                                size: 14
                                color: Theme.textSecondary
                                anchors.verticalCenter: parent.verticalCenter
                                MouseArea {
                                    anchors.fill: parent
                                    anchors.margins: -6
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: dlg.toggle(modelData)
                                }
                            }
                        }
                    }
                }
            }
        }

        Row {
            id: buttons
            anchors.bottom: parent.bottom
            anchors.right: parent.right
            spacing: Theme.s2
            PillButton { kind: "text"; text: qsTr("Cancel"); onClicked: dlg.close() }
            PillButton {
                text: qsTr("Apply")
                enabled: dlg.changed
                onClicked: { gallery.setExcludes(dlg.root, dlg.excludes); dlg.close() }
            }
        }
    }
}

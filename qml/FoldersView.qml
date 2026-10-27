import QtQuick
import QtQuick.Controls
import "."
import "components"

// Folders tab: watched folders with Add / Remove / Rescan.
Item {
    id: view
    property real bottomInset: 0
    signal settingsRequested()
    readonly property var win: ApplicationWindow.window
    readonly property real headerHeight: Math.max(150, Math.min(250, height * 0.3))
    readonly property real collapse: Math.max(0, Math.min(1, (list.contentY - list.originY) / (headerHeight * 0.7)))

    function totalCount() {
        var n = 0
        for (var i = 0; i < gallery.folders.length; ++i) n += Math.max(0, gallery.folders[i].count)
        return n
    }

    CollapsingHeader {
        id: bar
        z: 2
        width: parent.width
        title: qsTr("Folders")
        progress: view.collapse
        IconButton {
            icon: "refresh"
            tip: qsTr("Rescan all folders (F5)")
            enabled: !gallery.scanning && gallery.hasFolders
            onClicked: gallery.rescan()
        }
        IconButton { id: menuButton; icon: "more"; tip: qsTr("Menu"); onClicked: ApplicationWindow.window.openAppMenu(menuButton) }
    }

    ListView {
        id: list
        anchors.top: bar.bottom
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        spacing: Theme.s3
        model: gallery.folders

        header: Column {
            width: list.width
            spacing: Theme.s3
            BigTitle {
                width: parent.width
                height: view.headerHeight
                title: qsTr("Folders")
                busy: gallery.scanning
                progress: view.collapse
                subtitle: gallery.scanning
                    ? qsTr("Scanning… %1 found").arg(gallery.scanFound.toLocaleString(Qt.locale(), "f", 0))
                    : (gallery.folders.length === 1 ? qsTr("1 folder") : qsTr("%1 folders").arg(gallery.folders.length))
                      + " · " + qsTr("%1 pictures")
                          .arg(view.totalCount().toLocaleString(Qt.locale(), "f", 0))
            }
            Row {
                x: Theme.pageMargin
                spacing: Theme.s2
                PillButton {
                    text: qsTr("Add folder")
                    icon: "folderPlus"
                    onClicked: view.win.addFolder()
                }
                PillButton {
                    kind: "tonal"
                    text: gallery.scanning ? qsTr("Scanning…") : qsTr("Rescan")
                    icon: "refresh"
                    enabled: !gallery.scanning && gallery.hasFolders
                    onClicked: gallery.rescan()
                }
            }
            Text {
                x: Theme.pageMargin
                width: parent.width - 2 * Theme.pageMargin
                visible: gallery.scanning && gallery.scanDir !== ""
                text: gallery.scanDir
                elide: Text.ElideMiddle
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall
            }
            Rectangle {
                x: Theme.pageMargin
                width: parent.width - 2 * Theme.pageMargin
                height: visible ? 76 : 0
                visible: gallery.suggestedFolder !== ""
                radius: Theme.radiusL
                color: Theme.accentSoft
                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.s5
                    anchors.right: addSuggested.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        text: qsTr("Add your Pictures folder?")
                        color: Theme.text
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.DemiBold
                    }
                    Text {
                        width: parent.width
                        text: gallery.suggestedFolder
                        elide: Text.ElideMiddle
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSmall
                    }
                }
                PillButton {
                    id: addSuggested
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.s4
                    anchors.verticalCenter: parent.verticalCenter
                    compact: true
                    text: qsTr("Add")
                    onClicked: gallery.addFolder(gallery.suggestedFolder)
                }
            }
            // phones paired with KDE Connect (set up, or connected now)
            Column {
                id: phoneList
                readonly property var shown: phones.available
                    ? phones.devices.filter(function(p) { return p.setUp || p.reachable || p.busy }) : []
                x: Theme.pageMargin
                width: parent.width - 2 * Theme.pageMargin
                visible: shown.length > 0
                spacing: Theme.s2
                Text {
                    leftPadding: Theme.s4
                    text: qsTr("Phones")
                    color: Theme.accent
                    font.pixelSize: Theme.fontSmall + 1
                    font.weight: Font.DemiBold
                }
                Repeater {
                    model: phoneList.shown
                    PhoneCard {
                        required property var modelData
                        width: phoneList.width
                        phone: modelData
                    }
                }
                Text {
                    leftPadding: Theme.s4
                    topPadding: Theme.s2
                    text: qsTr("Folders")
                    color: Theme.accent
                    font.pixelSize: Theme.fontSmall + 1
                    font.weight: Font.DemiBold
                    visible: gallery.hasFolders
                }
            }
            Item { width: 1; height: Theme.s1 }
        }

        delegate: Item {
          required property var modelData
          width: list.width
          height: modelData.excludes.length > 0 ? 96 : 80
          Rectangle {
            x: Theme.pageMargin
            width: parent.width - 2 * Theme.pageMargin
            height: parent.height
            radius: Theme.radiusL
            color: Theme.surface

            Rectangle {
                id: badge
                anchors.left: parent.left
                anchors.leftMargin: Theme.s4
                anchors.verticalCenter: parent.verticalCenter
                width: 46
                height: 46
                radius: 23
                color: modelData.available ? Theme.accentSoft : Qt.rgba(1, 0.3, 0.3, 0.14)
                Icon {
                    anchors.centerIn: parent
                    name: modelData.mount !== "/" && modelData.mount !== "" && modelData.path.indexOf("/home") !== 0
                          ? "drive" : "folder"
                    color: modelData.available ? Theme.accent : Theme.danger
                    size: 22
                }
            }
            Column {
                anchors.left: badge.right
                anchors.leftMargin: Theme.s3
                anchors.right: excludeBtn.left
                anchors.rightMargin: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text {
                    width: parent.width
                    text: modelData.name
                    elide: Text.ElideRight
                    color: Theme.text
                    font.pixelSize: Theme.fontBody + 1
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: modelData.path
                    elide: Text.ElideMiddle
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSmall
                }
                Text {
                    visible: modelData.excludes.length > 0
                    text: modelData.excludes.length === 1 ? qsTr("1 sub-folder excluded") : qsTr("%1 sub-folders excluded").arg(modelData.excludes.length)
                    color: Theme.accent
                    font.pixelSize: Theme.fontSmall
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: view.win.editExcludes(modelData.path, modelData.excludes)
                    }
                }
                Text {
                    text: !modelData.available ? qsTr("Not available · drive not mounted. Items are kept.")
                        : modelData.count < 0 ? "…"
                        : qsTr("%1 pictures").arg(modelData.count.toLocaleString(Qt.locale(), "f", 0))
                    color: modelData.available ? Theme.textSecondary : Theme.danger
                    font.pixelSize: Theme.fontSmall
                }
            }
            IconButton {
                id: excludeBtn
                anchors.right: removeBtn.left
                anchors.verticalCenter: parent.verticalCenter
                visible: modelData.available
                icon: "folderMinus"
                color: Theme.textSecondary
                tip: qsTr("Exclude sub-folders…")
                onClicked: view.win.editExcludes(modelData.path, modelData.excludes)
            }
            IconButton {
                id: removeBtn
                anchors.right: parent.right
                anchors.rightMargin: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                icon: "close"
                color: Theme.textSecondary
                tip: qsTr("Remove from gallery")
                onClicked: view.win.confirm(
                    qsTr("Remove “%1” from the gallery?").arg(modelData.name),
                    qsTr("Its pictures disappear from the gallery. Files on disk are not deleted."),
                    qsTr("Remove"),
                    function() { gallery.removeFolder(modelData.path) })
            }
          }
        }

        footer: Item {
            width: list.width
            height: hint.implicitHeight + view.bottomInset + Theme.s6
            Text {
                id: hint
                x: Theme.pageMargin + 4
                y: Theme.s4
                width: parent.width - 2 * Theme.pageMargin - 8
                wrapMode: Text.Wrap
                visible: gallery.hasFolders
                text: qsTr("Sub-folders are included automatically. Hidden folders, node_modules, caches and trash folders are skipped. Removing a folder never deletes files.")
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall
            }
        }
    }
}

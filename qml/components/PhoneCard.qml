import QtQuick
import QtQuick.Controls
import ".."

// A phone paired with KDE Connect (Folders tab): set it up, sync now, automatic sync.
Rectangle {
    id: card
    required property var phone
    implicitHeight: col.implicitHeight + 2 * Theme.s4
    radius: Theme.radiusL
    color: phone.setUp ? Theme.surface : Theme.accentSoft

    function ago(seconds) {
        if (!seconds) return ""
        var mins = Math.floor((Date.now() / 1000 - seconds) / 60)
        if (mins < 1) return qsTr("synced just now")
        if (mins < 60) return qsTr("synced %1 min ago").arg(mins)
        if (mins < 24 * 60) return qsTr("synced %1 h ago").arg(Math.floor(mins / 60))
        if (mins < 48 * 60) return qsTr("synced yesterday")
        return qsTr("synced %1").arg(new Date(seconds * 1000).toLocaleDateString(Qt.locale(), Locale.ShortFormat))
    }

    readonly property string status: {
        if (phone.busy)
            return phone.total > 0 ? qsTr("Importing %1 of %2…").arg(phone.done + 1 > phone.total ? phone.total : phone.done + 1).arg(phone.total)
                                   : qsTr("Looking for new photos…")
        if (!phone.setUp)
            return phone.browsable ? qsTr("Import its photos and videos over Wi-Fi. They go to %1.").arg(phone.folderLabel)
                                   : qsTr("To import its photos, turn on “Remote filesystem browser” for it in KDE Connect, and “Filesystem expose” on the phone.")
        var parts = [phone.reachable ? qsTr("Connected") : qsTr("Not connected")]
        if (phone.lastSync) parts.push(ago(phone.lastSync))
        if (phone.count > 0) parts.push(qsTr("%1 items").arg(phone.count.toLocaleString(Qt.locale(), "f", 0)))
        return parts.join(" · ")
    }

    Column {
        id: col
        x: Theme.s4
        y: Theme.s4
        width: parent.width - 2 * Theme.s4
        spacing: Theme.s3

        Item {
            width: parent.width
            height: Math.max(46, texts.implicitHeight)
            Rectangle {
                id: badge
                width: 46
                height: 46
                radius: 23
                anchors.verticalCenter: parent.verticalCenter
                color: card.phone.setUp ? Theme.accentSoft : Theme.surface
                Icon {
                    anchors.centerIn: parent
                    name: "phone"
                    size: 22
                    color: card.phone.reachable ? Theme.accent : Theme.textSecondary
                }
            }
            Column {
                id: texts
                anchors.left: badge.right
                anchors.leftMargin: Theme.s3
                anchors.right: buttons.left
                anchors.rightMargin: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text {
                    width: parent.width
                    text: card.phone.setUp ? card.phone.name : qsTr("%1 is connected").arg(card.phone.name)
                    elide: Text.ElideRight
                    color: Theme.text
                    font.pixelSize: Theme.fontBody + 1
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: card.status
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSmall
                }
            }
            Row {
                id: buttons
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: card.phone.setUp || card.phone.busy
                spacing: Theme.s1
                PillButton {
                    anchors.verticalCenter: parent.verticalCenter
                    compact: true
                    kind: "tonal"
                    visible: card.phone.busy || card.phone.reachable
                    text: card.phone.busy ? qsTr("Stop") : qsTr("Sync now")
                    icon: card.phone.busy ? "" : "refresh"
                    onClicked: card.phone.busy ? phones.stop() : phones.syncNow(card.phone.id)
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: card.phone.setUp
                    icon: "showFolder"
                    color: Theme.textSecondary
                    tip: qsTr("Show the imported files")
                    onClicked: phones.showFolder(card.phone.id)
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: card.phone.setUp
                    icon: "close"
                    color: Theme.textSecondary
                    tip: qsTr("Stop syncing this phone")
                    onClicked: ApplicationWindow.window.confirm(
                        qsTr("Stop syncing “%1”?").arg(card.phone.name),
                        qsTr("Photos already imported stay in your gallery and in %1.").arg(card.phone.folderLabel),
                        qsTr("Stop syncing"),
                        function() { phones.forget(card.phone.id) })
                }
            }
        }

        // progress while importing
        Rectangle {
            visible: card.phone.busy
            x: badge.width + Theme.s3
            width: parent.width - x
            height: 4
            radius: 2
            color: Theme.divider
            Rectangle {
                height: parent.height
                radius: 2
                color: Theme.accent
                width: card.phone.total > 0 ? parent.width * Math.min(1, card.phone.done / card.phone.total) : 0
                Behavior on width { NumberAnimation { duration: Theme.durNormal } }
            }
        }

        // first time: import everything, or only what's taken from now on
        Row {
            visible: !card.phone.setUp && !card.phone.busy && card.phone.browsable
            x: badge.width + Theme.s3
            spacing: Theme.s2
            PillButton {
                compact: true
                text: qsTr("Import all")
                icon: "phone"
                onClicked: phones.setUp(card.phone.id, "all")
            }
            PillButton {
                compact: true
                kind: "text"
                text: qsTr("Only new ones")
                onClicked: phones.setUp(card.phone.id, "new")
            }
        }

        Row {
            visible: card.phone.setUp
            x: badge.width + Theme.s3
            spacing: Theme.s3
            OneSwitch {
                anchors.verticalCenter: parent.verticalCenter
                checked: card.phone.auto
                onToggled: (c) => phones.setAuto(card.phone.id, c)
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Import new photos automatically when connected")
                color: Theme.text
                font.pixelSize: Theme.fontSmall + 1
            }
        }
    }
}
